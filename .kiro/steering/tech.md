# Tech Stack

## Runtime
- Python 3.12+ (required)
- Package manager: `uv`

## Core Dependencies
- `textual` - TUI framework
- `structlog` - Structured logging
- `httpx` - Async HTTP client
- `beautifulsoup4` - HTML parsing
- `pydantic` - Data validation

## Dev Dependencies
- `pytest` + `pytest-asyncio` - Testing
- `hypothesis` - Property-based testing
- `mypy` - Static type checking (strict mode)
- `pytest-cov` - Coverage reporting

## Common Commands

```bash
# Install dependencies
uv sync

# Run application
uv run python -m src.main
# or
uv run tui-game-scraper

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=src --cov-report=term-missing

# Type checking
uv run mypy src/

# Run without TUI (CLI mode)
uv run python -m src.main --no-tui
```

## Configuration
- mypy: strict mode enabled in `pyproject.toml`
- pytest: async mode auto, coverage on `src/`
- Logs: `./logs/app.log` and `./logs/error.log`
