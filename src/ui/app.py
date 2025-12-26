"""Main Textual application with screen management and reactive state."""

from dataclasses import dataclass, field
from typing import Any, ClassVar, override

from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.reactive import reactive
from textual.widgets import Footer, Header

import structlog

from src.models.config import AppConfig
from src.models.game import GameData
from src.services.config import ConfigurationService
from src.services.download_manager import DownloadManagerService, DownloadTask
from src.services.game_scraper import GameScraperService


log = structlog.stdlib.get_logger()


@dataclass
class AppState:
    """Application state container for reactive state management."""
    
    games_data: dict[str, GameData] = field(default_factory=dict)
    scraping_active: bool = False
    download_queue: list[DownloadTask] = field(default_factory=list)
    current_config: AppConfig | None = None


class GameScraperApp(App[None]):
    """Main TUI application for game scraping and downloading.
    
    This is the root Textual application that manages screens, global state,
    and coordinates between different application components.
    """
    
    CSS: ClassVar[str] = """
    Screen {
        background: $surface;
    }
    
    #main-content {
        width: 100%;
        height: 100%;
        padding: 1 2;
    }
    
    .title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    """
    
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("q", "quit", "Quit", show=True, priority=True),
        Binding("escape", "go_back", "Back", show=True),
        Binding("?", "show_help", "Help", show=True),
    ]
    
    # Reactive state
    app_state: reactive[AppState] = reactive(AppState, init=False)
    
    # Instance attributes with type annotations
    _config_service: ConfigurationService | None
    _download_manager: DownloadManagerService | None
    _navigation_stack: list[str]
    _app_context: Any  # ApplicationContext from src.main (avoid circular import)
    
    def __init__(
        self,
        config_service: ConfigurationService | None = None,
        download_manager: DownloadManagerService | None = None,
    ) -> None:
        """Initialize the application with optional service injection.
        
        Args:
            config_service: Configuration service for loading/saving settings
            download_manager: Download manager service for file downloads
        """
        super().__init__()
        self.title = "TUI Game Scraper"  # type: ignore[assignment]
        self.sub_title = "Vimm's Lair Scraper & Downloader"  # type: ignore[assignment]
        self._config_service = config_service
        self._download_manager = download_manager
        self._navigation_stack = []
        self._app_context = None
        self.app_state = AppState()
        
        log.info("GameScraperApp initialized")
    
    @property
    def app_context(self) -> Any:
        """Get the application context."""
        return self._app_context
    
    def set_app_context(self, context: Any) -> None:
        """Set the application context.
        
        Args:
            context: The application context to set
        """
        self._app_context = context
    
    @property
    def config_service(self) -> ConfigurationService | None:
        """Get the configuration service."""
        return self._config_service
    
    @property
    def download_manager(self) -> DownloadManagerService | None:
        """Get the download manager service."""
        return self._download_manager
    
    @property
    def game_scraper(self) -> GameScraperService | None:
        """Get the game scraper service from the application context.
        
        Returns:
            GameScraperService if available through context, None otherwise
        """
        if self._app_context is not None:
            return self._app_context.game_scraper
        return None
    
    @property
    def navigation_stack(self) -> list[str]:
        """Get the current navigation stack."""
        return self._navigation_stack.copy()
    
    @override
    def compose(self) -> ComposeResult:
        """Compose the application layout."""
        yield Header()
        yield Footer()
    
    async def on_mount(self) -> None:
        """Handle application mount event."""
        log.info("Application mounted, loading configuration")
        
        # Load configuration if service is available
        if self._config_service:
            try:
                config = self._config_service.load_config()
                self.app_state = AppState(current_config=config)
                log.info("Configuration loaded successfully")
            except Exception as e:
                log.error("Failed to load configuration", error=str(e))
        
        # Push the main menu screen
        await self.push_screen_with_tracking("main_menu")
    
    async def push_screen_with_tracking(self, screen_name: str) -> None:
        """Push a screen and track it in the navigation stack.
        
        Args:
            screen_name: Name of the screen to push
        """
        # Lazy import to avoid circular dependency
        from src.ui.screens import get_screen_by_name
        
        screen = get_screen_by_name(screen_name)
        if screen:
            self._navigation_stack.append(screen_name)
            await self.push_screen(screen)
            log.info("Screen pushed", screen=screen_name, stack_depth=len(self._navigation_stack))
        else:
            log.warning("Unknown screen requested", screen=screen_name)
    
    async def action_go_back(self) -> None:
        """Navigate back to the previous screen."""
        if len(self._navigation_stack) > 1:
            # Pop current screen from stack
            current = self._navigation_stack.pop()
            log.info("Navigating back", from_screen=current, stack_depth=len(self._navigation_stack))
            
            # Pop the screen from Textual's screen stack
            _ = self.pop_screen()
        else:
            log.debug("Already at root screen, cannot go back")
    
    async def action_show_help(self) -> None:
        """Show help information."""
        log.info("Help requested")
        # Help screen will be implemented in later tasks
        self.notify("Help: Press 'q' to quit, 'escape' to go back")
    
    def update_games_data(self, games: dict[str, GameData]) -> None:
        """Update the games data in application state.
        
        Args:
            games: Dictionary of game data keyed by game URL
        """
        new_state = AppState(
            games_data=games,
            scraping_active=self.app_state.scraping_active,
            download_queue=self.app_state.download_queue,
            current_config=self.app_state.current_config,
        )
        self.app_state = new_state
        log.info("Games data updated", game_count=len(games))
    
    def set_scraping_active(self, active: bool) -> None:
        """Set the scraping active state.
        
        Args:
            active: Whether scraping is currently active
        """
        new_state = AppState(
            games_data=self.app_state.games_data,
            scraping_active=active,
            download_queue=self.app_state.download_queue,
            current_config=self.app_state.current_config,
        )
        self.app_state = new_state
        log.info("Scraping state changed", active=active)
    
    def update_download_queue(self, queue: list[DownloadTask]) -> None:
        """Update the download queue in application state.
        
        Args:
            queue: List of download tasks
        """
        new_state = AppState(
            games_data=self.app_state.games_data,
            scraping_active=self.app_state.scraping_active,
            download_queue=queue,
            current_config=self.app_state.current_config,
        )
        self.app_state = new_state
        log.info("Download queue updated", queue_size=len(queue))
