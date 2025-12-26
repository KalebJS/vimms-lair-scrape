"""Settings screen for configuring application settings."""

from pathlib import Path
from typing import ClassVar, override

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, Input, Label, Select, Static

import structlog

from src.models.config import AppConfig
from src.services.config import ConfigurationService

from .base import BaseScreen

log = structlog.stdlib.get_logger()


# Valid log levels for the dropdown
LOG_LEVELS: list[tuple[str, str]] = [
    ("DEBUG", "DEBUG"),
    ("INFO", "INFO"),
    ("WARNING", "WARNING"),
    ("ERROR", "ERROR"),
    ("CRITICAL", "CRITICAL"),
]


class SettingsScreen(BaseScreen):
    """Settings screen for configuring application settings.
    
    This screen provides a form-based interface for editing:
    - Target letters for scraping
    - Download directory path
    - Concurrent downloads limit
    - Request delay between operations
    - Log level
    
    Features:
    - Real-time validation feedback
    - Save and reset functionality
    - Confirmation before discarding changes
    """
    
    SCREEN_TITLE: ClassVar[str] = "Settings"
    SCREEN_NAME: ClassVar[str] = "settings"
    
    CSS: ClassVar[str] = """
    SettingsScreen {
        align: center middle;
    }
    
    #settings-container {
        width: 80;
        height: auto;
        max-height: 90%;
        padding: 1 2;
        border: solid $primary;
        background: $surface;
    }
    
    #settings-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    
    .form-group {
        margin-bottom: 1;
        height: auto;
    }
    
    .form-label {
        margin-bottom: 0;
        color: $text;
    }
    
    .form-input {
        width: 100%;
    }
    
    .form-hint {
        color: $text-muted;
        text-style: italic;
        margin-top: 0;
    }
    
    .validation-error {
        color: $error;
        margin-top: 0;
    }
    
    .validation-success {
        color: $success;
        margin-top: 0;
    }
    
    #button-row {
        margin-top: 2;
        height: auto;
        align: center middle;
    }
    
    #button-row Button {
        margin: 0 1;
    }
    
    #validation-status {
        text-align: center;
        margin-top: 1;
        height: 1;
    }
    """
    
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "go_back", "Back", show=True),
        Binding("ctrl+s", "save_settings", "Save", show=True),
        Binding("ctrl+r", "reset_settings", "Reset", show=True),
    ]

    # Instance attributes
    _original_config: AppConfig | None
    _has_changes: bool
    _validation_errors: dict[str, str]
    
    def __init__(self) -> None:
        """Initialize the settings screen."""
        super().__init__()
        self._original_config = None
        self._has_changes = False
        self._validation_errors = {}
    
    @override
    def compose(self) -> ComposeResult:
        """Compose the settings form layout."""
        with Container(id="settings-container"):
            yield Static("⚙️ Settings", id="settings-title")
            
            with Vertical(id="settings-form"):
                # Target Letters
                with Vertical(classes="form-group"):
                    yield Label("Target Letters:", classes="form-label")
                    yield Input(
                        placeholder="A, B, C (comma-separated)",
                        id="input-target-letters",
                        classes="form-input",
                    )
                    yield Static(
                        "Letters to scrape (e.g., A, B, C)",
                        classes="form-hint",
                        id="hint-target-letters",
                    )
                
                # Download Directory
                with Vertical(classes="form-group"):
                    yield Label("Download Directory:", classes="form-label")
                    yield Input(
                        placeholder="/path/to/downloads",
                        id="input-download-dir",
                        classes="form-input",
                    )
                    yield Static(
                        "Absolute path for downloaded files",
                        classes="form-hint",
                        id="hint-download-dir",
                    )
                
                # Concurrent Downloads
                with Vertical(classes="form-group"):
                    yield Label("Concurrent Downloads:", classes="form-label")
                    yield Input(
                        placeholder="3",
                        id="input-concurrent",
                        classes="form-input",
                        type="integer",
                    )
                    yield Static(
                        "Number of simultaneous downloads (1-10)",
                        classes="form-hint",
                        id="hint-concurrent",
                    )
                
                # Request Delay
                with Vertical(classes="form-group"):
                    yield Label("Request Delay (seconds):", classes="form-label")
                    yield Input(
                        placeholder="1.0",
                        id="input-delay",
                        classes="form-input",
                        type="number",
                    )
                    yield Static(
                        "Delay between requests (0-60 seconds)",
                        classes="form-hint",
                        id="hint-delay",
                    )
                
                # Log Level
                with Vertical(classes="form-group"):
                    yield Label("Log Level:", classes="form-label")
                    yield Select(
                        LOG_LEVELS,
                        id="select-log-level",
                        allow_blank=False,
                        value="INFO",
                    )
                    yield Static(
                        "Logging verbosity level",
                        classes="form-hint",
                        id="hint-log-level",
                    )
            
            # Validation status
            yield Static("", id="validation-status")
            
            # Buttons
            with Horizontal(id="button-row"):
                yield Button("Save", id="btn-save", variant="primary")
                yield Button("Reset", id="btn-reset", variant="default")
                yield Button("Cancel", id="btn-cancel", variant="error")

    @override
    async def on_mount(self) -> None:
        """Handle screen mount - load current configuration."""
        await super().on_mount()
        await self._load_current_config()
    
    async def _load_current_config(self) -> None:
        """Load and display the current configuration."""
        config_service = self._get_config_service()
        if config_service:
            try:
                config = config_service.load_config()
                self._original_config = config
                self._populate_form(config)
                log.info("Settings loaded", config=str(config))
            except Exception as e:
                log.error("Failed to load settings", error=str(e))
                self.notify_error(f"Failed to load settings: {e}")
        else:
            # Use default config if no service available
            default_service = ConfigurationService()
            config = default_service.load_config()  # This returns default if no file exists
            self._original_config = config
            self._populate_form(config)
    
    def _get_config_service(self) -> ConfigurationService | None:
        """Get the configuration service from the app."""
        try:
            return self.game_app.config_service
        except RuntimeError:
            return None
    
    def _populate_form(self, config: AppConfig) -> None:
        """Populate form fields with configuration values."""
        # Target letters
        letters_input = self.query_one("#input-target-letters", Input)
        letters_input.value = ", ".join(config.target_letters)
        
        # Download directory
        dir_input = self.query_one("#input-download-dir", Input)
        dir_input.value = str(config.download_directory)
        
        # Concurrent downloads
        concurrent_input = self.query_one("#input-concurrent", Input)
        concurrent_input.value = str(config.concurrent_downloads)
        
        # Request delay
        delay_input = self.query_one("#input-delay", Input)
        delay_input.value = str(config.request_delay)
        
        # Log level - use type ignore for Select generic type
        log_select = self.query_one("#select-log-level", Select)  # type: ignore[type-arg]
        log_select.value = config.log_level
        
        self._has_changes = False
        self._update_validation_status()
    
    def _get_form_values(self) -> dict[str, str]:
        """Get current values from form fields."""
        log_select = self.query_one("#select-log-level", Select)  # type: ignore[type-arg]
        log_value = log_select.value
        return {
            "target_letters": self.query_one("#input-target-letters", Input).value,
            "download_directory": self.query_one("#input-download-dir", Input).value,
            "concurrent_downloads": self.query_one("#input-concurrent", Input).value,
            "request_delay": self.query_one("#input-delay", Input).value,
            "log_level": str(log_value) if log_value else "INFO",
        }
    
    def _validate_form(self) -> tuple[bool, dict[str, str]]:
        """Validate all form fields and return validation result."""
        errors: dict[str, str] = {}
        values = self._get_form_values()
        
        # Validate target letters
        letters_str = values["target_letters"].strip()
        if not letters_str:
            errors["target_letters"] = "Target letters cannot be empty"
        else:
            letters = [l.strip().upper() for l in letters_str.split(",") if l.strip()]
            if not letters:
                errors["target_letters"] = "At least one letter is required"
            elif not all(len(l) == 1 and l.isalpha() for l in letters):
                errors["target_letters"] = "Each entry must be a single letter"
        
        # Validate download directory
        dir_str = values["download_directory"].strip()
        if not dir_str:
            errors["download_directory"] = "Download directory cannot be empty"
        else:
            path = Path(dir_str)
            if not path.is_absolute():
                errors["download_directory"] = "Path must be absolute"
        
        # Validate concurrent downloads
        concurrent_str = values["concurrent_downloads"].strip()
        if not concurrent_str:
            errors["concurrent_downloads"] = "Concurrent downloads is required"
        else:
            try:
                concurrent = int(concurrent_str)
                if concurrent < 1:
                    errors["concurrent_downloads"] = "Must be at least 1"
                elif concurrent > 10:
                    errors["concurrent_downloads"] = "Cannot exceed 10"
            except ValueError:
                errors["concurrent_downloads"] = "Must be a valid integer"
        
        # Validate request delay
        delay_str = values["request_delay"].strip()
        if not delay_str:
            errors["request_delay"] = "Request delay is required"
        else:
            try:
                delay = float(delay_str)
                if delay < 0:
                    errors["request_delay"] = "Cannot be negative"
                elif delay > 60:
                    errors["request_delay"] = "Cannot exceed 60 seconds"
            except ValueError:
                errors["request_delay"] = "Must be a valid number"
        
        # Validate log level
        log_level = values["log_level"]
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if log_level not in valid_levels:
            errors["log_level"] = f"Must be one of: {', '.join(valid_levels)}"
        
        self._validation_errors = errors
        return len(errors) == 0, errors

    def _update_validation_status(self) -> None:
        """Update the validation status display."""
        status_widget = self.query_one("#validation-status", Static)
        is_valid, errors = self._validate_form()
        
        if is_valid:
            if self._has_changes:
                status_widget.update("✓ Valid - Press Save to apply changes")
                _ = status_widget.remove_class("validation-error")
                _ = status_widget.add_class("validation-success")
            else:
                status_widget.update("")
                _ = status_widget.remove_class("validation-error")
                _ = status_widget.remove_class("validation-success")
        else:
            error_msg = next(iter(errors.values()), "Invalid configuration")
            status_widget.update(f"✗ {error_msg}")
            _ = status_widget.add_class("validation-error")
            _ = status_widget.remove_class("validation-success")
    
    def _build_config_from_form(self) -> AppConfig | None:
        """Build an AppConfig from form values, or None if invalid."""
        is_valid, _ = self._validate_form()
        if not is_valid:
            return None
        
        values = self._get_form_values()
        
        # Parse target letters
        letters = [l.strip().upper() for l in values["target_letters"].split(",") if l.strip()]
        
        return AppConfig(
            target_letters=letters,
            download_directory=Path(values["download_directory"]),
            concurrent_downloads=int(values["concurrent_downloads"]),
            request_delay=float(values["request_delay"]),
            log_level=values["log_level"],
        )
    
    async def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input field changes for real-time validation."""
        self._has_changes = True
        self._update_validation_status()
        log.debug("Input changed", input_id=event.input.id, value=event.value)
    
    async def on_select_changed(self, event: Select.Changed) -> None:
        """Handle select field changes."""
        self._has_changes = True
        self._update_validation_status()
        log.debug("Select changed", select_id=str(event.select.id), value=str(event.value))
    
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id
        
        if button_id == "btn-save":
            await self._save_settings()
        elif button_id == "btn-reset":
            await self._reset_settings()
        elif button_id == "btn-cancel":
            await self._cancel_settings()
    
    async def _save_settings(self) -> None:
        """Save the current settings."""
        config = self._build_config_from_form()
        if not config:
            self.notify_error("Cannot save: Please fix validation errors")
            return
        
        config_service = self._get_config_service()
        if config_service:
            try:
                config_service.save_config(config)
                self._original_config = config
                self._has_changes = False
                self._update_validation_status()
                self.notify_success("Settings saved successfully")
                log.info("Settings saved", config=str(config))
            except Exception as e:
                log.error("Failed to save settings", error=str(e))
                self.notify_error(f"Failed to save: {e}")
        else:
            # No service available, just update local state
            self._original_config = config
            self._has_changes = False
            self._update_validation_status()
            self.notify_success("Settings updated (not persisted)")
    
    async def _reset_settings(self) -> None:
        """Reset form to original configuration."""
        if self._original_config:
            self._populate_form(self._original_config)
            self.notify_success("Settings reset to last saved values")
            log.info("Settings reset")
    
    async def _cancel_settings(self) -> None:
        """Cancel and go back, discarding changes."""
        if self._has_changes:
            # In a full implementation, we'd show a confirmation dialog
            log.info("Discarding unsaved changes")
        await self.action_go_back()
    
    async def action_save_settings(self) -> None:
        """Action handler for save keyboard shortcut."""
        await self._save_settings()
    
    async def action_reset_settings(self) -> None:
        """Action handler for reset keyboard shortcut."""
        await self._reset_settings()
