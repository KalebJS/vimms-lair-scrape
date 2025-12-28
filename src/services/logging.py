"""Logging configuration service for the TUI Game Scraper application."""

import logging
import logging.handlers
import os
import sys
from pathlib import Path
from typing import Any

import structlog


class LoggingService:
    """Service for configuring and managing application logging."""
    
    def __init__(
        self, 
        log_level: str = "INFO", 
        log_dir: Path | None = None,
        tui_mode: bool = False,
    ) -> None:
        """Initialize the logging service.
        
        Args:
            log_level: The minimum log level to capture
            log_dir: Directory for log files (None for console only)
            tui_mode: If True, disable console logging to avoid corrupting TUI
        """
        self.log_level = log_level.upper()
        self.log_dir = log_dir
        self.tui_mode = tui_mode
        self.is_development = os.getenv("ENVIRONMENT", "development") == "development"
        
    def configure(self) -> None:
        """Configure structlog with appropriate processors and handlers."""
        # Configure standard library logging first
        self._configure_stdlib_logging()
        
        # Configure structlog processors
        processors = self._get_processors()
        
        structlog.configure(
            processors=processors,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        
    def _configure_stdlib_logging(self) -> None:
        """Configure standard library logging handlers."""
        # Clear any existing handlers
        root_logger = logging.getLogger()
        root_logger.handlers.clear()
        
        # Set log level
        numeric_level = getattr(logging, self.log_level, logging.INFO)
        root_logger.setLevel(numeric_level)
        
        # Console handler (only when NOT in TUI mode)
        if not self.tui_mode:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(numeric_level)
            
            if self.is_development:
                # Development: use simple format for console
                console_formatter = logging.Formatter(
                    fmt="%(asctime)s [%(levelname)8s] %(name)s: %(message)s",
                    datefmt="%H:%M:%S"
                )
            else:
                # Production: use JSON format for console
                console_formatter = logging.Formatter("%(message)s")
                
            console_handler.setFormatter(console_formatter)
            root_logger.addHandler(console_handler)
        
        # File handler (if log directory specified)
        if self.log_dir:
            self._setup_file_logging(root_logger, numeric_level)
            
    def _setup_file_logging(self, root_logger: logging.Logger, level: int) -> None:
        """Set up file-based logging with rotation."""
        if not self.log_dir:
            return
            
        # Ensure log directory exists
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Main application log with rotation
        app_log_path = self.log_dir / "app.log"
        file_handler = logging.handlers.RotatingFileHandler(
            filename=app_log_path,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8"
        )
        file_handler.setLevel(level)
        
        # Always use JSON format for file logs
        file_formatter = logging.Formatter("%(message)s")
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
        
        # Error log (ERROR and CRITICAL only)
        error_log_path = self.log_dir / "error.log"
        error_handler = logging.handlers.RotatingFileHandler(
            filename=error_log_path,
            maxBytes=5 * 1024 * 1024,  # 5MB
            backupCount=3,
            encoding="utf-8"
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(file_formatter)
        root_logger.addHandler(error_handler)
        
    def _get_processors(self) -> list[Any]:
        """Get the appropriate structlog processors for the environment."""
        # Common processors for all environments
        common_processors = [
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
        ]
        
        if self.is_development and not self.log_dir:
            # Development console only: use console renderer for better readability
            return common_processors + [
                structlog.dev.ConsoleRenderer(colors=True)
            ]
        elif self.is_development and self.log_dir:
            # Development with file logging: use JSON for files, console for stdout
            return common_processors + [
                structlog.processors.JSONRenderer()
            ]
        else:
            # Production: use JSON renderer for structured logging
            return common_processors + [
                structlog.processors.JSONRenderer()
            ]
            
    def get_logger(self, name: str | None = None) -> structlog.stdlib.BoundLogger:
        """Get a configured logger instance.
        
        Args:
            name: Logger name (defaults to calling module)
            
        Returns:
            Configured structlog logger
        """
        return structlog.stdlib.get_logger(name)


def setup_logging(
    log_level: str = "INFO", 
    log_dir: Path | None = None,
    environment: str | None = None,
    tui_mode: bool = False,
) -> LoggingService:
    """Set up application logging with the specified configuration.
    
    Args:
        log_level: Minimum log level to capture
        log_dir: Directory for log files (None for console only)
        environment: Environment name (development/production)
        tui_mode: If True, disable console logging to avoid corrupting TUI
        
    Returns:
        Configured LoggingService instance
    """
    if environment:
        os.environ["ENVIRONMENT"] = environment
        
    service = LoggingService(log_level=log_level, log_dir=log_dir, tui_mode=tui_mode)
    service.configure()
    return service