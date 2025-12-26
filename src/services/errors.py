"""Comprehensive error handling module for the TUI Game Scraper application.

This module provides:
- Custom exception classes for different error types (network, file system, validation)
- User-friendly error message generation with suggested actions
- Error recovery mechanisms
- Centralized error handling service

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any

import structlog

log = structlog.stdlib.get_logger()


class ErrorCategory(Enum):
    """Categories of errors for classification and handling."""
    NETWORK = "network"
    FILE_SYSTEM = "file_system"
    VALIDATION = "validation"
    CONFIGURATION = "configuration"
    SCRAPING = "scraping"
    DOWNLOAD = "download"
    UNEXPECTED = "unexpected"


class ErrorSeverity(Enum):
    """Severity levels for errors."""
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(frozen=True)
class ErrorContext:
    """Context information for an error."""
    operation: str
    component: str
    details: dict[str, Any]


@dataclass(frozen=True)
class UserFriendlyError:
    """User-friendly error representation with suggested actions."""
    message: str
    category: ErrorCategory
    severity: ErrorSeverity
    suggested_actions: list[str]
    technical_details: str | None = None
    recoverable: bool = True


class AppError(Exception):
    """Base exception class for application errors."""
    
    def __init__(
        self,
        message: str,
        category: ErrorCategory = ErrorCategory.UNEXPECTED,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        suggested_actions: list[str] | None = None,
        technical_details: str | None = None,
        recoverable: bool = True,
        context: ErrorContext | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.category = category
        self.severity = severity
        self.suggested_actions = suggested_actions or []
        self.technical_details = technical_details
        self.recoverable = recoverable
        self.context = context
    
    def to_user_friendly(self) -> UserFriendlyError:
        """Convert to user-friendly error representation."""
        return UserFriendlyError(
            message=self.message,
            category=self.category,
            severity=self.severity,
            suggested_actions=self.suggested_actions,
            technical_details=self.technical_details,
            recoverable=self.recoverable,
        )


class NetworkError(AppError):
    """Exception for network-related errors."""
    
    def __init__(
        self,
        message: str,
        original_error: Exception | None = None,
        url: str | None = None,
        status_code: int | None = None,
    ) -> None:
        suggested_actions = [
            "Check your internet connection",
            "Verify the URL is correct",
            "Try again in a few moments",
        ]
        
        if status_code:
            if status_code == 429:
                suggested_actions = [
                    "Wait a few minutes before retrying",
                    "Reduce the request frequency in settings",
                ]
            elif status_code == 404:
                suggested_actions = [
                    "The requested resource may no longer exist",
                    "Check if the URL is correct",
                ]
            elif status_code >= 500:
                suggested_actions = [
                    "The server is experiencing issues",
                    "Try again later",
                ]
        
        technical_details = None
        if original_error:
            technical_details = f"{type(original_error).__name__}: {str(original_error)}"
        if url:
            technical_details = f"URL: {url}" + (f"\n{technical_details}" if technical_details else "")
        if status_code:
            technical_details = f"Status: {status_code}" + (f"\n{technical_details}" if technical_details else "")
        
        super().__init__(
            message=message,
            category=ErrorCategory.NETWORK,
            severity=ErrorSeverity.ERROR,
            suggested_actions=suggested_actions,
            technical_details=technical_details,
            recoverable=True,
        )
        self.original_error = original_error
        self.url = url
        self.status_code = status_code


class FileSystemError(AppError):
    """Exception for file system-related errors."""
    
    def __init__(
        self,
        message: str,
        original_error: Exception | None = None,
        path: str | None = None,
        operation: str | None = None,
    ) -> None:
        suggested_actions = self._get_suggested_actions(original_error, operation)
        
        technical_details = None
        if original_error:
            technical_details = f"{type(original_error).__name__}: {str(original_error)}"
        if path:
            technical_details = f"Path: {path}" + (f"\n{technical_details}" if technical_details else "")
        
        super().__init__(
            message=message,
            category=ErrorCategory.FILE_SYSTEM,
            severity=ErrorSeverity.ERROR,
            suggested_actions=suggested_actions,
            technical_details=technical_details,
            recoverable=True,
        )
        self.original_error = original_error
        self.path = path
        self.operation = operation
    
    @staticmethod
    def _get_suggested_actions(
        original_error: Exception | None,
        operation: str | None,
    ) -> list[str]:
        """Get suggested actions based on error type."""
        if isinstance(original_error, PermissionError):
            return [
                "Check file/directory permissions",
                "Try running with appropriate permissions",
                "Choose a different location",
            ]
        elif isinstance(original_error, FileNotFoundError):
            return [
                "Verify the file path is correct",
                "Check if the file was moved or deleted",
                "Create the file or directory first",
            ]
        elif isinstance(original_error, OSError):
            error_str = str(original_error).lower()
            if "no space" in error_str or "disk full" in error_str:
                return [
                    "Free up disk space",
                    "Choose a different download location",
                    "Delete unnecessary files",
                ]
            elif "read-only" in error_str:
                return [
                    "The file system is read-only",
                    "Choose a different location",
                ]
        
        # Default suggestions
        return [
            "Check the file path and permissions",
            "Ensure sufficient disk space",
            "Try a different location",
        ]


class ValidationError(AppError):
    """Exception for validation-related errors."""
    
    def __init__(
        self,
        message: str,
        field: str | None = None,
        value: Any = None,
        constraints: list[str] | None = None,
    ) -> None:
        suggested_actions = ["Review the input requirements"]
        if constraints:
            suggested_actions.extend([f"Ensure: {c}" for c in constraints])
        
        technical_details = None
        if field:
            technical_details = f"Field: {field}"
        if value is not None:
            value_str = str(value)[:100]  # Truncate long values
            technical_details = (technical_details or "") + f"\nValue: {value_str}"
        
        super().__init__(
            message=message,
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.WARNING,
            suggested_actions=suggested_actions,
            technical_details=technical_details,
            recoverable=True,
        )
        self.field = field
        self.value = value
        self.constraints = constraints or []


class ConfigurationError(AppError):
    """Exception for configuration-related errors."""
    
    def __init__(
        self,
        message: str,
        setting: str | None = None,
        current_value: Any = None,
        expected: str | None = None,
    ) -> None:
        suggested_actions = [
            "Check the configuration settings",
            "Reset to default values if needed",
        ]
        if expected:
            suggested_actions.append(f"Expected: {expected}")
        
        technical_details = None
        if setting:
            technical_details = f"Setting: {setting}"
        if current_value is not None:
            technical_details = (technical_details or "") + f"\nCurrent: {current_value}"
        
        super().__init__(
            message=message,
            category=ErrorCategory.CONFIGURATION,
            severity=ErrorSeverity.ERROR,
            suggested_actions=suggested_actions,
            technical_details=technical_details,
            recoverable=True,
        )
        self.setting = setting
        self.current_value = current_value
        self.expected = expected


class ScrapingError(AppError):
    """Exception for scraping-related errors."""
    
    def __init__(
        self,
        message: str,
        game_title: str | None = None,
        url: str | None = None,
        original_error: Exception | None = None,
    ) -> None:
        suggested_actions = [
            "The page structure may have changed",
            "Try scraping again later",
            "Check if the game page is accessible",
        ]
        
        technical_details = None
        if game_title:
            technical_details = f"Game: {game_title}"
        if url:
            technical_details = (technical_details or "") + f"\nURL: {url}"
        if original_error:
            technical_details = (technical_details or "") + f"\nError: {type(original_error).__name__}: {str(original_error)}"
        
        super().__init__(
            message=message,
            category=ErrorCategory.SCRAPING,
            severity=ErrorSeverity.WARNING,
            suggested_actions=suggested_actions,
            technical_details=technical_details,
            recoverable=True,
        )
        self.game_title = game_title
        self.url = url
        self.original_error = original_error


class DownloadError(AppError):
    """Exception for download-related errors."""
    
    def __init__(
        self,
        message: str,
        file_name: str | None = None,
        url: str | None = None,
        bytes_downloaded: int = 0,
        total_bytes: int = 0,
        original_error: Exception | None = None,
    ) -> None:
        suggested_actions = [
            "Check your internet connection",
            "Verify sufficient disk space",
            "Try resuming the download",
        ]
        
        technical_details = None
        if file_name:
            technical_details = f"File: {file_name}"
        if url:
            technical_details = (technical_details or "") + f"\nURL: {url}"
        if total_bytes > 0:
            progress = (bytes_downloaded / total_bytes) * 100
            technical_details = (technical_details or "") + f"\nProgress: {progress:.1f}%"
        if original_error:
            technical_details = (technical_details or "") + f"\nError: {type(original_error).__name__}: {str(original_error)}"
        
        super().__init__(
            message=message,
            category=ErrorCategory.DOWNLOAD,
            severity=ErrorSeverity.ERROR,
            suggested_actions=suggested_actions,
            technical_details=technical_details,
            recoverable=True,
        )
        self.file_name = file_name
        self.url = url
        self.bytes_downloaded = bytes_downloaded
        self.total_bytes = total_bytes
        self.original_error = original_error



@dataclass
class RecoveryState:
    """State information for error recovery."""
    operation: str
    component: str
    state_data: dict[str, Any]
    timestamp: float
    error: AppError | None = None


class ErrorHandlingService:
    """Centralized error handling service with recovery mechanisms.
    
    This service provides:
    - Error classification and user-friendly message generation
    - Error logging with technical details
    - State preservation for recovery
    - Recovery action suggestions
    
    Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
    """
    
    def __init__(self) -> None:
        """Initialize the error handling service."""
        self._recovery_states: dict[str, RecoveryState] = {}
        self._error_history: list[tuple[float, AppError]] = []
        self._max_history_size = 100
        log.info("Error handling service initialized")
    
    def handle_error(
        self,
        error: Exception,
        operation: str,
        component: str,
        context: dict[str, Any] | None = None,
    ) -> UserFriendlyError:
        """Handle an error and return a user-friendly representation.
        
        Args:
            error: The exception that occurred
            operation: The operation being performed
            component: The component where the error occurred
            context: Additional context information
            
        Returns:
            User-friendly error representation
        """
        import time
        
        # Convert to AppError if needed
        app_error = self._convert_to_app_error(error, operation, component, context)
        
        # Log the error with full technical details
        self._log_error(app_error, operation, component, context)
        
        # Store in history
        self._error_history.append((time.time(), app_error))
        if len(self._error_history) > self._max_history_size:
            self._error_history.pop(0)
        
        return app_error.to_user_friendly()
    
    def _convert_to_app_error(
        self,
        error: Exception,
        operation: str,
        component: str,
        context: dict[str, Any] | None,
    ) -> AppError:
        """Convert a standard exception to an AppError."""
        import httpx
        
        # Already an AppError
        if isinstance(error, AppError):
            return error
        
        # Network errors
        if isinstance(error, httpx.ConnectError):
            return NetworkError(
                message="Unable to connect to the server. Please check your internet connection.",
                original_error=error,
                url=context.get("url") if context else None,
            )
        elif isinstance(error, httpx.TimeoutException):
            return NetworkError(
                message="The request timed out. The server may be slow or unavailable.",
                original_error=error,
                url=context.get("url") if context else None,
            )
        elif isinstance(error, httpx.HTTPStatusError):
            status_code = error.response.status_code
            message = self._get_http_error_message(status_code)
            return NetworkError(
                message=message,
                original_error=error,
                url=str(error.request.url) if error.request else None,
                status_code=status_code,
            )
        elif isinstance(error, httpx.RequestError):
            return NetworkError(
                message="A network error occurred. Please check your connection.",
                original_error=error,
                url=context.get("url") if context else None,
            )
        
        # File system errors
        elif isinstance(error, PermissionError):
            return FileSystemError(
                message="Permission denied. You don't have access to this file or directory.",
                original_error=error,
                path=context.get("path") if context else None,
                operation=operation,
            )
        elif isinstance(error, FileNotFoundError):
            return FileSystemError(
                message="The file or directory was not found.",
                original_error=error,
                path=context.get("path") if context else None,
                operation=operation,
            )
        elif isinstance(error, OSError):
            return FileSystemError(
                message=f"A file system error occurred: {str(error)}",
                original_error=error,
                path=context.get("path") if context else None,
                operation=operation,
            )
        
        # Validation errors
        elif isinstance(error, ValueError):
            return ValidationError(
                message=str(error),
                field=context.get("field") if context else None,
                value=context.get("value") if context else None,
            )
        elif isinstance(error, TypeError):
            return ValidationError(
                message=f"Invalid data type: {str(error)}",
                field=context.get("field") if context else None,
            )
        
        # JSON errors
        elif isinstance(error, (json.JSONDecodeError if 'json' in dir() else type(None))):
            return ValidationError(
                message="Invalid JSON format. The data could not be parsed.",
                field="json_content",
            )
        
        # Default: unexpected error
        return AppError(
            message="An unexpected error occurred. Please try again.",
            category=ErrorCategory.UNEXPECTED,
            severity=ErrorSeverity.ERROR,
            technical_details=f"{type(error).__name__}: {str(error)}",
            recoverable=True,
            context=ErrorContext(
                operation=operation,
                component=component,
                details=context or {},
            ),
        )
    
    @staticmethod
    def _get_http_error_message(status_code: int) -> str:
        """Get a user-friendly message for HTTP status codes."""
        messages = {
            400: "The request was invalid. Please check your input.",
            401: "Authentication required. Please check your credentials.",
            403: "Access denied. You don't have permission to access this resource.",
            404: "The requested resource was not found.",
            408: "The request timed out. Please try again.",
            429: "Too many requests. Please wait before trying again.",
            500: "The server encountered an error. Please try again later.",
            502: "The server is temporarily unavailable. Please try again later.",
            503: "The service is temporarily unavailable. Please try again later.",
            504: "The server took too long to respond. Please try again.",
        }
        return messages.get(status_code, f"HTTP error {status_code} occurred.")
    
    def _log_error(
        self,
        error: AppError,
        operation: str,
        component: str,
        context: dict[str, Any] | None,
    ) -> None:
        """Log error with full technical details."""
        log_method = log.error if error.severity == ErrorSeverity.ERROR else log.warning
        
        log_method(
            "Error occurred",
            error_message=error.message,
            category=error.category.value,
            severity=error.severity.value,
            operation=operation,
            component=component,
            technical_details=error.technical_details,
            recoverable=error.recoverable,
            context=context,
        )
    
    def save_recovery_state(
        self,
        key: str,
        operation: str,
        component: str,
        state_data: dict[str, Any],
    ) -> None:
        """Save state for potential recovery.
        
        Args:
            key: Unique key for this recovery state
            operation: The operation being performed
            component: The component saving state
            state_data: State data to preserve
        """
        import time
        
        self._recovery_states[key] = RecoveryState(
            operation=operation,
            component=component,
            state_data=state_data,
            timestamp=time.time(),
        )
        log.debug(
            "Recovery state saved",
            key=key,
            operation=operation,
            component=component,
        )
    
    def get_recovery_state(self, key: str) -> RecoveryState | None:
        """Get saved recovery state.
        
        Args:
            key: The key for the recovery state
            
        Returns:
            The recovery state or None if not found
        """
        return self._recovery_states.get(key)
    
    def clear_recovery_state(self, key: str) -> bool:
        """Clear a recovery state after successful recovery.
        
        Args:
            key: The key for the recovery state
            
        Returns:
            True if state was cleared, False if not found
        """
        if key in self._recovery_states:
            del self._recovery_states[key]
            log.debug("Recovery state cleared", key=key)
            return True
        return False
    
    def get_recent_errors(self, count: int = 10) -> list[AppError]:
        """Get recent errors from history.
        
        Args:
            count: Number of recent errors to return
            
        Returns:
            List of recent AppError instances
        """
        recent = self._error_history[-count:] if self._error_history else []
        return [error for _, error in recent]
    
    def get_error_count_by_category(self) -> dict[ErrorCategory, int]:
        """Get count of errors by category.
        
        Returns:
            Dictionary mapping categories to error counts
        """
        counts: dict[ErrorCategory, int] = {}
        for _, error in self._error_history:
            counts[error.category] = counts.get(error.category, 0) + 1
        return counts
    
    def create_user_message(
        self,
        error: UserFriendlyError,
        include_suggestions: bool = True,
    ) -> str:
        """Create a formatted user message from an error.
        
        Args:
            error: The user-friendly error
            include_suggestions: Whether to include suggested actions
            
        Returns:
            Formatted message string
        """
        parts = [error.message]
        
        if include_suggestions and error.suggested_actions:
            parts.append("\nSuggested actions:")
            for action in error.suggested_actions[:3]:  # Limit to 3 suggestions
                parts.append(f"  • {action}")
        
        return "\n".join(parts)


# Import json for JSONDecodeError check
import json


# Global error handling service instance
_error_service: ErrorHandlingService | None = None


def get_error_service() -> ErrorHandlingService:
    """Get the global error handling service instance."""
    global _error_service
    if _error_service is None:
        _error_service = ErrorHandlingService()
    return _error_service


def handle_error(
    error: Exception,
    operation: str,
    component: str,
    context: dict[str, Any] | None = None,
) -> UserFriendlyError:
    """Convenience function to handle errors using the global service.
    
    Args:
        error: The exception that occurred
        operation: The operation being performed
        component: The component where the error occurred
        context: Additional context information
        
    Returns:
        User-friendly error representation
    """
    return get_error_service().handle_error(error, operation, component, context)
