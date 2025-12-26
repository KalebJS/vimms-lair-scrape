"""Screen components for the TUI application."""

from .base import BaseScreen
from .main_menu import MainMenuScreen
from .scraping import ScrapingScreen
from .settings import SettingsScreen
from .download import DownloadScreen
from .data_view import DataViewScreen

# Screen registry for navigation
_SCREEN_REGISTRY: dict[str, type[BaseScreen]] = {
    "main_menu": MainMenuScreen,
    "scraping": ScrapingScreen,
    "settings": SettingsScreen,
    "downloads": DownloadScreen,
    "data_view": DataViewScreen,
}


def get_screen_by_name(name: str) -> BaseScreen | None:
    """Get a screen instance by its registered name.
    
    Args:
        name: The registered name of the screen
        
    Returns:
        A new instance of the screen, or None if not found
    """
    screen_class = _SCREEN_REGISTRY.get(name)
    if screen_class:
        return screen_class()
    return None


def register_screen(name: str, screen_class: type[BaseScreen]) -> None:
    """Register a screen class with a name for navigation.
    
    Args:
        name: The name to register the screen under
        screen_class: The screen class to register
    """
    _SCREEN_REGISTRY[name] = screen_class


def get_registered_screens() -> list[str]:
    """Get a list of all registered screen names.
    
    Returns:
        List of registered screen names
    """
    return list(_SCREEN_REGISTRY.keys())


__all__ = [
    "BaseScreen",
    "MainMenuScreen",
    "ScrapingScreen",
    "SettingsScreen",
    "DownloadScreen",
    "DataViewScreen",
    "get_screen_by_name",
    "register_screen",
    "get_registered_screens",
]
