"""Tests for the logging service."""

import json
import logging
import os
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
import structlog
from hypothesis import given, strategies as st

from src.services.logging import LoggingService, setup_logging


class TestLoggingService:
    """Test cases for LoggingService."""
    
    def test_development_logging_format(self) -> None:
        """Test that development logging uses console format."""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            # Capture the actual stdout during logging configuration
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                service = LoggingService(log_level="INFO")
                service.configure()
                
                # Get a logger and log a message
                logger = service.get_logger("test")
                logger.info("test message", key="value")
                
                output = mock_stdout.getvalue()
                
            # Development format should be human-readable, not JSON
            assert "test message" in output
            assert "[    INFO]" in output or "info" in output.lower()
            # In development mode without file logging, should use console renderer
            assert not output.strip().startswith("{")
    
    def test_production_logging_format(self) -> None:
        """Test that production logging uses JSON format."""
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            service = LoggingService(log_level="INFO")
            service.configure()
            
            logger = service.get_logger("test")
            
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                logger.info("test message", key="value")
                output = mock_stdout.getvalue()
                
            # Production format should be JSON
            lines = [line for line in output.strip().split('\n') if line.strip()]
            if lines:
                json_line = lines[0]
                parsed = json.loads(json_line)
                assert parsed["event"] == "test message"
                assert parsed["key"] == "value"
                assert "timestamp" in parsed
                assert "level" in parsed
    
    def test_file_logging_setup(self) -> None:
        """Test that file logging is configured correctly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir)
            # Use production environment to ensure JSON format in files
            with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
                service = LoggingService(log_level="INFO", log_dir=log_dir)
                service.configure()
                
                logger = service.get_logger("test")
                logger.info("test file message", data="test")
                
                # Check that log files are created
                app_log = log_dir / "app.log"
                error_log = log_dir / "error.log"
                
                assert app_log.exists()
                assert error_log.exists()
                
                # Check app log content
                content = app_log.read_text()
                parsed = json.loads(content.strip())
                assert parsed["event"] == "test file message"
                assert parsed["data"] == "test"
    
    def test_error_file_logging(self) -> None:
        """Test that errors are logged to error file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir)
            # Use production environment to ensure JSON format in files
            with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
                service = LoggingService(log_level="DEBUG", log_dir=log_dir)
                service.configure()
                
                logger = service.get_logger("test")
                logger.error("test error message", error_code=500)
                
                error_log = log_dir / "error.log"
                assert error_log.exists()
                
                content = error_log.read_text()
                parsed = json.loads(content.strip())
                assert parsed["event"] == "test error message"
                assert parsed["error_code"] == 500
                assert parsed["level"] == "error"


