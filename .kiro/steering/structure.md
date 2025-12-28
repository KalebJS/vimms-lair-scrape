# Project Structure

```
src/
├── main.py              # Entry point, CLI args, ApplicationContext
├── models/              # Frozen dataclasses for data structures
│   ├── config.py        # AppConfig
│   ├── game.py          # GameData, DiscInfo
│   └── progress.py      # ScrapingProgress, DownloadProgress
├── services/            # Business logic layer
│   ├── config.py        # ConfigurationService - JSON persistence
│   ├── download_manager.py  # Queue management, concurrent downloads
│   ├── game_scraper.py  # Async scraping with progress tracking
│   ├── http_client.py   # Rate-limited HTTP client wrapper
│   ├── filesystem.py    # File operations abstraction
│   ├── logging.py       # structlog configuration
│   └── errors.py        # Custom exception hierarchy
└── ui/                  # Textual UI layer
    ├── app.py           # Main App class, reactive state, navigation
    ├── screens/         # Screen components (main_menu, settings, etc.)
    └── widgets/         # Reusable UI widgets

tests/                   # Test suite (mirrors src/ structure)
├── test_config_service.py
├── test_download_manager.py
├── test_game_scraper.py
└── ...

logs/                    # Runtime logs (gitignored content)
main.py                  # Legacy script (reference only)
```

## Architecture Patterns
- Dependency injection via `ApplicationContext`
- Lazy service initialization
- Frozen dataclasses for immutable models
- Async iterators for streaming results
- Reactive state management in UI via `textual.reactive`

## Naming Conventions
- Services: `*Service` suffix (e.g., `ConfigurationService`)
- Models: Plain names, frozen dataclasses
- Tests: `test_*.py` with `test_*` functions
- Screens: Located in `ui/screens/`, one per file
