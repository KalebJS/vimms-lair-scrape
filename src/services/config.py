"""Configuration service for managing application settings."""

import json
from pathlib import Path

import structlog

from ..models import AppConfig
from .errors import ConfigurationError, ValidationError as AppValidationError, get_error_service

log = structlog.stdlib.get_logger()


class ValidationResult:
    """Result of configuration validation."""
    
    def __init__(self, is_valid: bool, errors: list[str] | None = None) -> None:
        self.is_valid: bool = is_valid
        self.errors: list[str] = errors or []


class ConfigurationService:
    """Service for managing application configuration."""
    
    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path: Path = config_path or Path.home() / ".config" / "tui-game-scraper" / "config.json"
        log.info("Configuration service initialized", config_path=str(self.config_path))
    
    def load_config(self) -> AppConfig:
        """Load configuration from file or return default configuration."""
        if not self.config_path.exists():
            log.info("Configuration file not found, using defaults")
            return self._get_default_config()
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data: dict[str, str | int | float | list[str] | bool | None] = json.load(f)
            
            config = self._dict_to_config(data)
            validation_result = self.validate_config(config)
            
            if not validation_result.is_valid:
                log.warning("Invalid configuration loaded, using defaults", errors=validation_result.errors)
                return self._get_default_config()
            
            log.info("Configuration loaded successfully")
            return config
            
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            log.error("Failed to load configuration, using defaults", error=str(e))
            return self._get_default_config()
    
    def save_config(self, config: AppConfig) -> None:
        """Save configuration to file."""
        validation_result = self.validate_config(config)
        if not validation_result.is_valid:
            raise ValueError(f"Invalid configuration: {', '.join(validation_result.errors)}")
        
        # Ensure directory exists
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            data = self._config_to_dict(config)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            log.info("Configuration saved successfully")
            
        except (OSError, IOError) as e:
            log.error("Failed to save configuration", error=str(e))
            raise
    
    def validate_config(self, config: AppConfig) -> ValidationResult:
        """Validate configuration settings."""
        errors = []
        
        # Validate target_letters
        if not config.target_letters:
            errors.append("target_letters cannot be empty")
        elif not all(isinstance(letter, str) and len(letter) == 1 and letter.isalpha() 
                    for letter in config.target_letters):
            errors.append("target_letters must contain single alphabetic characters")
        
        # Validate download_directory
        if not isinstance(config.download_directory, Path):
            errors.append("download_directory must be a Path object")
        elif not config.download_directory.is_absolute():
            errors.append("download_directory must be an absolute path")
        
        # Validate concurrent_downloads
        if not isinstance(config.concurrent_downloads, int) or config.concurrent_downloads < 1:
            errors.append("concurrent_downloads must be a positive integer")
        elif config.concurrent_downloads > 10:
            errors.append("concurrent_downloads should not exceed 10")
        
        # Validate request_delay
        if not isinstance(config.request_delay, (int, float)) or config.request_delay < 0:
            errors.append("request_delay must be a non-negative number")
        elif config.request_delay > 60:
            errors.append("request_delay should not exceed 60 seconds")
        
        # Validate log_level
        valid_log_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if config.log_level not in valid_log_levels:
            errors.append(f"log_level must be one of: {', '.join(valid_log_levels)}")
        
        # Validate minimum_score
        if config.minimum_score is not None:
            if not isinstance(config.minimum_score, (int, float)):
                errors.append("minimum_score must be a number or None")
            elif config.minimum_score < 0 or config.minimum_score > 100:
                errors.append("minimum_score must be between 0 and 100")
        
        # Validate concurrent_scrapes
        if not isinstance(config.concurrent_scrapes, int) or config.concurrent_scrapes < 1:
            errors.append("concurrent_scrapes must be a positive integer")
        elif config.concurrent_scrapes > 10:
            errors.append("concurrent_scrapes should not exceed 10")
        
        return ValidationResult(len(errors) == 0, errors)
    
    def _get_default_config(self) -> AppConfig:
        """Get default configuration."""
        return AppConfig(
            target_letters=["A"],
            download_directory=Path.home() / "Downloads" / "games",
            concurrent_downloads=1,
            request_delay=2.0,
            log_level="INFO",
            concurrent_scrapes=3,
            auto_queue_downloads=True,
        )
    
    def _config_to_dict(self, config: AppConfig) -> dict[str, str | int | float | list[str] | bool | None]:
        """Convert AppConfig to dictionary for JSON serialization."""
        return {
            "target_letters": config.target_letters,
            "download_directory": str(config.download_directory),
            "concurrent_downloads": config.concurrent_downloads,
            "request_delay": config.request_delay,
            "log_level": config.log_level,
            "minimum_score": config.minimum_score,
            "concurrent_scrapes": config.concurrent_scrapes,
            "auto_queue_downloads": config.auto_queue_downloads,
        }
    
    def _dict_to_config(self, data: dict[str, str | int | float | list[str] | bool | None]) -> AppConfig:
        """Convert dictionary to AppConfig."""
        # Parse minimum_score - can be None, int, or float
        min_score_raw = data.get("minimum_score")
        minimum_score: float | None = None
        if min_score_raw is not None and min_score_raw != "":
            try:
                minimum_score = float(min_score_raw)
            except (ValueError, TypeError):
                minimum_score = None
        
        # Parse concurrent_scrapes with default fallback
        concurrent_scrapes_raw = data.get("concurrent_scrapes", 3)
        concurrent_scrapes = int(concurrent_scrapes_raw) if isinstance(concurrent_scrapes_raw, (int, float)) else 3
        
        # Parse auto_queue_downloads with default fallback (True for backwards compatibility)
        auto_queue_raw = data.get("auto_queue_downloads", True)
        auto_queue_downloads = bool(auto_queue_raw) if isinstance(auto_queue_raw, bool) else True
        
        return AppConfig(
            target_letters=data["target_letters"] if isinstance(data["target_letters"], list) else [],
            download_directory=Path(str(data["download_directory"])),
            concurrent_downloads=int(data["concurrent_downloads"]) if isinstance(data["concurrent_downloads"], (int, float)) else 1,
            request_delay=float(data["request_delay"]) if isinstance(data["request_delay"], (int, float)) else 2.0,
            log_level=str(data["log_level"]) if isinstance(data["log_level"], str) else "INFO",
            minimum_score=minimum_score,
            concurrent_scrapes=concurrent_scrapes,
            auto_queue_downloads=auto_queue_downloads,
        )