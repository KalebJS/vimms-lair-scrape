"""Game-related data models."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class DiscInfo:
    """Information about a game disc/file."""
    disc_number: str
    media_id: str
    download_url: str
    file_size: int | None = None


@dataclass(frozen=True)
class GameData:
    """Core game data structure."""
    title: str
    game_url: str
    category: str
    discs: list[DiscInfo]
    scraped_at: datetime
    rating: float | None = None  # 0-100 scale, None if not available
    rating_count: int | None = None  # Number of ratings/votes