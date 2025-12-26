"""Download manager service with queue management and progress tracking."""

import asyncio
import hashlib
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import structlog

from ..models import DiscInfo, DownloadProgress, GameData
from .errors import DownloadError, FileSystemError as FSError, get_error_service
from .http_client import HttpClientService
from .filesystem import FileSystemService

log = structlog.stdlib.get_logger()


class DownloadStatus(Enum):
    """Status of a download task."""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class DownloadTask:
    """Represents a single download task in the queue."""
    game: GameData
    disc: DiscInfo
    destination: Path
    task_id: str  # Unique identifier assigned at creation
    status: DownloadStatus = DownloadStatus.PENDING
    bytes_downloaded: int = 0
    total_bytes: int = 0
    download_speed: float = 0.0
    error_message: str | None = None
    checksum: str | None = None
    retry_count: int = 0


@dataclass
class QueueStatus:
    """Overall status of the download queue."""
    total_tasks: int = 0
    pending_tasks: int = 0
    downloading_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    paused_tasks: int = 0
    total_bytes: int = 0
    downloaded_bytes: int = 0


class DownloadManagerService:
    """Service for managing file downloads with queue management and progress tracking."""
    
    def __init__(
        self,
        http_client: HttpClientService,
        filesystem: FileSystemService,
        download_directory: Path,
        concurrent_downloads: int = 3,
        max_retries: int = 3,
        chunk_size: int = 8192
    ) -> None:
        """Initialize the download manager service.
        
        Args:
            http_client: HTTP client for making download requests
            filesystem: File system service for file operations
            download_directory: Base directory for downloads
            concurrent_downloads: Maximum concurrent downloads
            max_retries: Maximum retry attempts for failed downloads
            chunk_size: Size of chunks to read/write in bytes
        """
        self._http_client: HttpClientService = http_client
        self._filesystem: FileSystemService = filesystem
        self._download_directory: Path = download_directory
        self._concurrent_downloads: int = concurrent_downloads
        self._max_retries: int = max_retries
        self._chunk_size: int = chunk_size
        
        # Queue management
        self._queue: list[DownloadTask] = []
        self._active_downloads: dict[str, asyncio.Task[None]] = {}
        
        # State management
        self._is_paused: bool = False
        self._is_running: bool = False
        self._cancel_event: asyncio.Event = asyncio.Event()
        self._pause_event: asyncio.Event = asyncio.Event()
        self._pause_event.set()  # Not paused initially
        
        # Progress tracking
        self._current_progress: DownloadProgress = DownloadProgress(
            current_file="",
            bytes_downloaded=0,
            total_bytes=0,
            download_speed=0.0,
            eta_seconds=0
        )
        
        log.info(
            "Download manager service initialized",
            download_directory=str(download_directory),
            concurrent_downloads=concurrent_downloads,
            max_retries=max_retries
        )
    
    def add_to_queue(self, game: GameData, disc: DiscInfo) -> DownloadTask:
        """Add a download task to the queue.
        
        Args:
            game: Game data for the download
            disc: Disc information for the download
            
        Returns:
            The created download task
        """
        # Generate unique task ID
        task_id = f"{game.title}_{disc.disc_number}_{disc.media_id}_{uuid.uuid4().hex[:8]}"
        
        # Generate destination path
        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in game.title)
        destination = self._download_directory / game.category / safe_title / f"disc_{disc.disc_number}.zip"
        
        task = DownloadTask(
            game=game,
            disc=disc,
            destination=destination,
            task_id=task_id,
            total_bytes=disc.file_size or 0
        )
        
        self._queue.append(task)
        
        log.info(
            "Download task added to queue",
            task_id=task.task_id,
            game=game.title,
            disc=disc.disc_number,
            destination=str(destination)
        )
        
        return task
    
    def add_batch_to_queue(self, games: list[GameData]) -> list[DownloadTask]:
        """Add multiple games to the download queue.
        
        Args:
            games: List of games to add
            
        Returns:
            List of created download tasks
        """
        tasks = []
        for game in games:
            for disc in game.discs:
                task = self.add_to_queue(game, disc)
                tasks.append(task)
        
        log.info("Batch added to queue", total_tasks=len(tasks))
        return tasks
    
    def remove_from_queue(self, task_id: str) -> bool:
        """Remove a task from the queue.
        
        Args:
            task_id: ID of the task to remove
            
        Returns:
            True if task was removed, False if not found
        """
        for i, task in enumerate(self._queue):
            if task.task_id == task_id:
                if task.status == DownloadStatus.DOWNLOADING:
                    # Cancel active download
                    if task_id in self._active_downloads:
                        self._active_downloads[task_id].cancel()
                
                self._queue.pop(i)
                log.info("Download task removed from queue", task_id=task_id)
                return True
        
        log.warning("Download task not found for removal", task_id=task_id)
        return False
    
    def clear_queue(self) -> None:
        """Clear all pending tasks from the queue."""
        # Cancel active downloads
        for task_id, async_task in self._active_downloads.items():
            async_task.cancel()
        
        # Remove pending tasks
        self._queue = [t for t in self._queue if t.status in (DownloadStatus.COMPLETED, DownloadStatus.FAILED)]
        
        log.info("Download queue cleared")

    
    async def start_downloads(self) -> AsyncIterator[DownloadTask]:
        """Start processing the download queue.
        
        Yields:
            Download tasks as they complete or fail
        """
        if self._is_running:
            log.warning("Download manager is already running")
            return
        
        self._is_running = True
        self._cancel_event.clear()
        
        log.info("Starting download processing", queue_size=len(self._queue))
        
        try:
            while self._is_running:
                # Check for cancellation
                if self._cancel_event.is_set():
                    log.info("Download processing cancelled")
                    break
                
                # Wait if paused
                await self._pause_event.wait()
                
                # Get pending tasks
                pending_tasks = [t for t in self._queue if t.status == DownloadStatus.PENDING]
                
                if not pending_tasks and not self._active_downloads:
                    log.info("All downloads completed")
                    break
                
                # Start new downloads up to concurrent limit
                while (
                    len(self._active_downloads) < self._concurrent_downloads
                    and pending_tasks
                    and not self._cancel_event.is_set()
                ):
                    task = pending_tasks.pop(0)
                    task.status = DownloadStatus.DOWNLOADING
                    
                    async_task = asyncio.create_task(self._download_task(task))
                    self._active_downloads[task.task_id] = async_task
                
                # Wait for any download to complete
                if self._active_downloads:
                    done, _ = await asyncio.wait(
                        self._active_downloads.values(),
                        return_when=asyncio.FIRST_COMPLETED,
                        timeout=1.0
                    )
                    
                    # Process completed downloads
                    for completed_task in done:
                        # Find and yield the corresponding download task
                        for task_id, async_task in list(self._active_downloads.items()):
                            if async_task == completed_task:
                                del self._active_downloads[task_id]
                                
                                # Find the download task
                                for download_task in self._queue:
                                    if download_task.task_id == task_id:
                                        yield download_task
                                        break
                                break
                else:
                    # Small delay to prevent busy waiting
                    await asyncio.sleep(0.1)
        
        finally:
            self._is_running = False
            log.info("Download processing stopped")
    
    async def _download_task(self, task: DownloadTask) -> None:
        """Execute a single download task.
        
        Args:
            task: The download task to execute
        """
        start_time = time.time()
        last_update_time = start_time
        last_bytes = 0
        
        log.info(
            "Starting download",
            task_id=task.task_id,
            url=task.disc.download_url,
            destination=str(task.destination)
        )
        
        try:
            # Ensure destination directory exists
            self._filesystem.ensure_directory(task.destination.parent)
            
            # Download with progress tracking
            await self._download_with_progress(task, start_time)
            
            # Verify file integrity if checksum is available
            if task.checksum:
                if not await self._verify_checksum(task):
                    raise ValueError("Checksum verification failed")
            
            task.status = DownloadStatus.COMPLETED
            log.info(
                "Download completed",
                task_id=task.task_id,
                bytes_downloaded=task.bytes_downloaded,
                duration=time.time() - start_time
            )
            
        except asyncio.CancelledError:
            task.status = DownloadStatus.CANCELLED
            log.info("Download cancelled", task_id=task.task_id)
            # Clean up partial file
            if task.destination.exists():
                try:
                    task.destination.unlink()
                except OSError:
                    pass
            raise
            
        except Exception as e:
            task.retry_count += 1
            task.error_message = str(e)
            
            if task.retry_count < self._max_retries:
                task.status = DownloadStatus.PENDING
                log.warning(
                    "Download failed, will retry",
                    task_id=task.task_id,
                    error=str(e),
                    retry_count=task.retry_count
                )
            else:
                task.status = DownloadStatus.FAILED
                log.error(
                    "Download failed after max retries",
                    task_id=task.task_id,
                    error=str(e),
                    retry_count=task.retry_count
                )
            
            # Clean up partial file
            if task.destination.exists():
                try:
                    task.destination.unlink()
                except OSError:
                    pass

    
    async def _download_with_progress(self, task: DownloadTask, start_time: float) -> None:
        """Download a file with progress tracking.
        
        Args:
            task: The download task
            start_time: When the download started
        """
        import httpx
        
        last_update_time = start_time
        last_bytes = 0
        
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0), follow_redirects=True) as client:
            async with client.stream("GET", task.disc.download_url) as response:
                response.raise_for_status()
                
                task.total_bytes = int(response.headers.get("content-length", 0))
                
                with open(task.destination, "wb") as f:
                    async for chunk in response.aiter_bytes(self._chunk_size):
                        # Check for pause
                        await self._pause_event.wait()
                        
                        # Check for cancellation
                        if self._cancel_event.is_set():
                            raise asyncio.CancelledError()
                        
                        f.write(chunk)
                        task.bytes_downloaded += len(chunk)
                        
                        # Update speed calculation
                        current_time = time.time()
                        if current_time - last_update_time >= 0.5:  # Update every 0.5 seconds
                            elapsed = current_time - last_update_time
                            bytes_since_last = task.bytes_downloaded - last_bytes
                            task.download_speed = bytes_since_last / elapsed if elapsed > 0 else 0
                            
                            last_update_time = current_time
                            last_bytes = task.bytes_downloaded
                        
                        # Update overall progress
                        self._update_progress(task)
    
    def _update_progress(self, current_task: DownloadTask) -> None:
        """Update the overall download progress.
        
        Args:
            current_task: The currently downloading task
        """
        total_bytes = sum(t.total_bytes for t in self._queue if t.total_bytes > 0)
        downloaded_bytes = sum(t.bytes_downloaded for t in self._queue)
        
        # Calculate overall speed from active downloads
        total_speed = sum(
            t.download_speed for t in self._queue 
            if t.status == DownloadStatus.DOWNLOADING
        )
        
        # Calculate ETA
        remaining_bytes = total_bytes - downloaded_bytes
        eta_seconds = int(remaining_bytes / total_speed) if total_speed > 0 else 0
        
        self._current_progress = DownloadProgress(
            current_file=current_task.game.title,
            bytes_downloaded=downloaded_bytes,
            total_bytes=total_bytes,
            download_speed=total_speed,
            eta_seconds=eta_seconds
        )
    
    def pause_downloads(self) -> None:
        """Pause all active downloads."""
        if self._is_paused:
            log.warning("Downloads are already paused")
            return
        
        self._is_paused = True
        self._pause_event.clear()
        
        # Update status of downloading tasks
        for task in self._queue:
            if task.status == DownloadStatus.DOWNLOADING:
                task.status = DownloadStatus.PAUSED
        
        log.info("Downloads paused")
    
    def resume_downloads(self) -> None:
        """Resume paused downloads."""
        if not self._is_paused:
            log.warning("Downloads are not paused")
            return
        
        self._is_paused = False
        self._pause_event.set()
        
        # Update status of paused tasks
        for task in self._queue:
            if task.status == DownloadStatus.PAUSED:
                task.status = DownloadStatus.DOWNLOADING
        
        log.info("Downloads resumed")
    
    def cancel_downloads(self) -> None:
        """Cancel all downloads."""
        self._cancel_event.set()
        self._is_running = False
        
        # Cancel active async tasks
        for task_id, async_task in self._active_downloads.items():
            async_task.cancel()
        
        # Update status of active tasks
        for task in self._queue:
            if task.status in (DownloadStatus.DOWNLOADING, DownloadStatus.PENDING, DownloadStatus.PAUSED):
                task.status = DownloadStatus.CANCELLED
        
        log.info("Downloads cancelled")
    
    def get_download_progress(self) -> DownloadProgress:
        """Get the current download progress.
        
        Returns:
            Current download progress information
        """
        return self._current_progress
    
    def get_queue_status(self) -> QueueStatus:
        """Get the overall queue status.
        
        Returns:
            Queue status information
        """
        status = QueueStatus()
        
        for task in self._queue:
            status.total_tasks += 1
            status.total_bytes += task.total_bytes
            status.downloaded_bytes += task.bytes_downloaded
            
            if task.status == DownloadStatus.PENDING:
                status.pending_tasks += 1
            elif task.status == DownloadStatus.DOWNLOADING:
                status.downloading_tasks += 1
            elif task.status == DownloadStatus.COMPLETED:
                status.completed_tasks += 1
            elif task.status == DownloadStatus.FAILED:
                status.failed_tasks += 1
            elif task.status == DownloadStatus.PAUSED:
                status.paused_tasks += 1
        
        return status
    
    def get_task(self, task_id: str) -> DownloadTask | None:
        """Get a specific task by ID.
        
        Args:
            task_id: The task ID to look up
            
        Returns:
            The download task or None if not found
        """
        for task in self._queue:
            if task.task_id == task_id:
                return task
        return None
    
    def get_all_tasks(self) -> list[DownloadTask]:
        """Get all tasks in the queue.
        
        Returns:
            List of all download tasks
        """
        return list(self._queue)
    
    @property
    def is_paused(self) -> bool:
        """Check if downloads are paused."""
        return self._is_paused
    
    @property
    def is_running(self) -> bool:
        """Check if download processing is running."""
        return self._is_running

    
    async def _verify_checksum(self, task: DownloadTask) -> bool:
        """Verify the checksum of a downloaded file.
        
        Args:
            task: The download task with checksum to verify
            
        Returns:
            True if checksum matches, False otherwise
        """
        if not task.checksum:
            return True
        
        if not task.destination.exists():
            log.error("Cannot verify checksum, file does not exist", path=str(task.destination))
            return False
        
        log.debug("Verifying file checksum", task_id=task.task_id, expected=task.checksum)
        
        # Calculate file hash
        calculated_hash = await self._calculate_file_hash(task.destination)
        
        if calculated_hash.lower() == task.checksum.lower():
            log.info("Checksum verification passed", task_id=task.task_id)
            return True
        else:
            log.error(
                "Checksum verification failed",
                task_id=task.task_id,
                expected=task.checksum,
                calculated=calculated_hash
            )
            return False
    
    async def _calculate_file_hash(self, path: Path, algorithm: str = "sha256") -> str:
        """Calculate the hash of a file.
        
        Args:
            path: Path to the file
            algorithm: Hash algorithm to use (default: sha256)
            
        Returns:
            Hexadecimal hash string
        """
        hash_obj = hashlib.new(algorithm)
        
        with open(path, "rb") as f:
            while chunk := f.read(self._chunk_size):
                hash_obj.update(chunk)
        
        return hash_obj.hexdigest()
    
    async def verify_file_integrity(self, task_id: str, expected_checksum: str) -> bool:
        """Verify the integrity of a downloaded file.
        
        Args:
            task_id: ID of the task to verify
            expected_checksum: Expected checksum value
            
        Returns:
            True if file integrity is verified, False otherwise
        """
        task = self.get_task(task_id)
        if not task:
            log.error("Task not found for integrity verification", task_id=task_id)
            return False
        
        if task.status != DownloadStatus.COMPLETED:
            log.error("Cannot verify incomplete download", task_id=task_id, status=task.status.value)
            return False
        
        task.checksum = expected_checksum
        return await self._verify_checksum(task)
    
    async def retry_failed_download(self, task_id: str) -> bool:
        """Retry a failed download.
        
        Args:
            task_id: ID of the task to retry
            
        Returns:
            True if retry was initiated, False otherwise
        """
        task = self.get_task(task_id)
        if not task:
            log.error("Task not found for retry", task_id=task_id)
            return False
        
        if task.status not in (DownloadStatus.FAILED, DownloadStatus.CANCELLED):
            log.warning("Task is not in a retryable state", task_id=task_id, status=task.status.value)
            return False
        
        # Reset task state
        task.status = DownloadStatus.PENDING
        task.bytes_downloaded = 0
        task.error_message = None
        task.retry_count = 0
        
        log.info("Download task reset for retry", task_id=task_id)
        return True
    
    def get_failed_tasks(self) -> list[DownloadTask]:
        """Get all failed download tasks.
        
        Returns:
            List of failed download tasks
        """
        return [t for t in self._queue if t.status == DownloadStatus.FAILED]
    
    def get_completed_tasks(self) -> list[DownloadTask]:
        """Get all completed download tasks.
        
        Returns:
            List of completed download tasks
        """
        return [t for t in self._queue if t.status == DownloadStatus.COMPLETED]