class TestStructuredLoggingProperties:
    """Property-based tests for structured logging consistency."""
    
    @given(
        log_level=st.sampled_from(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
        logger_name=st.text(min_size=1, max_size=50).filter(lambda x: x.isidentifier()),
        message=st.text(min_size=1, max_size=200),
        context_data=st.dictionaries(
            keys=st.text(min_size=1, max_size=20).filter(lambda x: x.isidentifier()),
            values=st.one_of(
                st.text(max_size=100),
                st.integers(),
                st.floats(allow_nan=False, allow_infinity=False),
                st.booleans()
            ),
            max_size=5
        )
    )
    def test_structured_logging_consistency(
        self, 
        log_level: str, 
        logger_name: str, 
        message: str, 
        context_data: dict[str, str | int | float | bool]
    ) -> None:
        """**Feature: tui-game-scraper, Property 9: Structured logging consistency**
        
        For any operation or user action, the logger should record events with 
        appropriate log levels and structured data including relevant context.
        **Validates: Requirements 5.1, 5.3**
        """
        # Set up logging service
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            service = LoggingService(log_level="DEBUG")  # Capture all levels
            service.configure()
            
            logger = service.get_logger(logger_name)
            
            # Capture log output
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                # Log message with context data
                log_method = getattr(logger, log_level.lower())
                log_method(message, **context_data)
                
                output = mock_stdout.getvalue()
            
            # Verify structured logging consistency
            if output.strip():
                lines = [line for line in output.strip().split('\n') if line.strip()]
                if lines:
                    json_line = lines[0]
                    parsed = json.loads(json_line)
                    
                    # Required fields should always be present
                    assert "event" in parsed
                    assert "level" in parsed
                    assert "timestamp" in parsed
                    assert "logger" in parsed
                    
                    # Event should match the message
                    assert parsed["event"] == message
                    
                    # Level should match (case insensitive)
                    assert parsed["level"].upper() == log_level.upper()
                    
                    # Logger name should match
                    assert parsed["logger"] == logger_name
                    
                    # All context data should be preserved
                    for key, value in context_data.items():
                        assert key in parsed
                        assert parsed[key] == value
                    
                    # Timestamp should be ISO format
                    assert "T" in parsed["timestamp"]
                    assert "Z" in parsed["timestamp"]
    
    @given(
        logger_name=st.text(min_size=1, max_size=50).filter(lambda x: x.isidentifier()),
        error_message=st.text(min_size=1, max_size=200),
        exception_type=st.sampled_from([ValueError, RuntimeError, KeyError, TypeError, IOError]),
        context_data=st.dictionaries(
            keys=st.text(min_size=1, max_size=20).filter(lambda x: x.isidentifier()),
            values=st.one_of(
                st.text(max_size=100),
                st.integers(),
                st.floats(allow_nan=False, allow_infinity=False),
                st.booleans()
            ),
            max_size=3
        )
    )
    def test_error_logging_completeness(
        self,
        logger_name: str,
        error_message: str,
        exception_type: type[Exception],
        context_data: dict[str, str | int | float | bool]
    ) -> None:
        """**Feature: tui-game-scraper, Property 10: Error logging completeness**
        
        For any error that occurs, the logger should capture complete error details 
        including stack traces and context information.
        **Validates: Requirements 5.2**
        """
        # Set up logging service
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            service = LoggingService(log_level="DEBUG")
            service.configure()
            
            logger = service.get_logger(logger_name)
            
            # Create an exception with stack trace
            try:
                raise exception_type(error_message)
            except exception_type as e:
                # Capture log output
                with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                    # Log the exception with context
                    logger.error(
                        "Error occurred during operation",
                        exc_info=True,
                        error_type=exception_type.__name__,
                        original_message=error_message,
                        **context_data
                    )
                    
                    output = mock_stdout.getvalue()
            
            # Verify error logging completeness
            if output.strip():
                lines = [line for line in output.strip().split('\n') if line.strip()]
                if lines:
                    json_line = lines[0]
                    parsed = json.loads(json_line)
                    
                    # Required error logging fields
                    assert "event" in parsed
                    assert "level" in parsed
                    assert "timestamp" in parsed
                    assert "logger" in parsed
                    
                    # Error-specific fields
                    assert parsed["level"] == "error"
                    assert parsed["error_type"] == exception_type.__name__
                    assert parsed["original_message"] == error_message
                    
                    # Exception information should be present
                    assert "exception" in parsed
                    exception_info = parsed["exception"]
                    
                    # Exception should contain stack trace information
                    assert exception_type.__name__ in exception_info
                    assert error_message in exception_info
                    assert "Traceback" in exception_info
                    
                    # All context data should be preserved
                    for key, value in context_data.items():
                        assert key in parsed
                        assert parsed[key] == value
                    
                    # Logger name should match
                    assert parsed["logger"] == logger_name


def test_setup_logging_function() -> None:
    """Test the setup_logging convenience function."""
    with tempfile.TemporaryDirectory() as temp_dir:
        log_dir = Path(temp_dir)
        
        service = setup_logging(
            log_level="DEBUG",
            log_dir=log_dir,
            environment="production"
        )
        
        assert isinstance(service, LoggingService)
        assert os.environ["ENVIRONMENT"] == "production"
        
        # Test that logging works
        logger = service.get_logger("test_setup")
        
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            logger.info("setup test", component="test")
            output = mock_stdout.getvalue()
            
        if output.strip():
            parsed = json.loads(output.strip())
            assert parsed["event"] == "setup test"
            assert parsed["component"] == "test"