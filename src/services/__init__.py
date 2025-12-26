"""Service layer for business logic and external integrations."""

from .config import ConfigurationService, ValidationResult
from .download_manager import (
    DownloadManagerService,
    DownloadStatus,
    DownloadTask,
    QueueStatus,
)
from .errors import (
    AppError,
    ConfigurationError,
    DownloadError,
    ErrorCategory,
    ErrorHandlingService,
    ErrorSeverity,
    FileSystemError,
    NetworkError,
    ScrapingError,
    UserFriendlyError,
    ValidationError,
    get_error_service,
    handle_error,
)
from .filesystem import FileSystemService
from .http_client import HttpClientService

__all__ = [
    "AppError",
    "ConfigurationError",
    "ConfigurationService",
    "DownloadError",
    "DownloadManagerService",
    "DownloadStatus",
    "DownloadTask",
    "ErrorCategory",
    "ErrorHandlingService",
    "ErrorSeverity",
    "FileSystemError",
    "FileSystemService",
    "HttpClientService",
    "NetworkError",
    "QueueStatus",
    "ScrapingError",
    "UserFriendlyError",
    "ValidationError",
    "ValidationResult",
    "get_error_service",
    "handle_error",
]