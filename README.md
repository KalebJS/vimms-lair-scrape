# TUI Game Scraper

A modern textual user interface application for scraping game metadata and downloading game files from Vimm's Lair.

## Project Structure

```
src/
├── __init__.py          # Package initialization
├── main.py              # Application entry point
├── models/              # Data models and structures
│   └── __init__.py
├── services/            # Business logic and external integrations
│   └── __init__.py
└── ui/                  # Textual UI components
    └── __init__.py

tests/                   # Test suite
└── __init__.py
```

## Development Setup

1. Install dependencies:
   ```bash
   uv sync
   ```

2. Install development dependencies:
   ```bash
   uv add --dev pytest hypothesis mypy pytest-asyncio pytest-cov
   ```

3. Run the application:
   ```bash
   uv run src/main.py
   ```

4. Run tests:
   ```bash
   uv run pytest
   ```

5. Run type checking:
   ```bash
   uv run mypy src/
   ```

## Features

- Modern Python 3.12+ with type hints
- Textual framework for TUI
- Structured logging with structlog
- Async HTTP client with httpx
- Data validation with Pydantic
- Property-based testing with Hypothesis
- Comprehensive test coverage

## Requirements

- Python 3.12+
- uv package manager

---

## Original Script Information

This project is a modernized version of a Vimm's Lair scraper. The original script scraped game links from Vimm's Lair for personal or educational use, focusing on Xbox game categories and individual game pages.

### Important Notes

- **Respects Site Limits**: This application does not bypass download-per-client limits
- **Disclaimer**: Use responsibly and in accordance with Vimm's Lair's terms of service
- **Ethical Scraping**: Designed with ethical scraping practices in mind