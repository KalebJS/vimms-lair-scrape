"""Download screen for managing and monitoring file downloads."""

import asyncio
from typing import ClassVar, override

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.message import Message
from textual.widgets import Button, DataTable, ProgressBar, Static
from textual.worker import Worker, WorkerState

import structlog

from src.services.download_manager import (
    DownloadManagerService,
    DownloadStatus,
    DownloadTask,
    QueueStatus,
)
from src.services.http_client import HttpClientService
from src.services.filesystem import FileSystemService

from .base import BaseScreen

log = structlog.stdlib.get_logger()


class DownloadScreen(BaseScreen):
    """Download screen for managing and monitoring file downloads.
    
    This screen provides:
    - Download queue display with individual progress
    - Batch download controls (start, pause, cancel)
    - Download statistics and completion status
    
    Requirements: 4.1, 4.2, 4.4, 4.5
    """
    
    class DownloadProgressUpdate(Message):
        """Message for download progress updates."""
        
        task: DownloadTask
        queue_status: QueueStatus
        
        def __init__(self, task: DownloadTask, queue_status: QueueStatus) -> None:
            super().__init__()
            self.task = task
            self.queue_status = queue_status
    
    class DownloadComplete(Message):
        """Message when a download completes."""
        
        task: DownloadTask
        
        def __init__(self, task: DownloadTask) -> None:
            super().__init__()
            self.task = task
    
    class AllDownloadsComplete(Message):
        """Message when all downloads are complete."""
        
        completed: int
        failed: int
        
        def __init__(self, completed: int, failed: int) -> None:
            super().__init__()
            self.completed = completed
            self.failed = failed
    
    SCREEN_TITLE: ClassVar[str] = "Downloads"
    SCREEN_NAME: ClassVar[str] = "downloads"
    
    CSS: ClassVar[str] = """
    DownloadScreen {
        align: center middle;
    }
    
    #download-container {
        width: 95%;
        height: 95%;
        padding: 1 2;
        border: solid $primary;
        background: $surface;
    }
    
    #download-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    
    .section-title {
        text-style: bold;
        color: $secondary;
        margin-top: 1;
        margin-bottom: 0;
    }
    
    #stats-section {
        height: auto;
        padding: 1;
        border: solid $primary-darken-2;
        margin-bottom: 1;
    }
    
    #stats-row {
        height: 3;
    }
    
    .stat-box {
        width: 1fr;
        height: 100%;
        padding: 0 1;
        content-align: center middle;
    }
    
    .stat-label {
        color: $text-muted;
    }
    
    .stat-value {
        text-style: bold;
    }
    
    #overall-progress-section {
        height: auto;
        padding: 1;
        margin-bottom: 1;
    }
    
    #overall-progress-bar {
        margin: 1 0;
    }
    
    #queue-section {
        height: 1fr;
        border: solid $primary-darken-2;
        padding: 1;
    }
    
    #queue-table {
        height: 100%;
    }
    
    #button-row {
        margin-top: 1;
        height: auto;
        align: center middle;
    }
    
    #button-row Button {
        margin: 0 1;
    }
    
    .status-pending {
        color: $text-muted;
    }
    
    .status-downloading {
        color: $primary;
    }
    
    .status-completed {
        color: $success;
    }
    
    .status-failed {
        color: $error;
    }
    
    .status-paused {
        color: $warning;
    }
    """
    
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "go_back", "Back", show=True),
        Binding("s", "start_downloads", "Start", show=True),
        Binding("p", "pause_downloads", "Pause", show=True),
        Binding("c", "cancel_downloads", "Cancel", show=True),
        Binding("r", "refresh_queue", "Refresh", show=True),
    ]
    
    # Instance attributes
    _download_manager: DownloadManagerService | None
    _download_worker: Worker[None] | None
    _is_downloading: bool
    _ui_update_timer: asyncio.Task[None] | None
    
    def __init__(self) -> None:
        """Initialize the download screen."""
        super().__init__()
        self._download_manager = None
        self._download_worker = None
        self._is_downloading = False
        self._ui_update_timer = None

    @override
    def compose(self) -> ComposeResult:
        """Compose the download screen layout."""
        with Container(id="download-container"):
            yield Static("📥 Downloads", id="download-title")
            
            # Statistics Section
            yield Static("Queue Statistics", classes="section-title")
            with Vertical(id="stats-section"):
                with Horizontal(id="stats-row"):
                    with Vertical(classes="stat-box"):
                        yield Static("Total", classes="stat-label")
                        yield Static("0", id="stat-total", classes="stat-value")
                    with Vertical(classes="stat-box"):
                        yield Static("Pending", classes="stat-label")
                        yield Static("0", id="stat-pending", classes="stat-value")
                    with Vertical(classes="stat-box"):
                        yield Static("Active", classes="stat-label")
                        yield Static("0", id="stat-active", classes="stat-value")
                    with Vertical(classes="stat-box"):
                        yield Static("Completed", classes="stat-label")
                        yield Static("0", id="stat-completed", classes="stat-value")
                    with Vertical(classes="stat-box"):
                        yield Static("Failed", classes="stat-label")
                        yield Static("0", id="stat-failed", classes="stat-value")
            
            # Overall Progress Section
            yield Static("Overall Progress", classes="section-title")
            with Vertical(id="overall-progress-section"):
                yield Static("Ready to start downloads", id="progress-status")
                yield ProgressBar(id="overall-progress-bar", total=100, show_eta=True)
                yield Static("", id="progress-details")
            
            # Queue Table Section
            yield Static("Download Queue", classes="section-title")
            with ScrollableContainer(id="queue-section"):
                yield DataTable(id="queue-table")
            
            # Control Buttons
            with Horizontal(id="button-row"):
                yield Button("Start", id="btn-start", variant="primary")
                yield Button("Pause", id="btn-pause", variant="warning", disabled=True)
                yield Button("Cancel", id="btn-cancel", variant="error", disabled=True)
                yield Button("Clear Completed", id="btn-clear", variant="default")
                yield Button("Back", id="btn-back", variant="default")
    
    @override
    async def on_mount(self) -> None:
        """Handle screen mount - initialize table and load queue."""
        await super().on_mount()
        self._setup_table()
        await self._load_download_queue()
    
    def _setup_table(self) -> None:
        """Set up the download queue table columns."""
        table = self.query_one("#queue-table", DataTable)
        table.add_columns("Game", "Disc", "Status", "Progress", "Speed", "Size")
        table.cursor_type = "row"
    
    async def _load_download_queue(self) -> None:
        """Load and display the current download queue."""
        # Get download manager from app context
        if self.game_app.download_manager:
            self._download_manager = self.game_app.download_manager
        else:
            # Fallback: create a new download manager if not available
            http_client = HttpClientService()
            filesystem = FileSystemService()
            config = self.game_app.app_state.current_config
            
            if config:
                from pathlib import Path
                self._download_manager = DownloadManagerService(
                    http_client=http_client,
                    filesystem=filesystem,
                    download_directory=config.download_directory,
                )
            else:
                # Use default download directory
                from pathlib import Path
                default_dir = Path.home() / "Downloads" / "games"
                self._download_manager = DownloadManagerService(
                    http_client=http_client,
                    filesystem=filesystem,
                    download_directory=default_dir,
                )
        
        self._refresh_queue_display()
        self._update_statistics()
    
    def _refresh_queue_display(self) -> None:
        """Refresh the queue table display."""
        table = self.query_one("#queue-table", DataTable)
        table.clear()
        
        if not self._download_manager:
            return
        
        tasks = self._download_manager.get_all_tasks()
        
        for task in tasks:
            status_text = self._get_status_text(task.status)
            progress_text = self._get_progress_text(task)
            speed_text = self._get_speed_text(task)
            size_text = self._get_size_text(task)
            
            table.add_row(
                task.game.title[:30],
                f"Disc {task.disc.disc_number}",
                status_text,
                progress_text,
                speed_text,
                size_text,
                key=task.task_id,
            )
    
    def _get_status_text(self, status: DownloadStatus) -> str:
        """Get display text for download status."""
        status_map = {
            DownloadStatus.PENDING: "⏳ Pending",
            DownloadStatus.DOWNLOADING: "⬇️ Downloading",
            DownloadStatus.PAUSED: "⏸️ Paused",
            DownloadStatus.COMPLETED: "✅ Completed",
            DownloadStatus.FAILED: "❌ Failed",
            DownloadStatus.CANCELLED: "🚫 Cancelled",
        }
        return status_map.get(status, str(status.value))
    
    def _get_progress_text(self, task: DownloadTask) -> str:
        """Get progress text for a download task."""
        if task.total_bytes > 0:
            percentage = (task.bytes_downloaded / task.total_bytes) * 100
            return f"{percentage:.1f}%"
        return "0%"
    
    def _get_speed_text(self, task: DownloadTask) -> str:
        """Get speed text for a download task."""
        if task.status == DownloadStatus.DOWNLOADING and task.download_speed > 0:
            if task.download_speed >= 1024 * 1024:
                return f"{task.download_speed / (1024 * 1024):.1f} MB/s"
            elif task.download_speed >= 1024:
                return f"{task.download_speed / 1024:.1f} KB/s"
            return f"{task.download_speed:.0f} B/s"
        return "-"
    
    def _get_size_text(self, task: DownloadTask) -> str:
        """Get size text for a download task."""
        if task.total_bytes > 0:
            if task.total_bytes >= 1024 * 1024 * 1024:
                return f"{task.total_bytes / (1024 * 1024 * 1024):.1f} GB"
            elif task.total_bytes >= 1024 * 1024:
                return f"{task.total_bytes / (1024 * 1024):.1f} MB"
            elif task.total_bytes >= 1024:
                return f"{task.total_bytes / 1024:.1f} KB"
            return f"{task.total_bytes} B"
        return "Unknown"
    
    def _update_statistics(self) -> None:
        """Update the statistics display."""
        if not self._download_manager:
            return
        
        status = self._download_manager.get_queue_status()
        
        self.query_one("#stat-total", Static).update(str(status.total_tasks))
        self.query_one("#stat-pending", Static).update(str(status.pending_tasks))
        self.query_one("#stat-active", Static).update(str(status.downloading_tasks))
        self.query_one("#stat-completed", Static).update(str(status.completed_tasks))
        self.query_one("#stat-failed", Static).update(str(status.failed_tasks))
        
        # Update overall progress
        if status.total_bytes > 0:
            percentage = (status.downloaded_bytes / status.total_bytes) * 100
            self.query_one("#overall-progress-bar", ProgressBar).update(progress=percentage)
            
            downloaded_mb = status.downloaded_bytes / (1024 * 1024)
            total_mb = status.total_bytes / (1024 * 1024)
            self.query_one("#progress-details", Static).update(
                f"{downloaded_mb:.1f} MB / {total_mb:.1f} MB"
            )

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id
        
        if button_id == "btn-start":
            await self._start_downloads()
        elif button_id == "btn-pause":
            self._pause_downloads()
        elif button_id == "btn-cancel":
            self._cancel_downloads()
        elif button_id == "btn-clear":
            self._clear_completed()
        elif button_id == "btn-back":
            await self.action_go_back()
    
    async def _start_downloads(self) -> None:
        """Start processing the download queue."""
        if self._is_downloading:
            self.notify_warning("Downloads are already in progress")
            return
        
        if not self._download_manager:
            self.notify_error("Download manager not initialized")
            return
        
        queue_status = self._download_manager.get_queue_status()
        if queue_status.pending_tasks == 0 and queue_status.paused_tasks == 0:
            self.notify_warning("No downloads in queue")
            return
        
        log.info("Starting downloads")
        
        self._is_downloading = True
        self._update_ui_for_downloading(True)
        self._update_progress_status("Starting downloads...")
        
        # Resume if paused
        if self._download_manager.is_paused:
            self._download_manager.resume_downloads()
        
        # Start download worker
        self._download_worker = self.run_worker(
            self._run_downloads(),
            name="download_worker",
            exclusive=True,
        )
        
        # Start periodic UI update
        self._start_update_timer()
    
    async def _run_downloads(self) -> None:
        """Run the download processing (executed in worker)."""
        if not self._download_manager:
            return
        
        completed_count = 0
        failed_count = 0
        
        try:
            async for task in self._download_manager.start_downloads():
                if task.status == DownloadStatus.COMPLETED:
                    completed_count += 1
                    _ = self.post_message(self.DownloadComplete(task))
                elif task.status == DownloadStatus.FAILED:
                    failed_count += 1
                
                queue_status = self._download_manager.get_queue_status()
                _ = self.post_message(self.DownloadProgressUpdate(task, queue_status))
            
            # All downloads complete
            _ = self.post_message(self.AllDownloadsComplete(completed_count, failed_count))
            
        except asyncio.CancelledError:
            log.info("Download worker cancelled")
            raise
        except Exception as e:
            log.error("Download processing failed", error=str(e))
            self.notify_error(f"Download error: {str(e)}")
    
    def _start_update_timer(self) -> None:
        """Start periodic UI updates."""
        async def update_loop() -> None:
            while self._is_downloading:
                self._refresh_queue_display()
                self._update_statistics()
                await asyncio.sleep(0.5)
        
        self._ui_update_timer = asyncio.create_task(update_loop())
    
    def _stop_update_timer(self) -> None:
        """Stop periodic UI updates."""
        if self._ui_update_timer:
            self._ui_update_timer.cancel()
            self._ui_update_timer = None
    
    def _pause_downloads(self) -> None:
        """Pause all active downloads."""
        if not self._download_manager:
            return
        
        if not self._is_downloading:
            self.notify_warning("No downloads in progress")
            return
        
        log.info("Pausing downloads")
        self._download_manager.pause_downloads()
        self._update_progress_status("Downloads paused")
        self._update_ui_for_paused(True)
        self.notify_success("Downloads paused")
    
    def _resume_downloads(self) -> None:
        """Resume paused downloads."""
        if not self._download_manager:
            return
        
        log.info("Resuming downloads")
        self._download_manager.resume_downloads()
        self._update_progress_status("Resuming downloads...")
        self._update_ui_for_paused(False)
        self.notify_success("Downloads resumed")
    
    def _cancel_downloads(self) -> None:
        """Cancel all downloads."""
        if not self._download_manager:
            return
        
        log.info("Cancelling downloads")
        self._download_manager.cancel_downloads()
        
        if self._download_worker:
            self._download_worker.cancel()
        
        self._stop_update_timer()
        self._is_downloading = False
        self._update_ui_for_downloading(False)
        self._update_progress_status("Downloads cancelled")
        self._refresh_queue_display()
        self._update_statistics()
        self.notify_warning("Downloads cancelled")
    
    def _clear_completed(self) -> None:
        """Clear completed downloads from the queue."""
        if not self._download_manager:
            return
        
        # Remove completed and failed tasks
        tasks_to_remove = [
            t.task_id for t in self._download_manager.get_all_tasks()
            if t.status in (DownloadStatus.COMPLETED, DownloadStatus.FAILED, DownloadStatus.CANCELLED)
        ]
        
        for task_id in tasks_to_remove:
            self._download_manager.remove_from_queue(task_id)
        
        self._refresh_queue_display()
        self._update_statistics()
        self.notify_success(f"Cleared {len(tasks_to_remove)} completed downloads")
    
    def _update_ui_for_downloading(self, is_downloading: bool) -> None:
        """Update UI elements based on download state."""
        start_btn = self.query_one("#btn-start", Button)
        pause_btn = self.query_one("#btn-pause", Button)
        cancel_btn = self.query_one("#btn-cancel", Button)
        
        start_btn.disabled = is_downloading
        pause_btn.disabled = not is_downloading
        cancel_btn.disabled = not is_downloading
        
        # Update pause button label
        if self._download_manager and self._download_manager.is_paused:
            pause_btn.label = "Resume"
        else:
            pause_btn.label = "Pause"
    
    def _update_ui_for_paused(self, is_paused: bool) -> None:
        """Update UI for paused state."""
        pause_btn = self.query_one("#btn-pause", Button)
        pause_btn.label = "Resume" if is_paused else "Pause"
    
    def _update_progress_status(self, status: str) -> None:
        """Update the progress status text."""
        self.query_one("#progress-status", Static).update(status)
    
    def on_download_screen_download_progress_update(
        self, event: DownloadProgressUpdate
    ) -> None:
        """Handle download progress update messages."""
        self._refresh_queue_display()
        self._update_statistics()
    
    def on_download_screen_download_complete(self, event: DownloadComplete) -> None:
        """Handle download complete messages."""
        log.info("Download completed", game=event.task.game.title)
        self._refresh_queue_display()
        self._update_statistics()
    
    def on_download_screen_all_downloads_complete(
        self, event: AllDownloadsComplete
    ) -> None:
        """Handle all downloads complete message."""
        self._stop_update_timer()
        self._is_downloading = False
        self._update_ui_for_downloading(False)
        
        if event.failed > 0:
            self._update_progress_status(
                f"✓ Completed: {event.completed} downloads, {event.failed} failed"
            )
            self.notify_warning(
                f"Downloads completed with {event.failed} failures"
            )
        else:
            self._update_progress_status(
                f"✓ All {event.completed} downloads completed successfully!"
            )
            self.notify_success(f"All {event.completed} downloads completed!")
        
        log.info(
            "All downloads complete",
            completed=event.completed,
            failed=event.failed
        )
    
    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Handle worker state changes."""
        if event.worker.name == "download_worker":
            log.debug("Download worker state changed", state=event.state)
            
            if event.state == WorkerState.CANCELLED:
                self._stop_update_timer()
                self._is_downloading = False
                self._update_ui_for_downloading(False)
    
    async def action_start_downloads(self) -> None:
        """Action handler for start downloads keyboard shortcut."""
        await self._start_downloads()
    
    def action_pause_downloads(self) -> None:
        """Action handler for pause downloads keyboard shortcut."""
        if self._download_manager and self._download_manager.is_paused:
            self._resume_downloads()
        else:
            self._pause_downloads()
    
    def action_cancel_downloads(self) -> None:
        """Action handler for cancel downloads keyboard shortcut."""
        self._cancel_downloads()
    
    def action_refresh_queue(self) -> None:
        """Action handler for refresh queue keyboard shortcut."""
        self._refresh_queue_display()
        self._update_statistics()
        self.notify_success("Queue refreshed")
    
    @override
    def on_screen_suspend(self) -> None:
        """Handle screen suspension."""
        super().on_screen_suspend()
        # Don't stop downloads when navigating away
    
    @override
    async def on_unmount(self) -> None:
        """Handle screen unmount."""
        await super().on_unmount()
        self._stop_update_timer()
