"""User interface components using Textual framework."""

from .app import AppState, GameScraperApp
from .screens import (
    BaseScreen,
    MainMenuScreen,
    get_registered_screens,
    get_screen_by_name,
    register_screen,
)

__all__ = [
    "AppState",
    "BaseScreen",
    "GameScraperApp",
    "MainMenuScreen",
    "get_registered_screens",
    "get_screen_by_name",
    "register_screen",
]