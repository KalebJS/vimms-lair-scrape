"""Main entry point for the TUI Game Scraper application.

This module provides the application entry point with:
- Command-line argument parsing
- Application initialization and dependency injection
- Graceful shutdown handling
"""

import argparse
import asyncio
import signal
import sys
from pathlib import Path

import structlog

from src.models import AppConfig
from src.services.config import ConfigurationService
from src.services.download_manager import DownloadManagerService
from src.services.filesystem import FileSystemService
from src.services.game_scraper import GameScraperService
from src.services.http_client import HttpClientService
from src.services.logging import setup_logging


log = structlog.stdlib.get_logger()


class ApplicationContext:
    """Container for application services and state.
    
    This class manages the lifecycle of all application services
    and provides dependency injection for the UI components.
    """
    
    def __init__(
        self,
        config_path: Path | None = None,
        log_level: str = "INFO",
        log_dir: Path | None = None,
    ) -> None:
        """Initialize the application context.
        
        Args:
            config_path: Path to configuration file
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            log_dir: Directory for log files (None for console only)
        """
        self._config_path: Path | None = config_path
        self._log_level: str = log_level
        self._log_dir: Path | None = log_dir
        
        # Services (initialized lazily)
        self._config_service: ConfigurationService | None = None
        self._http_client: HttpClientService | None = None
        self._filesystem: FileSystemService | None = None
        self._game_scraper: GameScraperService | None = None
        self._download_manager: DownloadManagerService | None = None
        
        # Configuration
        self._config: AppConfig | None = None
        
        # Shutdown flag
        self._shutdown_requested: bool = False
    
    @property
    def config_service(self) -> ConfigurationService:
        """Get the configuration service (lazy initialization)."""
        if self._config_service is None:
            self._config_service = ConfigurationService(config_path=self._config_path)
        return self._config_service
    
    @property
    def config(self) -> AppConfig:
        """Get the current application configuration."""
        if self._config is None:
            self._config = self.config_service.load_config()
        return self._config
    
    @property
    def http_client(self) -> HttpClientService:
        """Get the HTTP client service (lazy initialization)."""
        if self._http_client is None:
            self._http_client = HttpClientService(
                rate_limit_delay=self.config.request_delay
            )
        return self._http_client
    
    @property
    def filesystem(self) -> FileSystemService:
        """Get the file system service (lazy initialization)."""
        if self._filesystem is None:
            self._filesystem = FileSystemService()
        return self._filesystem
    
    @property
    def game_scraper(self) -> GameScraperService:
        """Get the game scraper service (lazy initialization)."""
        if self._game_scraper is None:
            self._game_scraper = GameScraperService(
                http_client=self.http_client,
                request_delay=self.config.request_delay
            )
        return self._game_scraper
    
    @property
    def download_manager(self) -> DownloadManagerService:
        """Get the download manager service (lazy initialization)."""
        if self._download_manager is None:
            self._download_manager = DownloadManagerService(
                http_client=self.http_client,
                filesystem=self.filesystem,
                download_directory=self.config.download_directory,
                concurrent_downloads=self.config.concurrent_downloads
            )
        return self._download_manager
    
    def request_shutdown(self) -> None:
        """Request graceful shutdown of the application."""
        self._shutdown_requested = True
        log.info("Shutdown requested")
    
    @property
    def shutdown_requested(self) -> bool:
        """Check if shutdown has been requested."""
        return self._shutdown_requested
    
    async def cleanup(self) -> None:
        """Clean up resources and close connections."""
        log.info("Cleaning up application resources")
        
        # Cancel any active downloads
        if self._download_manager is not None:
            self._download_manager.cancel_downloads()
        
        # Cancel any active scraping
        if self._game_scraper is not None:
            self._game_scraper.cancel_scraping()
        
        # Close HTTP client
        if self._http_client is not None:
            await self._http_client.close()
        
        log.info("Application cleanup complete")


class ParsedArgs:
    """Type-safe container for parsed command-line arguments."""
    
    def __init__(
        self,
        config: Path | None,
        log_level: str,
        log_dir: Path | None,
        no_tui: bool,
    ) -> None:
        self.config: Path | None = config
        self.log_level: str = log_level
        self.log_dir: Path | None = log_dir
        self.no_tui: bool = no_tui


