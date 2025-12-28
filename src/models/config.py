"""Configuration data models."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    """Application configuration settings."""
    target_letters: list[str]
    download_directory: Path
    concurrent_downloads: int  # Legacy - kept for backwards compatibility
    request_delay: float
    log_level: str
    minimum_score: float | None = None  # 0-100 scale, None = no filtering
    concurrent_scrapes: int = 3  # Concurrent metadata scraping requests
    auto_queue_downloads: bool = True  # Auto-add scraped games to download queue