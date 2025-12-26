"""File system service for data persistence and file management."""

import json
import shutil
from pathlib import Path
from typing import Any
import os

import structlog

from .errors import FileSystemError as FSError, get_error_service

log = structlog.stdlib.get_logger()


class FileSystemService:
    """Service for file system operations with error handling and validation."""
    
    def __init__(self, base_path: Path | None = None) -> None:
        """Initialize the file system service.
        
        Args:
            base_path: Base directory for operations (defaults to current working directory)
        """
        self.base_path = base_path or Path.cwd()
        log.info("File system service initialized", base_path=str(self.base_path))
    
    async def save_json(self, data: dict[str, Any], path: Path) -> None:
        """Save data as JSON to the specified path.
        
        Args:
            data: Dictionary to save as JSON
            path: Path to save the file
            
        Raises:
            OSError: If file cannot be written
            ValueError: If data cannot be serialized to JSON
            PermissionError: If insufficient permissions
        """
        try:
            # Ensure parent directory exists
            self.ensure_directory(path.parent)
            
            # Write to temporary file first, then move to final location
            # This ensures atomic writes and prevents corruption
            temp_path = path.with_suffix(path.suffix + ".tmp")
            
            log.debug("Saving JSON data", path=str(path), temp_path=str(temp_path))
            
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)
            
            # Atomic move to final location
            temp_path.replace(path)
            
            log.info("JSON data saved successfully", path=str(path), size=path.stat().st_size)
            
        except (OSError, PermissionError) as e:
            log.error("Failed to save JSON data", path=str(path), error=str(e))
            # Clean up temporary file if it exists
            if 'temp_path' in locals() and temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            raise
        except (TypeError, ValueError) as e:
            log.error("Failed to serialize data to JSON", path=str(path), error=str(e))
            # Clean up temporary file if it exists
            if 'temp_path' in locals() and temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            raise ValueError(f"Cannot serialize data to JSON: {e}") from e
    
    async def load_json(self, path: Path) -> dict[str, Any]:
        """Load JSON data from the specified path.
        
        Args:
            path: Path to load the file from
            
        Returns:
            Dictionary loaded from JSON
            
        Raises:
            FileNotFoundError: If file does not exist
            OSError: If file cannot be read
            ValueError: If file contains invalid JSON
            PermissionError: If insufficient permissions
        """
        try:
            log.debug("Loading JSON data", path=str(path))
            
            if not path.exists():
                log.error("JSON file not found", path=str(path))
                raise FileNotFoundError(f"File not found: {path}")
            
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            log.info("JSON data loaded successfully", path=str(path), keys=list(data.keys()) if isinstance(data, dict) else "non-dict")
            
            if not isinstance(data, dict):
                raise ValueError(f"Expected JSON object (dict), got {type(data).__name__}")
            
            return data
            
        except (OSError, PermissionError) as e:
            log.error("Failed to read JSON file", path=str(path), error=str(e))
            raise
        except json.JSONDecodeError as e:
            log.error("Invalid JSON in file", path=str(path), error=str(e))
            raise ValueError(f"Invalid JSON in file {path}: {e}") from e
    
    def ensure_directory(self, path: Path) -> None:
        """Ensure that a directory exists, creating it if necessary.
        
        Args:
            path: Directory path to ensure exists
            
        Raises:
            OSError: If directory cannot be created
            PermissionError: If insufficient permissions
        """
        try:
            if path.exists():
                if not path.is_dir():
                    log.error("Path exists but is not a directory", path=str(path))
                    raise OSError(f"Path exists but is not a directory: {path}")
                return
            
            log.debug("Creating directory", path=str(path))
            path.mkdir(parents=True, exist_ok=True)
            log.info("Directory created successfully", path=str(path))
            
        except (OSError, PermissionError) as e:
            log.error("Failed to create directory", path=str(path), error=str(e))
            raise
    
    def get_file_size(self, path: Path) -> int:
        """Get the size of a file in bytes.
        
        Args:
            path: Path to the file
            
        Returns:
            File size in bytes
            
        Raises:
            FileNotFoundError: If file does not exist
            OSError: If file cannot be accessed
        """
        try:
            if not path.exists():
                raise FileNotFoundError(f"File not found: {path}")
            
            if not path.is_file():
                raise OSError(f"Path is not a file: {path}")
            
            size = path.stat().st_size
            log.debug("Retrieved file size", path=str(path), size=size)
            return size
            
        except (OSError, PermissionError) as e:
            log.error("Failed to get file size", path=str(path), error=str(e))
            raise
    
    def get_available_space(self, path: Path) -> int:
        """Get available disk space for the given path.
        
        Args:
            path: Path to check (can be file or directory)
            
        Returns:
            Available space in bytes
            
        Raises:
            OSError: If disk space cannot be determined
        """
        try:
            # Get the directory containing the path
            if path.is_file():
                check_path = path.parent
            else:
                check_path = path
            
            # Ensure the directory exists for the check
            if not check_path.exists():
                check_path = check_path.parent
                while not check_path.exists() and check_path != check_path.parent:
                    check_path = check_path.parent
            
            stat = shutil.disk_usage(check_path)
            available_space = stat.free
            
            log.debug(
                "Retrieved disk space information",
                path=str(path),
                check_path=str(check_path),
                available_bytes=available_space,
                available_mb=available_space // (1024 * 1024)
            )
            
            return available_space
            
        except OSError as e:
            log.error("Failed to get available disk space", path=str(path), error=str(e))
            raise
    
    def check_write_permission(self, path: Path) -> bool:
        """Check if we have write permission for the given path.
        
        Args:
            path: Path to check (can be file or directory)
            
        Returns:
            True if we have write permission, False otherwise
        """
        try:
            if path.exists():
                # Check existing path
                return path.is_dir() and os.access(path, os.W_OK) or path.is_file() and os.access(path.parent, os.W_OK)
            else:
                # Check parent directory for new files
                parent = path.parent
                while not parent.exists() and parent != parent.parent:
                    parent = parent.parent
                
                import os
                has_permission = os.access(parent, os.W_OK)
                log.debug("Checked write permission", path=str(path), parent=str(parent), has_permission=has_permission)
                return has_permission
                
        except OSError as e:
            log.warning("Failed to check write permission", path=str(path), error=str(e))
            return False
    
    def delete_file(self, path: Path) -> None:
        """Delete a file safely.
        
        Args:
            path: Path to the file to delete
            
        Raises:
            FileNotFoundError: If file does not exist
            OSError: If file cannot be deleted
            PermissionError: If insufficient permissions
        """
        try:
            if not path.exists():
                log.warning("Attempted to delete non-existent file", path=str(path))
                raise FileNotFoundError(f"File not found: {path}")
            
            if not path.is_file():
                log.error("Attempted to delete non-file", path=str(path))
                raise OSError(f"Path is not a file: {path}")
            
            log.debug("Deleting file", path=str(path))
            path.unlink()
            log.info("File deleted successfully", path=str(path))
            
        except (OSError, PermissionError) as e:
            log.error("Failed to delete file", path=str(path), error=str(e))
            raise
    
    def move_file(self, source: Path, destination: Path) -> None:
        """Move a file from source to destination.
        
        Args:
            source: Source file path
            destination: Destination file path
            
        Raises:
            FileNotFoundError: If source file does not exist
            OSError: If file cannot be moved
            PermissionError: If insufficient permissions
        """
        try:
            if not source.exists():
                log.error("Source file not found for move", source=str(source))
                raise FileNotFoundError(f"Source file not found: {source}")
            
            if not source.is_file():
                log.error("Source is not a file", source=str(source))
                raise OSError(f"Source is not a file: {source}")
            
            # Ensure destination directory exists
            self.ensure_directory(destination.parent)
            
            log.debug("Moving file", source=str(source), destination=str(destination))
            source.replace(destination)
            log.info("File moved successfully", source=str(source), destination=str(destination))
            
        except (OSError, PermissionError) as e:
            log.error("Failed to move file", source=str(source), destination=str(destination), error=str(e))
            raise
    
    def list_files(self, directory: Path, pattern: str = "*", recursive: bool = False) -> list[Path]:
        """List files in a directory matching a pattern.
        
        Args:
            directory: Directory to search in
            pattern: Glob pattern to match (default: "*")
            recursive: Whether to search recursively (default: False)
            
        Returns:
            List of matching file paths
            
        Raises:
            FileNotFoundError: If directory does not exist
            OSError: If directory cannot be accessed
        """
        try:
            if not directory.exists():
                log.error("Directory not found for listing", directory=str(directory))
                raise FileNotFoundError(f"Directory not found: {directory}")
            
            if not directory.is_dir():
                log.error("Path is not a directory", directory=str(directory))
                raise OSError(f"Path is not a directory: {directory}")
            
            if recursive:
                files = list(directory.rglob(pattern))
            else:
                files = list(directory.glob(pattern))
            
            # Filter to only include files (not directories)
            file_paths = [f for f in files if f.is_file()]
            
            log.debug(
                "Listed files in directory",
                directory=str(directory),
                pattern=pattern,
                recursive=recursive,
                count=len(file_paths)
            )
            
            return file_paths
            
        except (OSError, PermissionError) as e:
            log.error("Failed to list files", directory=str(directory), error=str(e))
            raise