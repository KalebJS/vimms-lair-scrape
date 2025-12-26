"""Property-based tests for configuration service."""

import tempfile
from pathlib import Path

import pytest
from hypothesis import given, strategies as st

from src.models import AppConfig
from src.services import ConfigurationService


# Strategies for generating valid configuration data
valid_letters = st.lists(
    st.text(min_size=1, max_size=1, alphabet=st.characters(whitelist_categories=("Lu", "Ll"))),
    min_size=1,
    max_size=10
)

valid_paths = st.builds(
    lambda x: Path.home() / "test" / x,
    st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")))
)

valid_concurrent_downloads = st.integers(min_value=1, max_value=10)
valid_request_delay = st.floats(min_value=0.0, max_value=60.0, allow_nan=False, allow_infinity=False)
valid_log_levels = st.sampled_from(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])

valid_config_strategy = st.builds(
    AppConfig,
    target_letters=valid_letters,
    download_directory=valid_paths,
    concurrent_downloads=valid_concurrent_downloads,
    request_delay=valid_request_delay,
    log_level=valid_log_levels
)


@given(valid_config_strategy)
def test_configuration_round_trip(config: AppConfig) -> None:
    """
    **Feature: tui-game-scraper, Property 4: Configuration persistence round-trip**
    **Validates: Requirements 2.4, 2.5**
    
    For any valid configuration, saving it and then reloading should preserve all values.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        config_path = Path(temp_dir) / "test_config.json"
        service = ConfigurationService(config_path)
        
        # Save the configuration
        service.save_config(config)
        
        # Load it back
        loaded_config = service.load_config()
        
        # Verify all fields are preserved
        assert loaded_config.target_letters == config.target_letters
        assert loaded_config.download_directory == config.download_directory
        assert loaded_config.concurrent_downloads == config.concurrent_downloads
        assert loaded_config.request_delay == config.request_delay
        assert loaded_config.log_level == config.log_level


def test_configuration_round_trip_example() -> None:
    """Unit test example for configuration round-trip."""
    config = AppConfig(
        target_letters=["A", "B"],
        download_directory=Path.home() / "Downloads" / "games",
        concurrent_downloads=3,
        request_delay=1.5,
        log_level="INFO"
    )
    
    with tempfile.TemporaryDirectory() as temp_dir:
        config_path = Path(temp_dir) / "test_config.json"
        service = ConfigurationService(config_path)
        
        service.save_config(config)
        loaded_config = service.load_config()
        
        assert loaded_config.target_letters == ["A", "B"]
        assert loaded_config.download_directory == Path.home() / "Downloads" / "games"
        assert loaded_config.concurrent_downloads == 3
        assert loaded_config.request_delay == 1.5
        assert loaded_config.log_level == "INFO"


# Strategies for generating invalid configuration data that will pass AppConfig construction
# but fail validation

def create_invalid_config_strategy():
    """Create strategy for invalid but constructible configs."""
    return st.one_of(
        # Empty target letters
        st.builds(AppConfig, 
                 target_letters=st.just([]),
                 download_directory=valid_paths,
                 concurrent_downloads=valid_concurrent_downloads,
                 request_delay=valid_request_delay,
                 log_level=valid_log_levels),
        
        # Invalid target letters (multi-character)
        st.builds(AppConfig,
                 target_letters=st.lists(st.text(min_size=2, max_size=5), min_size=1, max_size=3),
                 download_directory=valid_paths,
                 concurrent_downloads=valid_concurrent_downloads,
                 request_delay=valid_request_delay,
                 log_level=valid_log_levels),
        
        # Relative paths (invalid)
        st.builds(AppConfig,
                 target_letters=valid_letters,
                 download_directory=st.builds(Path, st.text(min_size=1, max_size=10).filter(lambda x: not x.startswith("/"))),
                 concurrent_downloads=valid_concurrent_downloads,
                 request_delay=valid_request_delay,
                 log_level=valid_log_levels),
        
        # Invalid concurrent downloads (too high)
        st.builds(AppConfig,
                 target_letters=valid_letters,
                 download_directory=valid_paths,
                 concurrent_downloads=st.integers(min_value=11, max_value=20),
                 request_delay=valid_request_delay,
                 log_level=valid_log_levels),
        
        # Invalid request delay (too high)
        st.builds(AppConfig,
                 target_letters=valid_letters,
                 download_directory=valid_paths,
                 concurrent_downloads=valid_concurrent_downloads,
                 request_delay=st.floats(min_value=61.0, max_value=120.0, allow_nan=False, allow_infinity=False),
                 log_level=valid_log_levels),
        
        # Invalid log level
        st.builds(AppConfig,
                 target_letters=valid_letters,
                 download_directory=valid_paths,
                 concurrent_downloads=valid_concurrent_downloads,
                 request_delay=valid_request_delay,
                 log_level=st.text(min_size=1).filter(lambda x: x not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]))
    )


@given(create_invalid_config_strategy())
def test_configuration_validation_rejects_invalid(config: AppConfig) -> None:
    """
    **Feature: tui-game-scraper, Property 3: Configuration validation**
    **Validates: Requirements 2.2, 2.3**
    
    For any invalid configuration input, the system should validate it correctly - 
    rejecting invalid inputs with error messages.
    """
    service = ConfigurationService()
    result = service.validate_config(config)
    
    # Invalid configurations should be rejected
    assert not result.is_valid
    assert len(result.errors) > 0
    assert all(isinstance(error, str) for error in result.errors)


@given(valid_config_strategy)
def test_configuration_validation_accepts_valid(config: AppConfig) -> None:
    """
    **Feature: tui-game-scraper, Property 3: Configuration validation**
    **Validates: Requirements 2.2, 2.3**
    
    For any valid configuration input, the system should validate it correctly - 
    accepting valid inputs without error messages.
    """
    service = ConfigurationService()
    result = service.validate_config(config)
    
    # Valid configurations should be accepted
    assert result.is_valid
    assert len(result.errors) == 0


def test_configuration_validation_examples() -> None:
    """Unit test examples for configuration validation."""
    service = ConfigurationService()
    
    # Valid configuration
    valid_config = AppConfig(
        target_letters=["A", "B"],
        download_directory=Path.home() / "Downloads",
        concurrent_downloads=3,
        request_delay=1.0,
        log_level="INFO"
    )
    result = service.validate_config(valid_config)
    assert result.is_valid
    assert len(result.errors) == 0
    
    # Invalid configuration - empty letters
    invalid_config = AppConfig(
        target_letters=[],
        download_directory=Path.home() / "Downloads",
        concurrent_downloads=3,
        request_delay=1.0,
        log_level="INFO"
    )
    result = service.validate_config(invalid_config)
    assert not result.is_valid
    assert len(result.errors) > 0
    assert "target_letters cannot be empty" in result.errors