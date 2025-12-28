"""HTTP client service with retry logic and rate limiting."""

import asyncio
from pathlib import Path
from typing import Any

import httpx
import structlog

from .errors import NetworkError, get_error_service

log = structlog.stdlib.get_logger()


class HttpClientService:
    """HTTP client service with retry logic, rate limiting, and timeout handling."""
    
    def __init__(
        self,
        timeout: float = 30.0,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        rate_limit_delay: float = 1.0,
        verify_ssl: bool = True
    ) -> None:
        """Initialize the HTTP client service.
        
        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            base_delay: Base delay for exponential backoff in seconds
            max_delay: Maximum delay between retries in seconds
            rate_limit_delay: Minimum delay between requests in seconds
            verify_ssl: Whether to verify SSL certificates (disable for macOS cert issues)
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.rate_limit_delay = rate_limit_delay
        self._last_request_time: float = 0.0
        
        # Configure HTTP client with reasonable defaults
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            headers={
                "User-Agent": "TUI-Game-Scraper/1.0 (Educational Purpose)"
            },
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            verify=verify_ssl
        )
        
        log.info(
            "HTTP client service initialized",
            timeout=timeout,
            max_retries=max_retries,
            rate_limit_delay=rate_limit_delay,
            verify_ssl=verify_ssl
        )
    
    async def get(
        self, 
        url: str, 
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None
    ) -> httpx.Response:
        """Make a GET request with retry logic and rate limiting.
        
        Args:
            url: The URL to request
            headers: Optional additional headers
            params: Optional query parameters
            
        Returns:
            HTTP response object
            
        Raises:
            httpx.HTTPError: If all retry attempts fail
            httpx.TimeoutException: If request times out after all retries
        """
        await self._enforce_rate_limit()
        
        merged_headers = self._client.headers.copy()
        if headers:
            merged_headers.update(headers)
        
        for attempt in range(self.max_retries + 1):
            try:
                log.debug(
                    "Making HTTP GET request",
                    url=url,
                    attempt=attempt + 1,
                    max_attempts=self.max_retries + 1
                )
                
                response = await self._client.get(
                    url,
                    headers=merged_headers,
                    params=params
                )
                
                # Check for HTTP errors
                response.raise_for_status()
                
                log.info(
                    "HTTP GET request successful",
                    url=url,
                    status_code=response.status_code,
                    content_length=len(response.content)
                )
                
                return response
                
            except (httpx.HTTPStatusError, httpx.RequestError, httpx.TimeoutException) as e:
                log.warning(
                    "HTTP GET request failed",
                    url=url,
                    attempt=attempt + 1,
                    error=str(e),
                    error_type=type(e).__name__
                )
                
                # Don't retry on client errors (4xx) except for rate limiting
                if isinstance(e, httpx.HTTPStatusError):
                    if e.response.status_code == 429:  # Too Many Requests
                        # Extract retry-after header if available
                        retry_after = e.response.headers.get("retry-after")
                        if retry_after:
                            try:
                                delay = float(retry_after)
                                log.info("Rate limited, waiting", delay=delay)
                                await asyncio.sleep(delay)
                                continue
                            except ValueError:
                                pass
                    elif 400 <= e.response.status_code < 500:
                        log.error("Client error, not retrying", status_code=e.response.status_code)
                        raise
                
                # If this was the last attempt, raise the exception
                if attempt == self.max_retries:
                    log.error(
                        "HTTP GET request failed after all retries",
                        url=url,
                        total_attempts=self.max_retries + 1
                    )
                    raise
                
                # Calculate exponential backoff delay
                delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                log.info("Retrying after delay", delay=delay)
                await asyncio.sleep(delay)
        
        # This should never be reached, but satisfy type checker
        raise RuntimeError("Unexpected end of retry loop")
    
    async def download_file(
        self,
        url: str,
        path: Path,
        headers: dict[str, str] | None = None,
        chunk_size: int = 8192
    ) -> None:
        """Download a file with retry logic and progress tracking.
        
        Args:
            url: The URL to download from
            path: Local path to save the file
            headers: Optional additional headers
            chunk_size: Size of chunks to read/write in bytes
            
        Raises:
            httpx.HTTPError: If all retry attempts fail
            OSError: If file cannot be written
        """
        await self._enforce_rate_limit()
        
        merged_headers = self._client.headers.copy()
        if headers:
            merged_headers.update(headers)
        
        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)
        
        for attempt in range(self.max_retries + 1):
            try:
                log.debug(
                    "Starting file download",
                    url=url,
                    path=str(path),
                    attempt=attempt + 1
                )
                
                async with self._client.stream(
                    "GET",
                    url,
                    headers=merged_headers
                ) as response:
                    response.raise_for_status()
                    
                    total_size = int(response.headers.get("content-length", 0))
                    downloaded = 0
                    
                    with open(path, "wb") as f:
                        async for chunk in response.aiter_bytes(chunk_size):
                            f.write(chunk)
                            downloaded += len(chunk)
                    
                    log.info(
                        "File download completed",
                        url=url,
                        path=str(path),
                        size=downloaded,
                        expected_size=total_size
                    )
                    
                    # Verify file size if content-length was provided
                    if total_size > 0 and downloaded != total_size:
                        log.warning(
                            "Downloaded file size mismatch",
                            expected=total_size,
                            actual=downloaded
                        )
                        raise httpx.RequestError(
                            f"File size mismatch: expected {total_size}, got {downloaded}"
                        )
                    
                    return
                    
            except (httpx.HTTPStatusError, httpx.RequestError, httpx.TimeoutException, OSError) as e:
                log.warning(
                    "File download failed",
                    url=url,
                    path=str(path),
                    attempt=attempt + 1,
                    error=str(e),
                    error_type=type(e).__name__
                )
                
                # Clean up partial file on error
                if path.exists():
                    try:
                        path.unlink()
                        log.debug("Cleaned up partial download", path=str(path))
                    except OSError:
                        log.warning("Failed to clean up partial download", path=str(path))
                
                # Handle rate limiting
                if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 429:
                    retry_after = e.response.headers.get("retry-after")
                    if retry_after:
                        try:
                            delay = float(retry_after)
                            log.info("Rate limited during download, waiting", delay=delay)
                            await asyncio.sleep(delay)
                            continue
                        except ValueError:
                            pass
                
                # Don't retry on client errors (except rate limiting) or file system errors
                if isinstance(e, httpx.HTTPStatusError) and 400 <= e.response.status_code < 500:
                    if e.response.status_code != 429:
                        log.error("Client error during download, not retrying", status_code=e.response.status_code)
                        raise
                elif isinstance(e, OSError):
                    log.error("File system error during download, not retrying", error=str(e))
                    raise
                
                # If this was the last attempt, raise the exception
                if attempt == self.max_retries:
                    log.error(
                        "File download failed after all retries",
                        url=url,
                        path=str(path),
                        total_attempts=self.max_retries + 1
                    )
                    raise
                
                # Calculate exponential backoff delay
                delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                log.info("Retrying download after delay", delay=delay)
                await asyncio.sleep(delay)
        
        # This should never be reached, but satisfy type checker
        raise RuntimeError("Unexpected end of retry loop")
    
    async def _enforce_rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        import time
        
        current_time = time.time()
        time_since_last = current_time - self._last_request_time
        
        if time_since_last < self.rate_limit_delay:
            sleep_time = self.rate_limit_delay - time_since_last
            log.debug("Rate limiting: sleeping", sleep_time=sleep_time)
            await asyncio.sleep(sleep_time)
        
        self._last_request_time = time.time()
    
    async def close(self) -> None:
        """Close the HTTP client and clean up resources."""
        await self._client.aclose()
        log.info("HTTP client closed")
    
    async def __aenter__(self) -> "HttpClientService":
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type: type[Exception] | None, exc_val: Exception | None, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()