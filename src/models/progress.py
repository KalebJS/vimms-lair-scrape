"""Progress tracking data models."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ScrapingProgress:
    """Progress information for scraping operations."""
    current_letter: str
    current_game: str
    games_processed: int
    total_games: int
    errors: list[str]
    games_skipped: int = 0  # Games skipped due to low score


@dataclass(frozen=True)
class DownloadProgress:
    """Progress information for download operations."""
    current_file: str
    bytes_downloaded: int
    total_bytes: int
    download_speed: float
    eta_seconds: int