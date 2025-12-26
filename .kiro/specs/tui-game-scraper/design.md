# Design Document

## Overview

The TUI Game Scraper application transforms a basic web scraper into a modern, well-structured textual user interface application. The system will provide an intuitive interface for scraping game metadata from Vimm's Lair and downloading game files while following modern Python development practices.

The application uses the Textual framework for the TUI, structlog for logging, and follows Python 3.12+ type hinting standards. The architecture emphasizes separation of concerns, proper error handling, and user experience through progress tracking and clear feedback.

## Architecture

The application follows a layered architecture with clear separation between presentation, business logic, and data access:

```
┌─────────────────────────────────────────┐
│              TUI Layer                  │
│  (Screens, Widgets, User Interaction)   │
├─────────────────────────────────────────┤
│            Service Layer                │
│   (Game Scraper, Download Manager)     │
├─────────────────────────────────────────┤
│           Infrastructure Layer          │
│  (HTTP Client, File System, Config)    │
└─────────────────────────────────────────┘
```

### Key Architectural Principles

- **Separation of Concerns**: UI logic is separated from business logic and data access
- **Dependency Injection**: Services are injected into UI components for testability
- **Async/Await**: Non-blocking operations for network requests and file I/O
- **Event-Driven**: Reactive UI updates based on application state changes
- **Configuration-Driven**: Externalized configuration for flexibility

## Components and Interfaces

### TUI Components

**MainApp**: The root Textual application that manages screens and global state
- Manages screen navigation and routing
- Handles global key bindings and application lifecycle
- Coordinates between different screens

**MainMenuScreen**: Primary navigation interface
- Displays main menu options (Scrape, Download, Settings, View Data)
- Handles user selection and navigation to appropriate screens

**ScrapingScreen**: Interface for configuring and monitoring scraping operations
- Configuration form for target letters, categories, and options
- Real-time progress display with progress bars
- Cancel/pause functionality for long-running operations

**DownloadScreen**: Interface for managing file downloads
- Queue display with individual file progress
- Batch download controls (start, pause, cancel)
- Download statistics and completion status

**SettingsScreen**: Configuration management interface
- Form-based settings editor with validation
- Save/reset functionality
- Preview of current configuration

**DataViewScreen**: Game data browser and search interface
- Searchable table of scraped games
- Filtering and sorting capabilities
- Detailed game information display

### Service Layer

**GameScraperService**: Core scraping functionality
```python
class GameScraperService:
    async def scrape_category(self, category: str, letters: list[str]) -> AsyncIterator[GameData]
    async def scrape_game_details(self, game_url: str) -> GameDetails
    def get_scraping_progress(self) -> ScrapingProgress
```

**DownloadManagerService**: File download management
```python
class DownloadManagerService:
    async def download_game(self, game: GameData, disc: DiscInfo) -> None
    async def download_batch(self, games: list[GameData]) -> None
    def get_download_progress(self) -> DownloadProgress
    def pause_downloads(self) -> None
    def resume_downloads(self) -> None
```

**ConfigurationService**: Application configuration management
```python
class ConfigurationService:
    def load_config(self) -> AppConfig
    def save_config(self, config: AppConfig) -> None
    def validate_config(self, config: AppConfig) -> ValidationResult
```

### Infrastructure Layer

**HttpClientService**: HTTP operations with retry and rate limiting
```python
class HttpClientService:
    async def get(self, url: str, headers: dict[str, str] | None = None) -> Response
    async def download_file(self, url: str, path: Path) -> None
```

**FileSystemService**: File operations and storage management
```python
class FileSystemService:
    async def save_json(self, data: dict, path: Path) -> None
    async def load_json(self, path: Path) -> dict
    def ensure_directory(self, path: Path) -> None
```

## Data Models

### Core Data Structures

```python
@dataclass(frozen=True)
class GameData:
    title: str
    game_url: str
    category: str
    discs: list[DiscInfo]
    scraped_at: datetime

@dataclass(frozen=True)
class DiscInfo:
    disc_number: str
    media_id: str
    download_url: str
    file_size: int | None = None

@dataclass(frozen=True)
class AppConfig:
    target_letters: list[str]
    download_directory: Path
    concurrent_downloads: int
    request_delay: float
    log_level: str
    
@dataclass(frozen=True)
class ScrapingProgress:
    current_letter: str
    current_game: str
    games_processed: int
    total_games: int
    errors: list[str]
    
@dataclass(frozen=True)
class DownloadProgress:
    current_file: str
    bytes_downloaded: int
    total_bytes: int
    download_speed: float
    eta_seconds: int
```

### State Management

The application uses reactive state management with Textual's reactive attributes:

