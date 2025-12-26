"""Scraping screen for configuring and monitoring scraping operations."""

import asyncio
from typing import ClassVar, override

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.message import Message
from textual.widgets import Button, Input, Label, ProgressBar, Static
from textual.worker import Worker, WorkerState

import structlog

from src.models.config import AppConfig
from src.models.game import GameData
from src.services.game_scraper import GameScraperService
from src.services.http_client import HttpClientService

from .base import BaseScreen

log = structlog.stdlib.get_logger()


class ScrapingScreen(BaseScreen):
    """Scraping screen for configuring and monitoring scraping operations.
    
    This screen provides:
    - Configuration form for target letters and category
    - Real-time progress display with progress bars
    - Cancel/pause controls for long-running operations
    - Error display without stopping the overall process
    
    Requirements: 3.1, 3.2, 3.5
    """
    
    # Custom messages for progress updates
    class ProgressUpdate(Message):
        """Message for progress updates from scraping worker."""
        
        status: str
        progress: float
        details: str
        current_game: str
        errors: list[str]
        
        def __init__(
            self,
            status: str,
            progress: float,
            details: str,
            current_game: str,
            errors: list[str] | None = None,
        ) -> None:
            super().__init__()
            self.status = status
            self.progress = progress
            self.details = details
            self.current_game = current_game
            self.errors = errors or []
    
    class GameScraped(Message):
        """Message when a game is successfully scraped."""
        
        game_data: GameData
        
        def __init__(self, game_data: GameData) -> None:
            super().__init__()
            self.game_data = game_data
    
    class ScrapingComplete(Message):
        """Message when scraping is complete."""
        
        games_scraped: int
        errors: list[str]
        
        def __init__(self, games_scraped: int, errors: list[str]) -> None:
            super().__init__()
            self.games_scraped = games_scraped
            self.errors = errors
    
    class ScrapingError(Message):
        """Message when scraping fails."""
        
        error: str
        
        def __init__(self, error: str) -> None:
            super().__init__()
            self.error = error
    
    SCREEN_TITLE: ClassVar[str] = "Scrape Games"
    SCREEN_NAME: ClassVar[str] = "scraping"
    
    CSS: ClassVar[str] = """
    ScrapingScreen {
        align: center middle;
    }
    
    #scraping-container {
        width: 90;
        height: auto;
        max-height: 95%;
        padding: 1 2;
        border: solid $primary;
        background: $surface;
    }
    
    #scraping-title {
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
    
    .form-group {
        margin-bottom: 1;
        height: auto;
    }
    
    .form-label {
        margin-bottom: 0;
        color: $text;
    }
    
    .form-input {
        width: 100%;
    }
    
    .form-hint {
        color: $text-muted;
        text-style: italic;
        margin-top: 0;
    }
    
    #progress-section {
        margin-top: 1;
        padding: 1;
        border: solid $primary-darken-2;
        height: auto;
    }
    
    #progress-status {
        margin-bottom: 1;
    }
    
    #progress-bar-container {
        height: 3;
        margin-bottom: 1;
    }
    
    #progress-details {
        color: $text-muted;
        height: auto;
    }
    
    #current-game {
        color: $text;
        text-style: italic;
    }
    
    #error-section {
        margin-top: 1;
        padding: 1;
        border: solid $error;
        height: auto;
        max-height: 10;
        overflow-y: auto;
        display: none;
    }
    
    #error-section.has-errors {
        display: block;
    }
    
    .error-title {
        color: $error;
        text-style: bold;
    }
    
    .error-list {
        color: $error;
    }
    
    #button-row {
        margin-top: 2;
        height: auto;
        align: center middle;
    }
    
    #button-row Button {
        margin: 0 1;
    }
    
    .hidden {
        display: none;
    }
    """
    
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "go_back", "Back", show=True),
        Binding("ctrl+s", "start_scraping", "Start", show=True),
        Binding("ctrl+c", "cancel_scraping", "Cancel", show=True),
    ]

    # Instance attributes
    _scraper: GameScraperService | None
    _scraping_worker: Worker[None] | None
    _is_scraping: bool
    _errors: list[str]
    
    def __init__(self) -> None:
        """Initialize the scraping screen."""
        super().__init__()
        self._scraper = None
        self._scraping_worker = None
        self._is_scraping = False
        self._errors = []
    
    @override
    def compose(self) -> ComposeResult:
        """Compose the scraping screen layout."""
        with Container(id="scraping-container"):
            yield Static("🔍 Scrape Games", id="scraping-title")
            
            # Configuration Section
            yield Static("Configuration", classes="section-title")
            with Vertical(id="config-form"):
                # Target Letters
                with Vertical(classes="form-group"):
                    yield Label("Target Letters:", classes="form-label")
                    yield Input(
                        placeholder="A, B, C (comma-separated)",
                        id="input-letters",
                        classes="form-input",
                    )
                    yield Static(
                        "Letters to scrape (e.g., A, B, C or leave empty for all)",
                        classes="form-hint",
                    )
                
                # Category
                with Vertical(classes="form-group"):
                    yield Label("Category:", classes="form-label")
                    yield Input(
                        value="Xbox",
                        id="input-category",
                        classes="form-input",
                    )
                    yield Static(
                        "Game category to scrape",
                        classes="form-hint",
                    )
            
            # Progress Section
            yield Static("Progress", classes="section-title")
            with Vertical(id="progress-section"):
                yield Static("Ready to start scraping", id="progress-status")
                with Container(id="progress-bar-container"):
                    yield ProgressBar(id="progress-bar", total=100, show_eta=True)
                yield Static("", id="progress-details")
                yield Static("", id="current-game")
            
            # Error Section (hidden by default)
            with Vertical(id="error-section"):
                yield Static("⚠️ Errors", classes="error-title")
                yield Static("", id="error-list", classes="error-list")
            
            # Buttons
            with Horizontal(id="button-row"):
                yield Button("Start Scraping", id="btn-start", variant="primary")
                yield Button("Cancel", id="btn-cancel", variant="error", disabled=True)
                yield Button("Back", id="btn-back", variant="default")

    @override
    async def on_mount(self) -> None:
        """Handle screen mount - load configuration."""
        await super().on_mount()
        await self._load_config()
    
    async def _load_config(self) -> None:
        """Load configuration and populate form."""
        try:
            config_service = self.game_app.config_service
            if config_service:
                config = config_service.load_config()
                self._populate_form(config)
                log.info("Scraping config loaded", letters=config.target_letters)
        except Exception as e:
            log.error("Failed to load config for scraping", error=str(e))
    
    def _populate_form(self, config: AppConfig) -> None:
        """Populate form fields from configuration."""
        letters_input = self.query_one("#input-letters", Input)
        letters_input.value = ", ".join(config.target_letters)
    
    def _get_target_letters(self) -> list[str]:
        """Get target letters from form input."""
        letters_input = self.query_one("#input-letters", Input)
        letters_str = letters_input.value.strip()
        
        if not letters_str:
            # Default to all letters if empty
            return list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        
        # Parse comma-separated letters
        letters = [l.strip().upper() for l in letters_str.split(",") if l.strip()]
        # Filter to valid single letters
        return [l for l in letters if len(l) == 1 and l.isalpha()]
    
    def _get_category(self) -> str:
        """Get category from form input."""
        category_input = self.query_one("#input-category", Input)
        return category_input.value.strip() or "Xbox"
    
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id
        
        if button_id == "btn-start":
            await self._start_scraping()
        elif button_id == "btn-cancel":
            await self._cancel_scraping()
        elif button_id == "btn-back":
            await self.action_go_back()
    
    async def _start_scraping(self) -> None:
        """Start the scraping operation."""
        if self._is_scraping:
            self.notify_warning("Scraping is already in progress")
            return
        
        letters = self._get_target_letters()
        category = self._get_category()
        
        if not letters:
            self.notify_error("Please specify at least one valid letter")
            return
        
        log.info("Starting scraping operation", letters=letters, category=category)
        
        # Update UI state
        self._is_scraping = True
        self._errors.clear()
        self._update_ui_for_scraping(True)
        self._update_progress_display(
            status="Initializing scraping...",
            progress=0,
            details=f"Target: {len(letters)} letters in {category}",
            current_game=""
        )
        
        # Get scraper service from app context or create a new one
        if self.game_app.game_scraper:
            self._scraper = self.game_app.game_scraper
        else:
            # Fallback: create a new scraper if not available from context
            http_client = HttpClientService()
            self._scraper = GameScraperService(http_client, request_delay=2.0)
        
        # Start scraping in a worker
        self._scraping_worker = self.run_worker(
            self._run_scraping(letters, category),
            name="scraping_worker",
            exclusive=True,
        )
    
    async def _run_scraping(self, letters: list[str], category: str) -> None:
        """Run the scraping operation (executed in worker)."""
        if not self._scraper:
            return
        
        games_scraped = 0
        
        try:
            async for game_data in self._scraper.scrape_category(category, letters):
                # Update progress
                progress = self._scraper.get_scraping_progress()
                percentage = (
                    (progress.games_processed / progress.total_games * 100)
                    if progress.total_games > 0 else 0
                )
                
                # Post progress update message
                self.post_message(self.ProgressUpdate(
                    status=f"Scraping letter {progress.current_letter}...",
                    progress=percentage,
                    details=f"Processed: {progress.games_processed}/{progress.total_games} games",
                    current_game=f"Current: {game_data.title}",
                    errors=progress.errors,
                ))
                
                # Post game scraped message
                self.post_message(self.GameScraped(game_data))
                
                games_scraped += 1
            
            # Scraping completed
            final_progress = self._scraper.get_scraping_progress()
            self.post_message(self.ScrapingComplete(
                games_scraped=games_scraped,
                errors=final_progress.errors,
            ))
            
        except asyncio.CancelledError:
            log.info("Scraping worker cancelled")
            raise
        except Exception as e:
            log.error("Scraping failed", error=str(e))
            self.post_message(self.ScrapingError(str(e)))
    
    def on_scraping_screen_progress_update(self, event: ProgressUpdate) -> None:
        """Handle progress update messages."""
        self._update_progress_display(
            status=event.status,
            progress=event.progress,
            details=event.details,
            current_game=event.current_game,
        )
        if event.errors:
            self._update_errors(event.errors)
    
    def on_scraping_screen_game_scraped(self, event: GameScraped) -> None:
        """Handle game scraped messages."""
        try:
            current_games = dict(self.game_app.app_state.games_data)
            current_games[event.game_data.game_url] = event.game_data
            self.game_app.update_games_data(current_games)
        except Exception as e:
            log.error("Failed to store game data", error=str(e))
    
    def on_scraping_screen_scraping_complete(self, event: ScrapingComplete) -> None:
        """Handle scraping completion."""
        self._is_scraping = False
        self._update_ui_for_scraping(False)
        
        error_count = len(event.errors)
        if error_count > 0:
            self._update_progress_display(
                status=f"✓ Completed with {error_count} errors",
                progress=100,
                details=f"Successfully scraped {event.games_scraped} games",
                current_game=""
            )
            self.notify_warning(f"Scraping completed with {error_count} errors")
        else:
            self._update_progress_display(
                status="✓ Scraping completed successfully!",
                progress=100,
                details=f"Scraped {event.games_scraped} games",
                current_game=""
            )
            self.notify_success(f"Successfully scraped {event.games_scraped} games")
        
        log.info("Scraping completed", games_scraped=event.games_scraped, errors=error_count)
    
    def on_scraping_screen_scraping_error(self, event: ScrapingError) -> None:
        """Handle scraping error."""
        self._is_scraping = False
        self._update_ui_for_scraping(False)
        self._update_progress_display(
            status=f"✗ Scraping failed: {event.error}",
            progress=0,
            details="",
            current_game=""
        )
        self.notify_error(f"Scraping failed: {event.error}")
        log.error("Scraping operation failed", error=event.error)
    
    async def _cancel_scraping(self) -> None:
        """Cancel the current scraping operation."""
        if not self._is_scraping:
            return
        
        log.info("Cancelling scraping operation")
        
        if self._scraper:
            self._scraper.cancel_scraping()
        
        if self._scraping_worker:
            self._scraping_worker.cancel()
        
        self._is_scraping = False
        self._update_ui_for_scraping(False)
        self._update_progress_display(
            status="⚠️ Scraping cancelled by user",
            progress=0,
            details="",
            current_game=""
        )
        self.notify_warning("Scraping cancelled")
    
    def _update_ui_for_scraping(self, is_scraping: bool) -> None:
        """Update UI elements based on scraping state."""
        start_btn = self.query_one("#btn-start", Button)
        cancel_btn = self.query_one("#btn-cancel", Button)
        letters_input = self.query_one("#input-letters", Input)
        category_input = self.query_one("#input-category", Input)
        
        start_btn.disabled = is_scraping
        cancel_btn.disabled = not is_scraping
        letters_input.disabled = is_scraping
        category_input.disabled = is_scraping
        
        # Update app state
        self.game_app.set_scraping_active(is_scraping)
    
    def _update_progress_display(
        self,
        status: str,
        progress: float,
        details: str,
        current_game: str
    ) -> None:
        """Update progress display widgets."""
        status_widget = self.query_one("#progress-status", Static)
        progress_bar = self.query_one("#progress-bar", ProgressBar)
        details_widget = self.query_one("#progress-details", Static)
        current_game_widget = self.query_one("#current-game", Static)
        
        status_widget.update(status)
        progress_bar.update(progress=progress)
        details_widget.update(details)
        current_game_widget.update(current_game)
    
    def _update_errors(self, errors: list[str]) -> None:
        """Update error display."""
        self._errors = errors
        error_section = self.query_one("#error-section", Vertical)
        error_list = self.query_one("#error-list", Static)
        
        if errors:
            _ = error_section.add_class("has-errors")
            # Show last 5 errors
            recent_errors = errors[-5:]
            error_text = "\n".join(f"• {e}" for e in recent_errors)
            if len(errors) > 5:
                error_text += f"\n... and {len(errors) - 5} more errors"
            error_list.update(error_text)
        else:
            _ = error_section.remove_class("has-errors")
            error_list.update("")
    
    async def action_start_scraping(self) -> None:
        """Action handler for start scraping keyboard shortcut."""
        await self._start_scraping()
    
    async def action_cancel_scraping(self) -> None:
        """Action handler for cancel scraping keyboard shortcut."""
        await self._cancel_scraping()
    
    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Handle worker state changes."""
        if event.worker.name == "scraping_worker":
            log.debug("Scraping worker state changed", state=event.state)
            
            if event.state == WorkerState.CANCELLED:
                self._is_scraping = False
                self._update_ui_for_scraping(False)
