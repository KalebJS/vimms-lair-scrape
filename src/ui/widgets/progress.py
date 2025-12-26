"""Custom progress tracking widgets for scraping operations."""

from typing import ClassVar, override

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widgets import ProgressBar, Static
from textual.widget import Widget

import structlog

from src.models.progress import ScrapingProgress

log = structlog.stdlib.get_logger()


class ScrapingProgressWidget(Widget):
    """Widget for displaying real-time scraping progress.
    
    This widget provides:
    - Progress bar with percentage
    - Current letter and game being processed
    - Games processed count
    - Estimated time remaining
    
    Requirements: 3.2, 3.4
    """
    
    DEFAULT_CSS: ClassVar[str] = """
    ScrapingProgressWidget {
        height: auto;
        padding: 1;
        border: solid $primary-darken-2;
        background: $surface;
    }
    
    ScrapingProgressWidget .progress-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    
    ScrapingProgressWidget .progress-status {
        margin-bottom: 1;
    }
    
    ScrapingProgressWidget .progress-bar-container {
        height: 3;
        margin-bottom: 1;
    }
    
    ScrapingProgressWidget .progress-details {
        color: $text-muted;
    }
    
    ScrapingProgressWidget .current-item {
        color: $text;
        text-style: italic;
    }
    
    ScrapingProgressWidget .progress-stats {
        margin-top: 1;
        color: $text-muted;
    }
    """
    
    # Reactive attributes for progress tracking
    status: reactive[str] = reactive("Ready", init=False)
    progress_value: reactive[float] = reactive(0.0, init=False)
    current_letter: reactive[str] = reactive("", init=False)
    current_game: reactive[str] = reactive("", init=False)
    games_processed: reactive[int] = reactive(0, init=False)
    total_games: reactive[int] = reactive(0, init=False)
    
    def __init__(
        self,
        title: str = "Progress",
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the progress widget.
        
        Args:
            title: Title to display above the progress bar
            name: Widget name
            id: Widget ID
            classes: CSS classes
        """
        super().__init__(name=name, id=id, classes=classes)
        self._title: str = title
        self.status = "Ready"
        self.progress_value = 0.0
        self.current_letter = ""
        self.current_game = ""
        self.games_processed = 0
        self.total_games = 0
    
    @override
    def compose(self) -> ComposeResult:
        """Compose the progress widget layout."""
        yield Static(f"📊 {self._title}", classes="progress-title")
        yield Static("Ready to start", id="progress-status", classes="progress-status")
        with Vertical(classes="progress-bar-container"):
            yield ProgressBar(id="progress-bar", total=100, show_eta=True)
        yield Static("", id="progress-details", classes="progress-details")
        yield Static("", id="current-item", classes="current-item")
        yield Static("", id="progress-stats", classes="progress-stats")
    
    def update_progress(self, progress: ScrapingProgress) -> None:
        """Update the widget with new progress information.
        
        Args:
            progress: ScrapingProgress object with current state
        """
        self.current_letter = progress.current_letter
        self.current_game = progress.current_game
        self.games_processed = progress.games_processed
        self.total_games = progress.total_games
        
        # Calculate percentage
        if progress.total_games > 0:
            self.progress_value = (progress.games_processed / progress.total_games) * 100
        else:
            self.progress_value = 0.0
        
        # Update status
        if progress.current_letter:
            self.status = f"Scraping letter {progress.current_letter}..."
        
        self._refresh_display()
    
    def set_status(self, status: str) -> None:
        """Set the status message.
        
        Args:
            status: Status message to display
        """
        self.status = status
        self._refresh_display()
    
    def set_complete(self, success: bool = True, message: str = "") -> None:
        """Mark the progress as complete.
        
        Args:
            success: Whether the operation completed successfully
            message: Optional completion message
        """
        self.progress_value = 100.0 if success else 0.0
        if message:
            self.status = message
        elif success:
            self.status = "✓ Completed successfully!"
        else:
            self.status = "✗ Operation failed"
        self._refresh_display()
    
    def reset(self) -> None:
        """Reset the progress widget to initial state."""
        self.status = "Ready"
        self.progress_value = 0.0
        self.current_letter = ""
        self.current_game = ""
        self.games_processed = 0
        self.total_games = 0
        self._refresh_display()
    
    def _refresh_display(self) -> None:
        """Refresh all display elements."""
        try:
            # Update status
            status_widget = self.query_one("#progress-status", Static)
            status_widget.update(self.status)
            
            # Update progress bar
            progress_bar = self.query_one("#progress-bar", ProgressBar)
            progress_bar.update(progress=self.progress_value)
            
            # Update details
            details_widget = self.query_one("#progress-details", Static)
            if self.total_games > 0:
                details_widget.update(
                    f"Processed: {self.games_processed}/{self.total_games} games"
                )
            else:
                details_widget.update("")
            
            # Update current item
            current_widget = self.query_one("#current-item", Static)
            if self.current_game:
                current_widget.update(f"Current: {self.current_game}")
            else:
                current_widget.update("")
            
            # Update stats
            stats_widget = self.query_one("#progress-stats", Static)
            if self.current_letter:
                stats_widget.update(f"Letter: {self.current_letter}")
            else:
                stats_widget.update("")
                
        except Exception as e:
            log.debug("Failed to refresh progress display", error=str(e))


class StatisticsWidget(Widget):
    """Widget for displaying scraping statistics.
    
    This widget shows:
    - Total games scraped
    - Success/error counts
    - Time elapsed
    - Average processing speed
    
    Requirements: 3.4
    """
    
    DEFAULT_CSS: ClassVar[str] = """
    StatisticsWidget {
        height: auto;
        padding: 1;
        border: solid $secondary;
        background: $surface;
    }
    
    StatisticsWidget .stats-title {
        text-style: bold;
        color: $secondary;
        margin-bottom: 1;
    }
    
    StatisticsWidget .stat-row {
        height: 1;
    }
    
    StatisticsWidget .stat-label {
        color: $text-muted;
    }
    
    StatisticsWidget .stat-value {
        color: $text;
        text-style: bold;
    }
    
    StatisticsWidget .stat-success {
        color: $success;
    }
    
    StatisticsWidget .stat-error {
        color: $error;
    }
    """
    
    # Reactive attributes
    total_games: reactive[int] = reactive(0, init=False)
    successful: reactive[int] = reactive(0, init=False)
    errors: reactive[int] = reactive(0, init=False)
    elapsed_seconds: reactive[int] = reactive(0, init=False)
    
    def __init__(
        self,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the statistics widget."""
        super().__init__(name=name, id=id, classes=classes)
        self.total_games = 0
        self.successful = 0
        self.errors = 0
        self.elapsed_seconds = 0
    
    @override
    def compose(self) -> ComposeResult:
        """Compose the statistics widget layout."""
        yield Static("📈 Statistics", classes="stats-title")
        yield Static("Total: 0", id="stat-total", classes="stat-row")
        yield Static("Success: 0", id="stat-success", classes="stat-row stat-success")
        yield Static("Errors: 0", id="stat-errors", classes="stat-row stat-error")
        yield Static("Time: 0:00", id="stat-time", classes="stat-row")
        yield Static("Speed: -- games/min", id="stat-speed", classes="stat-row")
    
    def update_stats(
        self,
        total: int,
        successful: int,
        errors: int,
        elapsed_seconds: int,
    ) -> None:
        """Update statistics display.
        
        Args:
            total: Total games processed
            successful: Successfully scraped games
            errors: Number of errors
            elapsed_seconds: Time elapsed in seconds
        """
        self.total_games = total
        self.successful = successful
        self.errors = errors
        self.elapsed_seconds = elapsed_seconds
        self._refresh_display()
    
    def reset(self) -> None:
        """Reset statistics to initial state."""
        self.total_games = 0
        self.successful = 0
        self.errors = 0
        self.elapsed_seconds = 0
        self._refresh_display()
    
    def _refresh_display(self) -> None:
        """Refresh all display elements."""
        try:
            # Update total
            total_widget = self.query_one("#stat-total", Static)
            total_widget.update(f"Total: {self.total_games}")
            
            # Update success
            success_widget = self.query_one("#stat-success", Static)
            success_widget.update(f"Success: {self.successful}")
            
            # Update errors
            errors_widget = self.query_one("#stat-errors", Static)
            errors_widget.update(f"Errors: {self.errors}")
            
            # Update time
            time_widget = self.query_one("#stat-time", Static)
            minutes = self.elapsed_seconds // 60
            seconds = self.elapsed_seconds % 60
            time_widget.update(f"Time: {minutes}:{seconds:02d}")
            
            # Update speed
            speed_widget = self.query_one("#stat-speed", Static)
            if self.elapsed_seconds > 0:
                speed = (self.successful / self.elapsed_seconds) * 60
                speed_widget.update(f"Speed: {speed:.1f} games/min")
            else:
                speed_widget.update("Speed: -- games/min")
                
        except Exception as e:
            log.debug("Failed to refresh statistics display", error=str(e))


class ErrorListWidget(Widget):
    """Widget for displaying errors without stopping operations.
    
    This widget provides:
    - Scrollable list of recent errors
    - Error count display
    - Ability to clear errors
    
    Requirements: 3.3
    """
    
    DEFAULT_CSS: ClassVar[str] = """
    ErrorListWidget {
        height: auto;
        max-height: 12;
        padding: 1;
        border: solid $error;
        background: $surface;
        display: none;
    }
    
    ErrorListWidget.has-errors {
        display: block;
    }
    
    ErrorListWidget .error-title {
        text-style: bold;
        color: $error;
        margin-bottom: 1;
    }
    
    ErrorListWidget .error-count {
        color: $error;
        margin-bottom: 1;
    }
    
    ErrorListWidget .error-list {
        color: $error;
        overflow-y: auto;
    }
    
    ErrorListWidget .error-item {
        margin-bottom: 0;
    }
    """
    
    # Reactive attributes
    error_count: reactive[int] = reactive(0, init=False)
    
    # Instance attributes
    _errors: list[str]
    _max_display: int
    
    def __init__(
        self,
        max_display: int = 5,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the error list widget.
        
        Args:
            max_display: Maximum number of errors to display
            name: Widget name
            id: Widget ID
            classes: CSS classes
        """
        super().__init__(name=name, id=id, classes=classes)
        self._errors = []
        self._max_display = max_display
        self.error_count = 0
    
    @override
    def compose(self) -> ComposeResult:
        """Compose the error list widget layout."""
        yield Static("⚠️ Errors", classes="error-title")
        yield Static("0 errors", id="error-count", classes="error-count")
        yield Static("", id="error-list", classes="error-list")
    
    def add_error(self, error: str) -> None:
        """Add an error to the list.
        
        Args:
            error: Error message to add
        """
        self._errors.append(error)
        self.error_count = len(self._errors)
        self._refresh_display()
        log.debug("Error added to widget", error=error, total_errors=self.error_count)
    
    def set_errors(self, errors: list[str]) -> None:
        """Set the complete error list.
        
        Args:
            errors: List of error messages
        """
        self._errors = errors.copy()
        self.error_count = len(self._errors)
        self._refresh_display()
    
    def clear_errors(self) -> None:
        """Clear all errors."""
        self._errors.clear()
        self.error_count = 0
        self._refresh_display()
    
    def get_errors(self) -> list[str]:
        """Get all errors.
        
        Returns:
            List of error messages
        """
        return self._errors.copy()
    
    def _refresh_display(self) -> None:
        """Refresh the error display."""
        try:
            # Show/hide widget based on error count
            if self.error_count > 0:
                _ = self.add_class("has-errors")
            else:
                _ = self.remove_class("has-errors")
            
            # Update error count
            count_widget = self.query_one("#error-count", Static)
            count_widget.update(f"{self.error_count} error(s)")
            
            # Update error list
            list_widget = self.query_one("#error-list", Static)
            if self._errors:
                # Show most recent errors
                recent_errors = self._errors[-self._max_display:]
                error_text = "\n".join(f"• {e}" for e in recent_errors)
                if len(self._errors) > self._max_display:
                    hidden_count = len(self._errors) - self._max_display
                    error_text += f"\n... and {hidden_count} more error(s)"
                list_widget.update(error_text)
            else:
                list_widget.update("")
                
        except Exception as e:
            log.debug("Failed to refresh error display", error=str(e))
