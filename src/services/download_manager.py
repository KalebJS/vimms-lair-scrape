"""Download manager service with queue management and progress tracking."""

import asyncio
import hashlib
import re
import shutil
import tempfile
import time
import uuid
import zipfile
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import py7zr
import structlog

from ..models import DiscInfo, DownloadProgress, GameData
from .http_client import HttpClientService
from .filesystem import FileSystemService
from .esde_compat import ESDECompatibilityService

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
        max_retries: int = 3,
        chunk_size: int = 8192,
        esde_mode: bool = True,
        download_delay: float = 2.0,
    ) -> None:
        """Initialize the download manager service.
        
        Args:
            http_client: HTTP client for making download requests
            filesystem: File system service for file operations
            download_directory: Base directory for downloads
            max_retries: Maximum retry attempts for failed downloads
            chunk_size: Size of chunks to read/write in bytes
            esde_mode: Enable ES-DE compatible folder structure (default: True)
            download_delay: Delay in seconds between downloads (default: 2.0)
        """
        self._http_client: HttpClientService = http_client
        self._filesystem: FileSystemService = filesystem
        self._download_directory: Path = download_directory
        self._max_retries: int = max_retries
        self._chunk_size: int = chunk_size
        self._esde_mode: bool = esde_mode
        self._download_delay: float = download_delay
        
        # Initialize ES-DE compatibility service if enabled
        self._esde_service: ESDECompatibilityService | None = None
        if esde_mode:
            self._esde_service = ESDECompatibilityService(download_directory)
        
        # Queue management (sequential processing)
        self._queue: list[DownloadTask] = []
        self._current_task: DownloadTask | None = None
        
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
            max_retries=max_retries,
            esde_mode=esde_mode,
        )
    
    @property
    def esde_mode(self) -> bool:
        """Check if ES-DE compatibility mode is enabled."""
        return self._esde_mode
    
    @esde_mode.setter
    def esde_mode(self, value: bool) -> None:
        """Enable or disable ES-DE compatibility mode."""
        self._esde_mode = value
        if value and not self._esde_service:
            self._esde_service = ESDECompatibilityService(self._download_directory)
        log.info("ES-DE mode changed", esde_mode=value)
    
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
        
        # Generate destination path based on mode
        if self._esde_mode and self._esde_service:
            # ES-DE compatible path: {base}/system_folder/GameTitle.zip
            destination = self._esde_service.generate_rom_path(
                vimm_category=game.category,
                game_title=game.title,
                disc_number=disc.disc_number,
                extension=".zip",  # Downloaded as zip, will be extracted
            )
        else:
            # Legacy path: {base}/category/safe_title/disc_X.zip
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
                    # Mark for cancellation - current download will check cancel event
                    task.status = DownloadStatus.CANCELLED
                
                self._queue.pop(i)
                log.info("Download task removed from queue", task_id=task_id)
                return True
        
        log.warning("Download task not found for removal", task_id=task_id)
        return False
    
    def clear_queue(self) -> None:
        """Clear all pending tasks from the queue."""
        # Mark current download as cancelled if running
        if self._current_task and self._current_task.status == DownloadStatus.DOWNLOADING:
            self._current_task.status = DownloadStatus.CANCELLED
        
        # Remove pending tasks
        self._queue = [t for t in self._queue if t.status in (DownloadStatus.COMPLETED, DownloadStatus.FAILED)]
        
        log.info("Download queue cleared")

    
    async def start_downloads(self) -> AsyncIterator[DownloadTask]:
        """Start processing the download queue sequentially.
        
        Downloads are processed one at a time to respect site rate limits.
        
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
                
                # Get next pending task
                pending_task: DownloadTask | None = None
                for task in self._queue:
                    if task.status == DownloadStatus.PENDING:
                        pending_task = task
                        break
                
                if pending_task is None:
                    log.info("All downloads completed")
                    break
                
                # Process single download
                self._current_task = pending_task
                pending_task.status = DownloadStatus.DOWNLOADING
                
                await self._download_task(pending_task)
                
                self._current_task = None
                yield pending_task
                
                # Add delay between downloads to respect rate limits
                if self._download_delay > 0 and not self._cancel_event.is_set():
                    log.debug("Waiting between downloads", delay=self._download_delay)
                    await asyncio.sleep(self._download_delay)
        
        finally:
            self._is_running = False
            self._current_task = None
            log.info("Download processing stopped")
    
    async def _download_task(self, task: DownloadTask) -> None:
        """Execute a single download task.
        
        Args:
            task: The download task to execute
        """
        start_time = time.time()
        
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
            
            # Detect actual archive type by reading file magic bytes
            actual_archive_type = await self._detect_archive_type(task.destination)
            
            # Extract archive files and remove archive
            if actual_archive_type == "zip":
                await self._extract_and_cleanup_zip(task)
            elif actual_archive_type == "7z":
                await self._extract_and_cleanup_7z(task)
            elif actual_archive_type:
                log.warning(
                    "Unknown archive type, skipping extraction",
                    task_id=task.task_id,
                    detected_type=actual_archive_type,
                )
            
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
            
            # Check if this is a rate limit error (429)
            is_rate_limited = "429" in str(e) or "Too Many Requests" in str(e)
            
            if task.retry_count < self._max_retries:
                task.status = DownloadStatus.PENDING
                
                # Exponential backoff for retries, especially for rate limiting
                if is_rate_limited:
                    backoff_delay = min(30.0, self._download_delay * (2 ** task.retry_count))
                else:
                    backoff_delay = self._download_delay * task.retry_count
                
                log.warning(
                    "Download failed, will retry after backoff",
                    task_id=task.task_id,
                    error=str(e),
                    retry_count=task.retry_count,
                    backoff_delay=backoff_delay,
                )
                
                # Wait before allowing retry
                await asyncio.sleep(backoff_delay)
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
    
    async def _extract_and_cleanup_zip(self, task: DownloadTask) -> None:
        """Extract a zip file and remove the archive.
        
        For ES-DE mode, extracted files are renamed to match the game title
        with proper disc numbering for multi-disc games.
        
        Args:
            task: The download task with zip file to extract
        """
        zip_path = task.destination
        
        # Determine extraction directory
        if self._esde_mode and self._esde_service:
            extract_dir = self._esde_service.generate_extraction_directory(
                vimm_category=task.game.category,
                game_title=task.game.title,
                disc_number=task.disc.disc_number,
            )
        else:
            extract_dir = zip_path.parent
        
        log.info(
            "Extracting zip archive",
            task_id=task.task_id,
            zip_path=str(zip_path),
            extract_dir=str(extract_dir),
            esde_mode=self._esde_mode,
        )
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                extracted_files = zf.namelist()
                
                if self._esde_mode and self._esde_service:
                    # ES-DE mode: rename extracted files to match game title
                    await self._extract_with_esde_naming(zf, task, extract_dir)
                else:
                    # Legacy mode: extract as-is
                    zf.extractall(extract_dir)
            
            log.info(
                "Zip extraction completed",
                task_id=task.task_id,
                files_extracted=len(extracted_files),
            )
            
            # Remove the zip archive
            zip_path.unlink()
            log.info(
                "Zip archive removed",
                task_id=task.task_id,
                zip_path=str(zip_path),
            )
            
        except zipfile.BadZipFile as e:
            log.error(
                "Failed to extract zip - invalid archive",
                task_id=task.task_id,
                error=str(e),
            )
            # Don't fail the download, just leave the zip file
        except Exception as e:
            log.error(
                "Failed to extract zip",
                task_id=task.task_id,
                error=str(e),
            )
            # Don't fail the download, just leave the zip file
    
    async def _extract_with_esde_naming(
        self,
        zf: zipfile.ZipFile,
        task: DownloadTask,
        extract_dir: Path,
    ) -> None:
        """Extract zip contents with ES-DE compatible naming.
        
        Renames extracted ROM files to match the game title while preserving
        the original file extension. For multi-disc games, adds disc numbering.
        
        Args:
            zf: Open ZipFile object
            task: The download task
            extract_dir: Directory to extract files to
        """
        if not self._esde_service:
            return
        
        # Ensure extraction directory exists
        self._filesystem.ensure_directory(extract_dir)
        
        # Get expected extensions for this system
        expected_extensions = self._esde_service.get_expected_extensions(task.game.category)
        
        for member in zf.namelist():
            # Skip directories
            if member.endswith('/'):
                continue
            
            original_name = Path(member).name
            original_ext = Path(member).suffix.lower()
            
            # Check if this is a ROM file we should rename
            is_rom_file = original_ext in expected_extensions or original_ext in (
                '.iso', '.bin', '.cue', '.chd', '.rvz', '.gcz', '.wbfs',
                '.nds', '.gba', '.gbc', '.gb', '.nes', '.sfc', '.smc',
                '.n64', '.z64', '.v64', '.md', '.gen', '.sms', '.gg',
                '.pce', '.ngp', '.ngc', '.vb', '.a26', '.a52', '.a78',
                '.j64', '.jag', '.lnx', '.32x', '.cdi', '.gdi',
            )
            
            if is_rom_file:
                # Generate ES-DE compatible filename
                new_path = self._esde_service.generate_rom_path(
                    vimm_category=task.game.category,
                    game_title=task.game.title,
                    disc_number=task.disc.disc_number,
                    extension=original_ext,
                )
                
                # Extract to the new path
                with zf.open(member) as source:
                    self._filesystem.ensure_directory(new_path.parent)
                    with open(new_path, 'wb') as target:
                        target.write(source.read())
                
                log.debug(
                    "Extracted ROM with ES-DE naming",
                    original=original_name,
                    new_name=new_path.name,
                )
            else:
                # Extract non-ROM files (like .cue files) with original names
                # but in the correct directory
                target_path = extract_dir / original_name
                with zf.open(member) as source:
                    with open(target_path, 'wb') as target:
                        target.write(source.read())
                
                log.debug(
                    "Extracted supporting file",
                    filename=original_name,
                )

    async def _extract_and_cleanup_7z(self, task: DownloadTask) -> None:
        """Extract a 7z file and remove the archive.
        
        For ES-DE mode, extracted files are renamed to match the game title
        with proper disc numbering for multi-disc games.
        
        Args:
            task: The download task with 7z file to extract
        """
        archive_path = task.destination
        
        # Determine extraction directory
        if self._esde_mode and self._esde_service:
            extract_dir = self._esde_service.generate_extraction_directory(
                vimm_category=task.game.category,
                game_title=task.game.title,
                disc_number=task.disc.disc_number,
            )
        else:
            extract_dir = archive_path.parent
        
        log.info(
            "Extracting 7z archive",
            task_id=task.task_id,
            archive_path=str(archive_path),
            extract_dir=str(extract_dir),
            esde_mode=self._esde_mode,
        )
        
        try:
            with py7zr.SevenZipFile(archive_path, mode='r') as archive:
                file_list = archive.getnames()
                
                if self._esde_mode and self._esde_service:
                    # ES-DE mode: extract to temp then rename
                    await self._extract_7z_with_esde_naming(archive, task, extract_dir)
                else:
                    # Legacy mode: extract as-is
                    archive.extractall(path=extract_dir)
            
            log.info(
                "7z extraction completed",
                task_id=task.task_id,
                files_extracted=len(file_list),
            )
            
            # Remove the 7z archive
            archive_path.unlink()
            log.info(
                "7z archive removed",
                task_id=task.task_id,
                archive_path=str(archive_path),
            )
            
        except py7zr.Bad7zFile as e:
            log.error(
                "Failed to extract 7z - invalid archive",
                task_id=task.task_id,
                error=str(e),
            )
            # Don't fail the download, just leave the 7z file
        except Exception as e:
            log.error(
                "Failed to extract 7z",
                task_id=task.task_id,
                error=str(e),
            )
            # Don't fail the download, just leave the 7z file
    
    async def _extract_7z_with_esde_naming(
        self,
        archive: py7zr.SevenZipFile,
        task: DownloadTask,
        extract_dir: Path,
    ) -> None:
        """Extract 7z contents with ES-DE compatible naming.
        
        Args:
            archive: Open SevenZipFile object
            task: The download task
            extract_dir: Directory to extract files to
        """
        if not self._esde_service:
            return
        
        # Ensure extraction directory exists
        self._filesystem.ensure_directory(extract_dir)
        
        # Get expected extensions for this system
        expected_extensions = self._esde_service.get_expected_extensions(task.game.category)
        
        # Extract to a temp directory first, then rename
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            archive.extractall(path=temp_path)
            
            # Process extracted files
            for extracted_file in temp_path.rglob('*'):
                if extracted_file.is_dir():
                    continue
                
                original_name = extracted_file.name
                original_ext = extracted_file.suffix.lower()
                
                # Check if this is a ROM file we should rename
                is_rom_file = original_ext in expected_extensions or original_ext in (
                    '.iso', '.bin', '.cue', '.chd', '.rvz', '.gcz', '.wbfs', '.ciso',
                    '.nds', '.gba', '.gbc', '.gb', '.nes', '.sfc', '.smc',
                    '.n64', '.z64', '.v64', '.md', '.gen', '.sms', '.gg',
                    '.pce', '.ngp', '.ngc', '.vb', '.a26', '.a52', '.a78',
                    '.j64', '.jag', '.lnx', '.32x', '.cdi', '.gdi',
                )
                
                if is_rom_file:
                    # Generate ES-DE compatible filename
                    new_path = self._esde_service.generate_rom_path(
                        vimm_category=task.game.category,
                        game_title=task.game.title,
                        disc_number=task.disc.disc_number,
                        extension=original_ext,
                    )
                    
                    # Move to the new path
                    self._filesystem.ensure_directory(new_path.parent)
                    shutil.move(str(extracted_file), str(new_path))
                    
                    log.debug(
                        "Extracted ROM with ES-DE naming",
                        original=original_name,
                        new_name=new_path.name,
                    )
                else:
                    # Move non-ROM files with original names
                    target_path = extract_dir / original_name
                    shutil.move(str(extracted_file), str(target_path))
                    
                    log.debug(
                        "Extracted supporting file",
                        filename=original_name,
                    )

    
    async def _download_with_progress(self, task: DownloadTask, start_time: float) -> None:
        """Download a file with progress tracking.
        
        Vimm's Lair requires a GET request to dl3.vimm.net with mediaId as query param,
        plus proper Referer header to pass bot protection.
        
        Args:
            task: The download task
            start_time: When the download started
        """
        import httpx
        
        last_update_time = start_time
        last_bytes = 0
        
        # Use the download URL from the disc info (includes correct server like dl2 or dl3)
        # Parse the URL to extract base and mediaId for proper request
        download_url = task.disc.download_url
        
        # Required headers to pass bot protection
        headers = {
            "Referer": task.game.game_url,
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        
        log.debug(
            "Initiating download request",
            url=download_url,
            media_id=task.disc.media_id,
        )
        
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(300.0, connect=30.0),  # Longer timeout for large files
            follow_redirects=True,
            verify=False,  # Disable SSL verification for compatibility
        ) as client:
            async with client.stream("GET", download_url, headers=headers) as response:
                response.raise_for_status()
                
                # Check content type - Vimm's Lair returns HTML for errors
                content_type = response.headers.get("content-type", "")
                if "text/html" in content_type.lower():
                    raise ValueError(
                        "Server returned HTML instead of file - likely rate limited or invalid request"
                    )
                
                task.total_bytes = int(response.headers.get("content-length", 0))
                
                # Try to get filename from Content-Disposition header
                content_disposition = response.headers.get("content-disposition", "")
                if "filename=" in content_disposition:
                    # Extract filename to get the actual extension
                    match = re.search(r'filename="?([^";\n]+)"?', content_disposition)
                    if match:
                        server_filename = match.group(1)
                        server_ext = Path(server_filename).suffix.lower()
                        
                        # Update destination with correct extension while preserving ES-DE naming
                        if self._esde_mode and self._esde_service:
                            # Regenerate path with correct extension
                            task.destination = self._esde_service.generate_rom_path(
                                vimm_category=task.game.category,
                                game_title=task.game.title,
                                disc_number=task.disc.disc_number,
                                extension=server_ext,
                            )
                        else:
                            # Legacy mode: just use the server filename
                            task.destination = task.destination.parent / server_filename
                        
                        log.debug(
                            "Updated destination from Content-Disposition",
                            server_filename=server_filename,
                            new_destination=str(task.destination),
                        )
                else:
                    # No Content-Disposition header - check if it's a known archive type
                    # by content-type or assume based on the response
                    if "application/x-7z-compressed" in content_type.lower():
                        # Update extension to .7z
                        if self._esde_mode and self._esde_service:
                            task.destination = self._esde_service.generate_rom_path(
                                vimm_category=task.game.category,
                                game_title=task.game.title,
                                disc_number=task.disc.disc_number,
                                extension=".7z",
                            )
                        else:
                            task.destination = task.destination.with_suffix(".7z")
                        
                        log.debug(
                            "Updated destination from content-type",
                            content_type=content_type,
                            new_destination=str(task.destination),
                        )
                
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
        
        # Update status of pending/active tasks
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

    
    async def _detect_archive_type(self, path: Path) -> str | None:
        """Detect the actual archive type by reading file magic bytes.
        
        Args:
            path: Path to the file to check
            
        Returns:
            Archive type string ('zip', '7z') or None if not an archive
        """
        if not path.exists():
            return None
        
        try:
            with open(path, "rb") as f:
                magic_bytes = f.read(8)
            
            # ZIP magic: PK (0x50 0x4B)
            if magic_bytes[:2] == b'PK':
                return "zip"
            
            # 7z magic: 7z¼¯' (0x37 0x7A 0xBC 0xAF 0x27 0x1C)
            if magic_bytes[:6] == b'7z\xbc\xaf\x27\x1c':
                return "7z"
            
            # Check file extension as fallback
            suffix = path.suffix.lower()
            if suffix == '.zip':
                return "zip"
            elif suffix == '.7z':
                return "7z"
            
            return None
            
        except Exception as e:
            log.warning(
                "Failed to detect archive type",
                path=str(path),
                error=str(e),
            )
            return None

    
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