def parse_arguments() -> ParsedArgs:
    """Parse command-line arguments.
    
    Returns:
        Parsed arguments container
    """
    parser = argparse.ArgumentParser(
        prog="tui-game-scraper",
        description="A modern textual interface for game scraping and downloading from Vimm's Lair",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  tui-game-scraper                    Start the TUI application
  tui-game-scraper --log-level DEBUG  Start with debug logging
  tui-game-scraper --config ./my-config.json  Use custom config file
        """
    )
    
    _ = parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.1.0"
    )
    
    _ = parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to configuration file (default: ~/.config/tui-game-scraper/config.json)"
    )
    
    _ = parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Set the logging level (default: INFO)"
    )
    
    _ = parser.add_argument(
        "--log-dir",
        type=Path,
        default=None,
        help="Directory for log files (default: ./logs in production, console only in development)"
    )
    
    _ = parser.add_argument(
        "--no-tui",
        action="store_true",
        help="Run without the TUI (for testing or scripting)"
    )
    
    ns = parser.parse_args()
    
    # Extract typed values from namespace
    config_val: Path | None = ns.config
    log_level_val: str = ns.log_level if ns.log_level else "INFO"
    log_dir_val: Path | None = ns.log_dir
    no_tui_val: bool = bool(ns.no_tui)
    
    return ParsedArgs(
        config=config_val,
        log_level=log_level_val,
        log_dir=log_dir_val,
        no_tui=no_tui_val,
    )


def setup_signal_handlers(context: ApplicationContext) -> None:
    """Set up signal handlers for graceful shutdown.
    
    Args:
        context: Application context for shutdown coordination
    """
    def signal_handler(signum: int, frame: object) -> None:
        """Handle shutdown signals."""
        _ = frame  # Unused but required by signal handler signature
        signal_name = signal.Signals(signum).name
        log.info("Received signal", signal=signal_name)
        context.request_shutdown()
    
    # Register signal handlers
    _ = signal.signal(signal.SIGINT, signal_handler)
    _ = signal.signal(signal.SIGTERM, signal_handler)
    
    log.debug("Signal handlers registered")


async def run_tui(context: ApplicationContext) -> int:
    """Run the TUI application.
    
    Args:
        context: Application context with initialized services
        
    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    from src.ui.app import GameScraperApp
    
    log.info("Starting TUI application")
    
    try:
        # Create the application with injected services
        app = GameScraperApp(
            config_service=context.config_service,
            download_manager=context.download_manager,
        )
        
        # Store context in app for access by screens
        app.set_app_context(context)
        
        # Run the application
        await app.run_async()
        
        log.info("TUI application exited normally")
        return 0
        
    except Exception as e:
        log.error("TUI application error", error=str(e), exc_info=True)
        return 1
    finally:
        await context.cleanup()


def main() -> None:
    """Main entry point for the application."""
    # Parse command-line arguments
    args = parse_arguments()
    
    # Determine log directory
    log_dir = args.log_dir
    if log_dir is None and not args.no_tui:
        # Default to ./logs for production
        log_dir = Path("logs")
    
    # Set up logging
    _ = setup_logging(
        log_level=args.log_level,
        log_dir=log_dir
    )
    
    log.info(
        "Starting TUI Game Scraper",
        version="0.1.0",
        log_level=args.log_level,
        config_path=str(args.config) if args.config else "default"
    )
    
    # Create application context
    context = ApplicationContext(
        config_path=args.config,
        log_level=args.log_level,
        log_dir=log_dir
    )
    
    # Set up signal handlers
    setup_signal_handlers(context)
    
    try:
        if args.no_tui:
            # Non-TUI mode for testing/scripting
            log.info("Running in non-TUI mode")
            print("TUI Game Scraper - Non-TUI mode")
            print(f"Configuration loaded from: {context.config_service.config_path}")
            print(f"Download directory: {context.config.download_directory}")
            print("Use --help for available options")
            exit_code = 0
        else:
            # Run the TUI application
            exit_code = asyncio.run(run_tui(context))
        
    except KeyboardInterrupt:
        log.info("Application interrupted by user")
        exit_code = 130  # Standard exit code for SIGINT
        
    except Exception as e:
        log.error("Unhandled exception", error=str(e), exc_info=True)
        print(f"Fatal error: {e}", file=sys.stderr)
        exit_code = 1
    
    log.info("Application exiting", exit_code=exit_code)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
