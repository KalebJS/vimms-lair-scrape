"""Data models for the TUI Game Scraper application."""

from .config import AppConfig
from .game import DiscInfo, GameData
from .progress import DownloadProgress, ScrapingProgress

__all__ = [
    "AppConfig",
    "DiscInfo", 
    "GameData",
    "DownloadProgress",
    "ScrapingProgress",
]