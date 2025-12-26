"""Configuration data models."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    """Application configuration settings."""
    target_letters: list[str]
    download_directory: Path
    concurrent_downloads: int
    request_delay: float
    log_level: str