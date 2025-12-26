"""Main menu screen for the TUI application."""

from typing import ClassVar, override

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.widgets import Button, Static

import structlog

from .base import BaseScreen

log = structlog.stdlib.get_logger()


class MainMenuScreen(BaseScreen):
    """Main menu screen providing navigation to all application features.
    
    This screen displays the primary navigation options:
    - Scrape Games: Start a new scraping operation
    - Downloads: Manage and monitor downloads
    - View Data: Browse scraped game data
    - Settings: Configure application settings
    """
    
    SCREEN_TITLE: ClassVar[str] = "Main Menu"
    SCREEN_NAME: ClassVar[str] = "main_menu"
    
    CSS: ClassVar[str] = """
    MainMenuScreen {
        align: center middle;
    }
    
    #menu-container {
        width: 60;
        height: auto;
        padding: 2 4;
        border: solid $primary;
        background: $surface;
    }
    
    #menu-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 2;
    }
    
    #menu-subtitle {
        text-align: center;
        color: $text-muted;
        margin-bottom: 2;
    }
    
    .menu-button {
        width: 100%;
        margin-bottom: 1;
    }
    
    .menu-button:focus {
        background: $primary;
    }
    """
    
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("1", "navigate_scrape", "Scrape", show=False),
        Binding("2", "navigate_downloads", "Downloads", show=False),
        Binding("3", "navigate_data", "View Data", show=False),
        Binding("4", "navigate_settings", "Settings", show=False),
    ]
    
    # Menu options with their navigation targets
    MENU_OPTIONS: ClassVar[list[tuple[str, str, str]]] = [
        ("scrape", "1. Scrape Games", "scraping"),
        ("downloads", "2. Downloads", "downloads"),
        ("data", "3. View Data", "data_view"),
        ("settings", "4. Settings", "settings"),
    ]
    
    @override
    def compose(self) -> ComposeResult:
        """Compose the main menu layout."""
        with Container(id="menu-container"):
            yield Static("🎮 TUI Game Scraper", id="menu-title")
            yield Static("Vimm's Lair Scraper & Downloader", id="menu-subtitle")
            
            with Vertical(id="menu-buttons"):
                for option_id, label, _ in self.MENU_OPTIONS:
                    yield Button(label, id=f"btn-{option_id}", classes="menu-button")
    
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle menu button presses.
        
        Args:
            event: The button pressed event
        """
        button_id = event.button.id
        if not button_id:
            return
        
        # Extract the option from button ID (btn-{option})
        option = button_id.replace("btn-", "")
        
        # Find the target screen for this option
        for opt_id, _, target in self.MENU_OPTIONS:
            if opt_id == option:
                log.info("Menu option selected", option=option, target=target)
                await self._navigate_to(target)
                return
        
        log.warning("Unknown menu option", button_id=button_id)
    
    async def _navigate_to(self, screen_name: str) -> None:
        """Navigate to a screen by name.
        
        Args:
            screen_name: The name of the screen to navigate to
        """
        try:
            await self.game_app.push_screen_with_tracking(screen_name)
        except Exception as e:
            log.error("Navigation failed", target=screen_name, error=str(e))
            self.notify_error(f"Cannot navigate to {screen_name}: Screen not implemented yet")
    
    async def action_navigate_scrape(self) -> None:
        """Navigate to the scraping screen."""
        await self._navigate_to("scraping")
    
    async def action_navigate_downloads(self) -> None:
        """Navigate to the downloads screen."""
        await self._navigate_to("downloads")
    
    async def action_navigate_data(self) -> None:
        """Navigate to the data view screen."""
        await self._navigate_to("data_view")
    
    async def action_navigate_settings(self) -> None:
        """Navigate to the settings screen."""
        await self._navigate_to("settings")
    
    @override
    async def action_go_back(self) -> None:
        """Override back action to quit from main menu."""
        # From main menu, back should quit the application
        log.info("Quit requested from main menu")
        self.game_app.exit()
