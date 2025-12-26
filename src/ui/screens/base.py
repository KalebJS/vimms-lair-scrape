"""Base screen class with common functionality for all screens."""

from typing import TYPE_CHECKING, ClassVar

from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Static

import structlog

from src.services.errors import (
    ErrorSeverity,
    UserFriendlyError,
    get_error_service,
    handle_error,
)

if TYPE_CHECKING:
    from src.ui.app import GameScraperApp

log = structlog.stdlib.get_logger()


class BaseScreen(Screen[None]):
    """Base screen class providing common functionality for all application screens.
    
    This class provides:
    - Common key bindings (escape for back navigation)
    - Access to the parent application and its services
    - Logging integration
    - Screen lifecycle hooks
    
    Subclasses should override compose() to define their layout and
    can override on_screen_resume() and on_screen_suspend() for
    screen transition handling.
    """
    
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "go_back", "Back", show=True),
    ]
    
    # Screen metadata - subclasses should override these
    SCREEN_TITLE: ClassVar[str] = "Screen"
    SCREEN_NAME: ClassVar[str] = "base"
    
    # Instance attribute type annotation
    _is_active: bool
    
    def __init__(self, name: str | None = None) -> None:
        """Initialize the base screen.
        
        Args:
            name: Optional name for the screen instance
        """
        super().__init__(name=name or self.SCREEN_NAME)
        self._is_active = False
    
    @property
    def game_app(self) -> "GameScraperApp":
        """Get the parent GameScraperApp instance.
        
        Returns:
            The parent application instance
            
        Raises:
            RuntimeError: If the screen is not attached to a GameScraperApp
        """
        from src.ui.app import GameScraperApp
        
        if isinstance(self.app, GameScraperApp):
            return self.app
        raise RuntimeError("Screen is not attached to a GameScraperApp")
    
    @property
    def screen_is_active(self) -> bool:
        """Check if this screen is currently active."""
        return self._is_active
    
    async def on_mount(self) -> None:
        """Handle screen mount event."""
        log.info("Screen mounted", screen=self.SCREEN_NAME, title=self.SCREEN_TITLE)
        self._is_active = True
    
    async def on_unmount(self) -> None:
        """Handle screen unmount event."""
        log.info("Screen unmounted", screen=self.SCREEN_NAME)
        self._is_active = False
    
    def on_screen_resume(self) -> None:
        """Called when the screen becomes active again after being suspended.
        
        Override this method to refresh data or update the display when
        returning to this screen from another screen.
        """
        log.debug("Screen resumed", screen=self.SCREEN_NAME)
        self._is_active = True
    
    def on_screen_suspend(self) -> None:
        """Called when the screen is suspended (another screen pushed on top).
        
        Override this method to pause operations or save state when
        navigating away from this screen.
        """
        log.debug("Screen suspended", screen=self.SCREEN_NAME)
        self._is_active = False
    
    async def action_go_back(self) -> None:
        """Navigate back to the previous screen.
        
        This delegates to the parent application's navigation system.
        """
        await self.game_app.action_go_back()
    
    def create_title_widget(self, title: str | None = None) -> Static:
        """Create a styled title widget for the screen.
        
        Args:
            title: Optional title text, defaults to SCREEN_TITLE
            
        Returns:
            A Static widget with the title
        """
        return Static(title or self.SCREEN_TITLE, classes="title")
    
    def notify_error(self, message: str) -> None:
        """Display an error notification to the user.
        
        Args:
            message: The error message to display
        """
        self.notify(message, severity="error")
        log.error("User notification", message=message, screen=self.SCREEN_NAME)
    
    def notify_success(self, message: str) -> None:
        """Display a success notification to the user.
        
        Args:
            message: The success message to display
        """
        self.notify(message, severity="information")
        log.info("User notification", message=message, screen=self.SCREEN_NAME)
    
    def notify_warning(self, message: str) -> None:
        """Display a warning notification to the user.
        
        Args:
            message: The warning message to display
        """
        self.notify(message, severity="warning")
        log.warning("User notification", message=message, screen=self.SCREEN_NAME)
    
    def handle_exception(
        self,
        error: Exception,
        operation: str,
        context: dict[str, str | int | float | bool] | None = None,
    ) -> UserFriendlyError:
        """Handle an exception and display user-friendly error message.
        
        This method:
        1. Converts the exception to a user-friendly error
        2. Logs technical details
        3. Displays appropriate notification to user
        4. Returns the error for further handling if needed
        
        Args:
            error: The exception that occurred
            operation: Description of the operation that failed
            context: Additional context information
            
        Returns:
            UserFriendlyError with message and suggested actions
        """
        # Use the error handling service
        user_error = handle_error(
            error=error,
            operation=operation,
            component=self.SCREEN_NAME,
            context=context,
        )
        
        # Display notification based on severity
        error_service = get_error_service()
        message = error_service.create_user_message(user_error, include_suggestions=False)
        
        if user_error.severity == ErrorSeverity.WARNING:
            self.notify_warning(message)
        else:
            self.notify_error(message)
        
        return user_error
    
    def show_error_with_suggestions(
        self,
        error: UserFriendlyError,
    ) -> None:
        """Display an error with suggested actions.
        
        Args:
            error: The user-friendly error to display
        """
        error_service = get_error_service()
        message = error_service.create_user_message(error, include_suggestions=True)
        
        if error.severity == ErrorSeverity.WARNING:
            self.notify_warning(message)
        else:
            self.notify_error(message)
