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
from .esde_compat import ESDECompatibilityService, SystemMapping, VIMM_TO_ESDE_MAPPING
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
    "ESDECompatibilityService",
    "FileSystemError",
    "FileSystemService",
    "HttpClientService",
    "NetworkError",
    "QueueStatus",
    "ScrapingError",
    "SystemMapping",
    "UserFriendlyError",
    "ValidationError",
    "ValidationResult",
    "VIMM_TO_ESDE_MAPPING",
    "get_error_service",
    "handle_error",
]