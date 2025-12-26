"""Property-based tests for error handling across HTTP client and file system services."""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from hypothesis import given, strategies as st, settings

from src.services import FileSystemService, HttpClientService


class TestErrorHandlingProperties:
    """Property-based tests for user-friendly error handling."""
    
    @given(
        url=st.text(min_size=10, max_size=100).map(lambda x: f"https://example.com/{x.replace('/', '_')}"),
        error_type=st.sampled_from([
            "network_error",
            "timeout_error", 
            "http_4xx_error",
            "http_5xx_error"
        ]),
        error_message=st.text(min_size=5, max_size=100)
    )
    @pytest.mark.asyncio
    @settings(deadline=None)  # Disable deadline for this test due to HTTP client setup/teardown
    async def test_http_client_user_friendly_error_messages(
        self,
        url: str,
        error_type: str,
        error_message: str
    ) -> None:
        """**Feature: tui-game-scraper, Property 11: User-friendly error messages**
        
        For any type of error (network, file system, validation, unexpected), 
        the application should display user-friendly error messages while 
        logging detailed technical information.
        **Validates: Requirements 7.1, 7.2, 7.3, 7.4**
        """
        client = HttpClientService(timeout=1.0, max_retries=1)
        
        # Mock different types of HTTP errors
        if error_type == "network_error":
            mock_error = httpx.ConnectError(error_message)
        elif error_type == "timeout_error":
            mock_error = httpx.TimeoutException(error_message)
        elif error_type == "http_4xx_error":
            mock_response = Mock()
            mock_response.status_code = 404
            mock_error = httpx.HTTPStatusError(error_message, request=Mock(), response=mock_response)
        elif error_type == "http_5xx_error":
            mock_response = Mock()
            mock_response.status_code = 500
            mock_error = httpx.HTTPStatusError(error_message, request=Mock(), response=mock_response)
        else:
            mock_error = httpx.RequestError(error_message)
        
        # Mock the HTTP client to raise the error
        with patch.object(client._client, 'get', side_effect=mock_error):
            # Capture log output by patching the module-level logger
            with patch('src.services.http_client.log') as mock_logger:
                # The error should be raised (user-friendly error handling)
                with pytest.raises((httpx.HTTPError, httpx.TimeoutException)):
                    await client.get(url)
                
                # Verify that detailed technical information was logged
                # The service should log warnings/errors with technical details
                assert mock_logger.warning.called or mock_logger.error.called
                
                # Check that log calls contain technical details
                log_calls = mock_logger.warning.call_args_list + mock_logger.error.call_args_list
                assert len(log_calls) > 0
                
                # Verify technical details are in the logs
                found_technical_details = False
                for call in log_calls:
                    args, kwargs = call
                    # Check if technical error information is logged
                    if ('error' in kwargs or 'error_type' in kwargs or 
                        'url' in kwargs or 'attempt' in kwargs):
                        found_technical_details = True
                        break
                
                assert found_technical_details, "Technical error details should be logged"
        
        await client.close()
    
    @given(
        # Generate safe file names using only ASCII alphanumeric characters
        file_name=st.text(min_size=5, max_size=20, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"))).map(lambda x: x or "test"),
        error_type=st.sampled_from([
            "permission_error",
            "file_not_found",
            "invalid_json"
        ]),
        test_data=st.dictionaries(
            keys=st.text(min_size=1, max_size=20).filter(lambda x: x.isidentifier()),
            values=st.one_of(
                st.text(max_size=50),
                st.integers(),
                st.booleans()
            ),
            min_size=1,
            max_size=5
        )
    )
    def test_filesystem_user_friendly_error_messages(
        self,
        file_name: str,
        error_type: str,
        test_data: dict[str, str | int | bool]
    ) -> None:
        """**Feature: tui-game-scraper, Property 11: User-friendly error messages**
        
        For any type of file system error, the application should display 
        user-friendly error messages while logging detailed technical information.
        **Validates: Requirements 7.1, 7.2, 7.3, 7.4**
        """
        service = FileSystemService()
        
        # Use a safe temporary directory path
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / f"{file_name}.json"
            
            # Capture log output by patching the module-level logger
            with patch('src.services.filesystem.log') as mock_logger:
                if error_type == "permission_error":
                    # Mock permission error during file operations
                    with patch('builtins.open', side_effect=PermissionError("Permission denied")):
                        with pytest.raises(PermissionError):
                            asyncio.run(service.save_json(test_data, file_path))
                        
                        # Verify technical details are logged
                        assert mock_logger.error.called
                        error_calls = mock_logger.error.call_args_list
                        assert any('error' in call.kwargs for call in error_calls)
                        
                elif error_type == "file_not_found":
                    # Test loading non-existent file
                    non_existent_path = Path(temp_dir) / "definitely_does_not_exist_12345.json"
                    
                    with pytest.raises(FileNotFoundError):
                        asyncio.run(service.load_json(non_existent_path))
                    
                    # Verify technical details are logged
                    assert mock_logger.error.called
                    error_calls = mock_logger.error.call_args_list
                    assert any('path' in call.kwargs for call in error_calls)
                    
                elif error_type == "invalid_json":
                    # Create a file with invalid JSON
                    invalid_json_path = Path(temp_dir) / f"invalid_{file_name}.json"
                    with open(invalid_json_path, 'w') as f:
                        f.write("{ invalid json content")
                    
                    try:
                        with pytest.raises(ValueError) as exc_info:
                            asyncio.run(service.load_json(invalid_json_path))
                        
                        # Error message should be user-friendly
                        assert "Invalid JSON" in str(exc_info.value)
                        assert str(invalid_json_path) in str(exc_info.value)
                        
                        # Verify technical details are logged
                        assert mock_logger.error.called
                        error_calls = mock_logger.error.call_args_list
                        assert any('error' in call.kwargs for call in error_calls)
                        
                    finally:
                        invalid_json_path.unlink(missing_ok=True)
    
    @given(
        # Generate safe file names
        file_name=st.text(min_size=5, max_size=20, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"))).map(lambda x: x or "test")
    )
    def test_validation_error_messages(
        self,
        file_name: str
    ) -> None:
        """**Feature: tui-game-scraper, Property 11: User-friendly error messages**
        
        For validation errors, the application should provide clear error messages
        explaining what went wrong and how to fix it.
        **Validates: Requirements 7.1, 7.2, 7.3, 7.4**
        """
        service = FileSystemService()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / f"{file_name}.json"
            
            # Capture log output by patching the module-level logger
            with patch('src.services.filesystem.log') as mock_logger:
                # Try to save non-serializable data
                with pytest.raises(ValueError) as exc_info:
                    # Create data with non-serializable object
                    invalid_data = {"invalid_object": object()}
                    asyncio.run(service.save_json(invalid_data, file_path))
                
                # Error message should be user-friendly and informative
                error_message = str(exc_info.value)
                assert "Cannot serialize data to JSON" in error_message
                
                # Verify technical details are logged
                assert mock_logger.error.called
                error_calls = mock_logger.error.call_args_list
                assert any('error' in call.kwargs for call in error_calls)
    
    def test_error_recovery_state_consistency_example(self) -> None:
        """Unit test example for error recovery state consistency.
        
        This tests that after an error occurs and is handled, the application
        returns to a stable state without data loss or corruption.
        """
        service = FileSystemService()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = Path(temp_dir) / "test.json"
            valid_data = {"key": "value", "number": 42}
            
            # First, save valid data successfully
            asyncio.run(service.save_json(valid_data, test_file))
            assert test_file.exists()
            
            # Verify the data was saved correctly
            loaded_data = asyncio.run(service.load_json(test_file))
            assert loaded_data == valid_data
            
            # Now try to save invalid data (should fail but not corrupt existing file)
            invalid_data = {"function": lambda x: x}  # Non-serializable
            
            with pytest.raises(ValueError):
                asyncio.run(service.save_json(invalid_data, test_file))
            
            # After the error, the original file should still exist and be valid
            assert test_file.exists()
            recovered_data = asyncio.run(service.load_json(test_file))
            assert recovered_data == valid_data  # No data loss
            
            # The service should still be functional for new operations
            new_valid_data = {"after_error": "still_works", "count": 123}
            new_file = Path(temp_dir) / "after_error.json"
            
            asyncio.run(service.save_json(new_valid_data, new_file))
            assert new_file.exists()
            
            final_data = asyncio.run(service.load_json(new_file))
            assert final_data == new_valid_data


class TestHttpClientErrorHandlingExamples:
    """Unit test examples for HTTP client error handling."""
    
    @pytest.mark.asyncio
    async def test_network_error_handling(self) -> None:
        """Test that network errors are handled gracefully."""
        client = HttpClientService(timeout=1.0, max_retries=1)
        
        with patch.object(client._client, 'get', side_effect=httpx.ConnectError("Connection failed")):
            with pytest.raises(httpx.ConnectError):
                await client.get("https://example.com/test")
        
        await client.close()
    
    @pytest.mark.asyncio
    async def test_http_status_error_handling(self) -> None:
        """Test that HTTP status errors are handled appropriately."""
        client = HttpClientService(timeout=1.0, max_retries=1)
        
        # Mock 404 error
        mock_response = Mock()
        mock_response.status_code = 404
        error = httpx.HTTPStatusError("Not found", request=Mock(), response=mock_response)
        
        with patch.object(client._client, 'get', side_effect=error):
            with pytest.raises(httpx.HTTPStatusError):
                await client.get("https://example.com/nonexistent")
        
        await client.close()
    
    @pytest.mark.asyncio
    async def test_rate_limiting_handling(self) -> None:
        """Test that rate limiting (429) is handled with retry."""
        client = HttpClientService(timeout=1.0, max_retries=2, base_delay=0.1)
        
        # Mock 429 error with retry-after header
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.headers = {"retry-after": "0.1"}
        
        call_count = 0
        
        def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:  # Fail first two attempts
                raise httpx.HTTPStatusError("Rate limited", request=Mock(), response=mock_response)
            else:  # Succeed on third attempt
                success_response = Mock()
                success_response.status_code = 200
                success_response.content = b"success"  # Add content attribute
                success_response.raise_for_status = Mock()
                return success_response
        
        with patch.object(client._client, 'get', side_effect=mock_get):
            response = await client.get("https://example.com/rate-limited")
            assert response.status_code == 200
            assert call_count == 3  # Should have retried twice
        
        await client.close()


class TestFileSystemErrorHandlingExamples:
    """Unit test examples for file system error handling."""
    
    def test_permission_error_handling(self) -> None:
        """Test that permission errors are handled gracefully."""
        service = FileSystemService()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = Path(temp_dir) / "test.json"
            
            # Try to write to a path that would cause permission error
            with patch('builtins.open', side_effect=PermissionError("Permission denied")):
                with pytest.raises(PermissionError):
                    asyncio.run(service.save_json({"test": "data"}, test_file))
    
    def test_invalid_json_error_handling(self) -> None:
        """Test that invalid JSON files are handled gracefully."""
        service = FileSystemService()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / "invalid.json"
            
            with open(temp_path, 'w') as f:
                f.write("{ this is not valid json }")
            
            try:
                with pytest.raises(ValueError) as exc_info:
                    asyncio.run(service.load_json(temp_path))
                
                # Should provide user-friendly error message
                assert "Invalid JSON" in str(exc_info.value)
                assert str(temp_path) in str(exc_info.value)
                
            finally:
                temp_path.unlink(missing_ok=True)
    
    def test_file_not_found_error_handling(self) -> None:
        """Test that missing files are handled gracefully."""
        service = FileSystemService()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            non_existent = Path(temp_dir) / "definitely_does_not_exist_12345.json"
            
            with pytest.raises(FileNotFoundError) as exc_info:
                asyncio.run(service.load_json(non_existent))
            
            # Should provide clear error message
            assert str(non_existent) in str(exc_info.value)


class TestErrorRecoveryStateConsistency:
    """Property-based tests for error recovery state consistency.
    
    **Feature: tui-game-scraper, Property 12: Error recovery state consistency**
    **Validates: Requirements 7.5**
    """
    
    @given(
        # Generate valid JSON-serializable data
        initial_data=st.dictionaries(
            keys=st.text(min_size=1, max_size=20).filter(lambda x: x.isidentifier()),
            values=st.one_of(
                st.text(max_size=50),
                st.integers(min_value=-1000000, max_value=1000000),
                st.booleans(),
                st.floats(allow_nan=False, allow_infinity=False),
            ),
            min_size=1,
            max_size=10
        ),
        # Generate safe file names
        file_name=st.text(
            min_size=3, 
            max_size=20, 
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"))
        ).filter(lambda x: len(x) >= 3),
    )
    @settings(deadline=None, max_examples=100)
    def test_error_recovery_preserves_existing_data(
        self,
        initial_data: dict[str, str | int | bool | float],
        file_name: str,
    ) -> None:
        """**Feature: tui-game-scraper, Property 12: Error recovery state consistency**
        
        For any valid data that has been successfully saved, if a subsequent
        save operation fails, the original data should remain intact and
        accessible without corruption.
        
        **Validates: Requirements 7.5**
        """
        service = FileSystemService()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = Path(temp_dir) / f"{file_name}.json"
            
            # Step 1: Save valid data successfully
            asyncio.run(service.save_json(dict(initial_data), test_file))
            assert test_file.exists(), "Initial save should succeed"
            
            # Step 2: Verify the data was saved correctly
            loaded_data = asyncio.run(service.load_json(test_file))
            assert loaded_data == initial_data, "Loaded data should match saved data"
            
            # Step 3: Attempt to save invalid data (should fail)
            invalid_data = {"function": lambda x: x}  # Non-serializable
            
            with pytest.raises(ValueError):
                asyncio.run(service.save_json(invalid_data, test_file))
            
            # Step 4: Verify original data is still intact (no corruption)
            assert test_file.exists(), "File should still exist after failed save"
            recovered_data = asyncio.run(service.load_json(test_file))
            assert recovered_data == initial_data, "Original data should be preserved after error"
    
    @given(
        # Generate valid JSON-serializable data
        data_items=st.lists(
            st.dictionaries(
                keys=st.text(min_size=1, max_size=15).filter(lambda x: x.isidentifier()),
                values=st.one_of(
                    st.text(max_size=30),
                    st.integers(min_value=-10000, max_value=10000),
                    st.booleans(),
                ),
                min_size=1,
                max_size=5
            ),
            min_size=2,
            max_size=5
        ),
        # Generate safe file names
        file_name=st.text(
            min_size=3, 
            max_size=20, 
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"))
        ).filter(lambda x: len(x) >= 3),
    )
    @settings(deadline=None, max_examples=100)
    def test_service_remains_functional_after_error(
        self,
        data_items: list[dict[str, str | int | bool]],
        file_name: str,
    ) -> None:
        """**Feature: tui-game-scraper, Property 12: Error recovery state consistency**
        
        For any sequence of operations where an error occurs, the service
        should remain functional for subsequent valid operations.
        
        **Validates: Requirements 7.5**
        """
        service = FileSystemService()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Step 1: Perform some successful operations
            for i, data in enumerate(data_items[:len(data_items)//2]):
                file_path = Path(temp_dir) / f"{file_name}_{i}.json"
                asyncio.run(service.save_json(dict(data), file_path))
                assert file_path.exists()
            
            # Step 2: Cause an error (try to save non-serializable data)
            error_file = Path(temp_dir) / f"{file_name}_error.json"
            with pytest.raises(ValueError):
                asyncio.run(service.save_json({"bad": object()}, error_file))
            
            # Step 3: Service should still be functional for new operations
            for i, data in enumerate(data_items[len(data_items)//2:]):
                file_path = Path(temp_dir) / f"{file_name}_after_{i}.json"
                asyncio.run(service.save_json(dict(data), file_path))
                assert file_path.exists()
                
                # Verify data integrity
                loaded = asyncio.run(service.load_json(file_path))
                assert loaded == data, "Data should be correctly saved after error recovery"
    
    @given(
        # Generate valid JSON-serializable data
        valid_data=st.dictionaries(
            keys=st.text(min_size=1, max_size=20).filter(lambda x: x.isidentifier()),
            values=st.one_of(
                st.text(max_size=50),
                st.integers(min_value=-1000000, max_value=1000000),
                st.booleans(),
            ),
            min_size=1,
            max_size=10
        ),
        # Generate safe file names
        file_name=st.text(
            min_size=3, 
            max_size=20, 
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"))
        ).filter(lambda x: len(x) >= 3),
    )
    @settings(deadline=None, max_examples=100)
    def test_error_handling_service_state_consistency(
        self,
        valid_data: dict[str, str | int | bool],
        file_name: str,
    ) -> None:
        """**Feature: tui-game-scraper, Property 12: Error recovery state consistency**
        
        For any error that is handled by the error handling service, the
        service should maintain consistent internal state and be able to
        handle subsequent errors correctly.
        
        **Validates: Requirements 7.5**
        """
        from src.services.errors import ErrorHandlingService, ErrorCategory
        
        error_service = ErrorHandlingService()
        
        # Step 1: Handle various types of errors
        errors_to_handle = [
            ValueError("Test validation error"),
            FileNotFoundError("Test file not found"),
            PermissionError("Test permission denied"),
            OSError("Test OS error"),
        ]
        
        for error in errors_to_handle:
            user_error = error_service.handle_error(
                error=error,
                operation="test_operation",
                component="test_component",
                context={"test_key": "test_value"},
            )
            
            # Verify user-friendly error was created
            assert user_error.message, "Error should have a message"
            assert user_error.category in ErrorCategory, "Error should have valid category"
            assert user_error.recoverable is True, "Errors should be marked as recoverable"
        
        # Step 2: Verify error history is maintained correctly
        recent_errors = error_service.get_recent_errors(count=10)
        assert len(recent_errors) == len(errors_to_handle), "All errors should be in history"
        
        # Step 3: Verify error counts by category
        counts = error_service.get_error_count_by_category()
        total_count = sum(counts.values())
        assert total_count == len(errors_to_handle), "Total count should match errors handled"
        
        # Step 4: Service should still be functional
        new_error = RuntimeError("New error after recovery")
        new_user_error = error_service.handle_error(
            error=new_error,
            operation="new_operation",
            component="new_component",
        )
        assert new_user_error.message, "Service should handle new errors after recovery"
        
        # Step 5: Verify history was updated
        updated_errors = error_service.get_recent_errors(count=10)
        assert len(updated_errors) == len(errors_to_handle) + 1