```python
class AppState:
    games_data: Reactive[dict[str, GameData]] = Reactive({})
    scraping_active: Reactive[bool] = Reactive(False)
    download_queue: Reactive[list[DownloadTask]] = Reactive([])
    current_config: Reactive[AppConfig] = Reactive(AppConfig())
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

Based on the prework analysis, the following properties have been identified after eliminating redundancy:

**Property 1: Menu navigation consistency**
*For any* valid menu option, selecting it should result in navigation to the corresponding screen with the correct screen being displayed
**Validates: Requirements 1.2**

**Property 2: Back navigation consistency**
*For any* screen in the application, pressing escape should return to the previous screen in the navigation stack
**Validates: Requirements 1.3**

**Property 3: Configuration validation**
*For any* configuration input, the system should validate it correctly - rejecting invalid inputs with error messages and accepting valid inputs
**Validates: Requirements 2.2, 2.3**

**Property 4: Configuration persistence round-trip**
*For any* valid configuration, saving it and then reloading the application should preserve all configuration values
**Validates: Requirements 2.4, 2.5**

**Property 5: Progress tracking updates**
*For any* game being processed during scraping, the progress tracker should update with the correct game name and completion percentage
**Validates: Requirements 3.2**

**Property 6: Error handling during operations**
*For any* error that occurs during scraping or downloading, the system should display error information while allowing the overall process to continue
**Validates: Requirements 3.3, 4.3**

**Property 7: Download queue management**
*For any* number of downloads in the queue, the download manager should correctly display overall queue status and individual file progress
**Validates: Requirements 4.2**

**Property 8: Download pause-resume round-trip**
*For any* active download, pausing and then resuming should restore the download to its previous state without data loss
**Validates: Requirements 4.5**

**Property 9: Structured logging consistency**
*For any* operation or user action, the logger should record events with appropriate log levels and structured data including relevant context
**Validates: Requirements 5.1, 5.3**

**Property 10: Error logging completeness**
*For any* error that occurs, the logger should capture complete error details including stack traces and context information
**Validates: Requirements 5.2**

**Property 11: User-friendly error messages**
*For any* type of error (network, file system, validation, unexpected), the application should display user-friendly error messages while logging detailed technical information
**Validates: Requirements 7.1, 7.2, 7.3, 7.4**

**Property 12: Error recovery state consistency**
*For any* error that occurs, after recovery the application should return to a stable state without data loss or corruption
**Validates: Requirements 7.5**

**Property 13: Game search filtering**
*For any* search criteria (title, category, metadata), the search function should return only games that match the specified criteria
**Validates: Requirements 8.2**

**Property 14: Game selection information display**
*For any* game selected by the user, the detailed view should display complete information including all available discs and download options
**Validates: Requirements 8.3**

**Property 15: Data refresh consistency**
*For any* change to the underlying game data, the display should be updated to reflect the new information accurately
**Validates: Requirements 8.4**

## Error Handling

The application implements comprehensive error handling at multiple levels:

### Network Error Handling
- **Connection Timeouts**: Configurable timeout values with exponential backoff retry
- **Rate Limiting**: Respect server rate limits with automatic delay adjustment
- **HTTP Errors**: Graceful handling of 4xx and 5xx responses with user-friendly messages
- **DNS Resolution**: Clear error messages for network connectivity issues

### File System Error Handling
- **Permission Errors**: Clear messages when write permissions are insufficient
- **Disk Space**: Monitoring and warnings for low disk space conditions
- **File Corruption**: Integrity checks for downloaded files with re-download capability
- **Path Issues**: Validation and creation of required directory structures

### User Input Validation
- **Configuration Validation**: Real-time validation with immediate feedback
- **Search Input Sanitization**: Protection against injection and malformed queries
- **File Path Validation**: Ensure valid and safe file paths for downloads

### Application Recovery
- **State Persistence**: Critical application state is persisted to survive crashes
- **Graceful Degradation**: Core functionality remains available even when optional features fail
- **Transaction Safety**: Operations are atomic where possible to prevent partial state corruption

## Testing Strategy

The application employs a dual testing approach combining unit tests and property-based tests for comprehensive coverage.

### Unit Testing Approach
Unit tests will focus on:
- Specific examples that demonstrate correct behavior
- Integration points between components
- Edge cases and boundary conditions
- Error conditions and exception handling

Unit tests provide concrete examples of expected behavior and catch specific bugs in implementation details.

### Property-Based Testing Approach
Property-based tests will verify universal properties using the **Hypothesis** library for Python. Each property-based test will:
- Run a minimum of 100 iterations with randomly generated inputs
- Be tagged with comments explicitly referencing the correctness property from this design document
- Use the format: `**Feature: tui-game-scraper, Property {number}: {property_text}**`
- Focus on testing invariants that should hold across all valid inputs

Property-based tests provide broader coverage by testing general correctness across many input combinations.

### Test Configuration
- **Framework**: pytest for unit tests, Hypothesis for property-based tests
- **Coverage Target**: 90%+ code coverage for core business logic
- **Test Data**: Factories for generating test data with realistic constraints
- **Mocking Strategy**: Mock external dependencies (HTTP requests, file system) while testing real business logic

### Integration Testing
- **End-to-End Scenarios**: Complete user workflows from UI interaction to data persistence
- **Service Integration**: Testing interactions between service layer components
- **Configuration Testing**: Verify configuration loading and validation across different scenarios

The testing strategy ensures both specific correctness (unit tests) and general correctness (property tests) while maintaining fast feedback cycles during development.