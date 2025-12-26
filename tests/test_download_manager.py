"""Property-based tests for download manager service."""

import asyncio
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given, strategies as st, settings, assume

from src.models import DiscInfo, DownloadProgress, GameData
from src.services.download_manager import (
    DownloadManagerService,
    DownloadStatus,
    DownloadTask,
    QueueStatus,
)
from src.services.http_client import HttpClientService
from src.services.filesystem import FileSystemService


# Strategies for generating test data
valid_game_titles = st.text(
    min_size=1,
    max_size=50,
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Zs"))
).filter(lambda x: x.strip())

valid_categories = st.sampled_from(["Xbox", "PlayStation", "Nintendo", "PC"])

valid_disc_numbers = st.text(
    min_size=1,
    max_size=5,
    alphabet=st.characters(whitelist_categories=("Nd",))
).filter(lambda x: x.strip())

valid_media_ids = st.integers(min_value=1000, max_value=99999).map(str)

valid_file_sizes = st.integers(min_value=1024, max_value=1024 * 1024 * 100)  # 1KB to 100MB


@st.composite
def disc_info_strategy(draw: st.DrawFn) -> DiscInfo:
    """Generate valid DiscInfo objects."""
    return DiscInfo(
        disc_number=draw(valid_disc_numbers),
        media_id=draw(valid_media_ids),
        download_url=f"https://example.com/download/{draw(valid_media_ids)}",
        file_size=draw(valid_file_sizes)
    )


@st.composite
def game_data_strategy(draw: st.DrawFn) -> GameData:
    """Generate valid GameData objects."""
    num_discs = draw(st.integers(min_value=1, max_value=3))
    discs = [draw(disc_info_strategy()) for _ in range(num_discs)]
    
    return GameData(
        title=draw(valid_game_titles),
        game_url=f"https://example.com/game/{draw(valid_media_ids)}",
        category=draw(valid_categories),
        discs=discs,
        scraped_at=datetime.now()
    )


def create_mock_services() -> tuple[AsyncMock, MagicMock]:
    """Create mock HTTP client and filesystem services."""
    mock_http_client = AsyncMock(spec=HttpClientService)
    mock_filesystem = MagicMock(spec=FileSystemService)
    mock_filesystem.ensure_directory = MagicMock()
    return mock_http_client, mock_filesystem


@given(st.lists(game_data_strategy(), min_size=1, max_size=5))
@settings(deadline=5000)
def test_queue_management_total_tasks(games: list[GameData]) -> None:
    """
    **Feature: tui-game-scraper, Property 7: Download queue management**
    **Validates: Requirements 4.2**
    
    For any number of downloads in the queue, the download manager should correctly
    display overall queue status and individual file progress.
    
    Property: Total tasks in queue equals sum of all discs across all games.
    """
    mock_http_client, mock_filesystem = create_mock_services()
    
    manager = DownloadManagerService(
        http_client=mock_http_client,
        filesystem=mock_filesystem,
        download_directory=Path("/tmp/downloads"),
        concurrent_downloads=3
    )
    
    # Add all games to queue
    all_tasks = manager.add_batch_to_queue(games)
    
    # Calculate expected total discs
    expected_total_discs = sum(len(game.discs) for game in games)
    
    # Verify queue status
    queue_status = manager.get_queue_status()
    
    # Property: Total tasks equals total discs
    assert queue_status.total_tasks == expected_total_discs
    assert len(all_tasks) == expected_total_discs
    
    # Property: All tasks start as pending
    assert queue_status.pending_tasks == expected_total_discs
    assert queue_status.downloading_tasks == 0
    assert queue_status.completed_tasks == 0
    assert queue_status.failed_tasks == 0


@given(st.lists(game_data_strategy(), min_size=1, max_size=5))
@settings(deadline=5000)
def test_queue_management_individual_progress(games: list[GameData]) -> None:
    """
    **Feature: tui-game-scraper, Property 7: Download queue management**
    **Validates: Requirements 4.2**
    
    Property: Each task in queue has correct game and disc information.
    """
    mock_http_client, mock_filesystem = create_mock_services()
    
    manager = DownloadManagerService(
        http_client=mock_http_client,
        filesystem=mock_filesystem,
        download_directory=Path("/tmp/downloads"),
        concurrent_downloads=3
    )
    
    # Add all games to queue
    manager.add_batch_to_queue(games)
    
    # Get all tasks
    all_tasks = manager.get_all_tasks()
    
    # Build expected task info
    expected_tasks: list[tuple[str, str, str]] = []
    for game in games:
        for disc in game.discs:
            expected_tasks.append((game.title, disc.disc_number, disc.media_id))
    
    # Verify each task has correct information
    assert len(all_tasks) == len(expected_tasks)
    
    for task in all_tasks:
        # Property: Task contains valid game reference
        assert task.game.title in [g.title for g in games]
        
        # Property: Task contains valid disc reference
        assert task.disc.media_id in [d.media_id for g in games for d in g.discs]
        
        # Property: Task has valid destination path
        assert task.destination.suffix == ".zip"
        assert task.game.category in str(task.destination)


@given(st.lists(game_data_strategy(), min_size=1, max_size=5))
@settings(deadline=5000)
def test_queue_management_total_bytes(games: list[GameData]) -> None:
    """
    **Feature: tui-game-scraper, Property 7: Download queue management**
    **Validates: Requirements 4.2**
    
    Property: Total bytes in queue equals sum of all file sizes.
    """
    mock_http_client, mock_filesystem = create_mock_services()
    
    manager = DownloadManagerService(
        http_client=mock_http_client,
        filesystem=mock_filesystem,
        download_directory=Path("/tmp/downloads"),
        concurrent_downloads=3
    )
    
    # Add all games to queue
    manager.add_batch_to_queue(games)
    
    # Calculate expected total bytes
    expected_total_bytes = sum(
        disc.file_size or 0 
        for game in games 
        for disc in game.discs
    )
    
    # Verify queue status
    queue_status = manager.get_queue_status()
    
    # Property: Total bytes equals sum of file sizes
    assert queue_status.total_bytes == expected_total_bytes
    
    # Property: Downloaded bytes starts at 0
    assert queue_status.downloaded_bytes == 0


@given(game_data_strategy())
@settings(deadline=5000)
def test_queue_management_task_lookup(game: GameData) -> None:
    """
    **Feature: tui-game-scraper, Property 7: Download queue management**
    **Validates: Requirements 4.2**
    
    Property: Tasks can be looked up by their unique ID.
    """
    mock_http_client, mock_filesystem = create_mock_services()
    
    manager = DownloadManagerService(
        http_client=mock_http_client,
        filesystem=mock_filesystem,
        download_directory=Path("/tmp/downloads"),
        concurrent_downloads=3
    )
    
    # Add game to queue
    tasks = manager.add_batch_to_queue([game])
    
    # Verify each task can be looked up
    for task in tasks:
        looked_up_task = manager.get_task(task.task_id)
        
        # Property: Task lookup returns the same task
        assert looked_up_task is not None
        assert looked_up_task.task_id == task.task_id
        assert looked_up_task.game.title == task.game.title
        assert looked_up_task.disc.media_id == task.disc.media_id
    
    # Property: Non-existent task returns None
    assert manager.get_task("non_existent_task_id") is None


@given(st.lists(game_data_strategy(), min_size=2, max_size=5, unique_by=lambda g: g.title))
@settings(deadline=5000)
def test_queue_management_remove_task(games: list[GameData]) -> None:
    """
    **Feature: tui-game-scraper, Property 7: Download queue management**
    **Validates: Requirements 4.2**
    
    Property: Removing a task decreases queue size by 1.
    """
    # Ensure we have games with unique titles to avoid duplicate task IDs
    assume(len(set(g.title for g in games)) == len(games))
    
    mock_http_client, mock_filesystem = create_mock_services()
    
    manager = DownloadManagerService(
        http_client=mock_http_client,
        filesystem=mock_filesystem,
        download_directory=Path("/tmp/downloads"),
        concurrent_downloads=3
    )
    
    # Add all games to queue
    all_tasks = manager.add_batch_to_queue(games)
    initial_count = len(all_tasks)
    
    # Remove first task
    task_to_remove = all_tasks[0]
    result = manager.remove_from_queue(task_to_remove.task_id)
    
    # Property: Remove returns True for existing task
    assert result is True
    
    # Property: Queue size decreases by 1
    assert manager.get_queue_status().total_tasks == initial_count - 1
    
    # Property: Removed task is no longer in queue
    assert manager.get_task(task_to_remove.task_id) is None
    
    # Property: Remove returns False for non-existent task
    assert manager.remove_from_queue("non_existent_task") is False



@given(st.lists(game_data_strategy(), min_size=1, max_size=3))
@settings(deadline=5000)
def test_pause_resume_round_trip_state(games: list[GameData]) -> None:
    """
    **Feature: tui-game-scraper, Property 8: Download pause-resume round-trip**
    **Validates: Requirements 4.5**
    
    For any active download, pausing and then resuming should restore the download
    to its previous state without data loss.
    
    Property: Pausing then resuming restores the is_paused state to False.
    """
    mock_http_client, mock_filesystem = create_mock_services()
    
    manager = DownloadManagerService(
        http_client=mock_http_client,
        filesystem=mock_filesystem,
        download_directory=Path("/tmp/downloads"),
        concurrent_downloads=3
    )
    
    # Add games to queue
    manager.add_batch_to_queue(games)
    
    # Initial state: not paused
    assert manager.is_paused is False
    
    # Pause downloads
    manager.pause_downloads()
    assert manager.is_paused is True
    
    # Resume downloads
    manager.resume_downloads()
    
    # Property: After pause-resume round trip, is_paused returns to False
    assert manager.is_paused is False


@given(st.lists(game_data_strategy(), min_size=1, max_size=3))
@settings(deadline=5000)
def test_pause_resume_idempotent(games: list[GameData]) -> None:
    """
    **Feature: tui-game-scraper, Property 8: Download pause-resume round-trip**
    **Validates: Requirements 4.5**
    
    Property: Multiple pause calls are idempotent (state remains paused).
    """
    mock_http_client, mock_filesystem = create_mock_services()
    
    manager = DownloadManagerService(
        http_client=mock_http_client,
        filesystem=mock_filesystem,
        download_directory=Path("/tmp/downloads"),
        concurrent_downloads=3
    )
    
    # Add games to queue
    manager.add_batch_to_queue(games)
    
    # Pause multiple times
    manager.pause_downloads()
    manager.pause_downloads()
    manager.pause_downloads()
    
    # Property: Still paused after multiple pause calls
    assert manager.is_paused is True
    
    # Resume multiple times
    manager.resume_downloads()
    manager.resume_downloads()
    manager.resume_downloads()
    
    # Property: Still not paused after multiple resume calls
    assert manager.is_paused is False


@given(
    st.lists(game_data_strategy(), min_size=1, max_size=3),
    st.integers(min_value=1, max_value=5)
)
@settings(deadline=5000)
def test_pause_resume_multiple_cycles(games: list[GameData], num_cycles: int) -> None:
    """
    **Feature: tui-game-scraper, Property 8: Download pause-resume round-trip**
    **Validates: Requirements 4.5**
    
    Property: Multiple pause-resume cycles maintain consistent state.
    """
    mock_http_client, mock_filesystem = create_mock_services()
    
    manager = DownloadManagerService(
        http_client=mock_http_client,
        filesystem=mock_filesystem,
        download_directory=Path("/tmp/downloads"),
        concurrent_downloads=3
    )
    
    # Add games to queue
    manager.add_batch_to_queue(games)
    
    # Perform multiple pause-resume cycles
    for _ in range(num_cycles):
        # Pause
        manager.pause_downloads()
        assert manager.is_paused is True
        
        # Resume
        manager.resume_downloads()
        assert manager.is_paused is False
    
    # Property: After any number of cycles, state is consistent
    assert manager.is_paused is False


@given(st.lists(game_data_strategy(), min_size=1, max_size=3))
@settings(deadline=5000)
def test_pause_preserves_queue(games: list[GameData]) -> None:
    """
    **Feature: tui-game-scraper, Property 8: Download pause-resume round-trip**
    **Validates: Requirements 4.5**
    
    Property: Pausing and resuming preserves the download queue.
    """
    mock_http_client, mock_filesystem = create_mock_services()
    
    manager = DownloadManagerService(
        http_client=mock_http_client,
        filesystem=mock_filesystem,
        download_directory=Path("/tmp/downloads"),
        concurrent_downloads=3
    )
    
    # Add games to queue
    tasks = manager.add_batch_to_queue(games)
    initial_task_ids = [t.task_id for t in tasks]
    initial_queue_size = manager.get_queue_status().total_tasks
    
    # Pause and resume
    manager.pause_downloads()
    manager.resume_downloads()
    
    # Property: Queue size is preserved
    assert manager.get_queue_status().total_tasks == initial_queue_size
    
    # Property: All original tasks are still in queue
    current_task_ids = [t.task_id for t in manager.get_all_tasks()]
    assert set(initial_task_ids) == set(current_task_ids)


@given(st.lists(game_data_strategy(), min_size=1, max_size=3))
@settings(deadline=5000)
def test_pause_preserves_progress(games: list[GameData]) -> None:
    """
    **Feature: tui-game-scraper, Property 8: Download pause-resume round-trip**
    **Validates: Requirements 4.5**
    
    Property: Pausing and resuming preserves download progress (bytes_downloaded).
    """
    mock_http_client, mock_filesystem = create_mock_services()
    
    manager = DownloadManagerService(
        http_client=mock_http_client,
        filesystem=mock_filesystem,
        download_directory=Path("/tmp/downloads"),
        concurrent_downloads=3
    )
    
    # Add games to queue
    tasks = manager.add_batch_to_queue(games)
    
    # Simulate some progress on first task
    if tasks:
        tasks[0].bytes_downloaded = 1024
        tasks[0].status = DownloadStatus.DOWNLOADING
    
    # Record progress before pause
    progress_before = {t.task_id: t.bytes_downloaded for t in tasks}
    
    # Pause and resume
    manager.pause_downloads()
    manager.resume_downloads()
    
    # Property: Progress is preserved after pause-resume
    for task in manager.get_all_tasks():
        assert task.bytes_downloaded == progress_before[task.task_id]



def test_file_integrity_verification() -> None:
    """Unit test for file integrity verification functionality.
    
    Tests checksum verification for downloaded files.
    _Requirements: 4.4_
    """
    import tempfile
    import hashlib
    
    mock_http_client, mock_filesystem = create_mock_services()
    
    manager = DownloadManagerService(
        http_client=mock_http_client,
        filesystem=mock_filesystem,
        download_directory=Path("/tmp/downloads"),
        concurrent_downloads=3
    )
    
    # Create a test file with known content
    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.zip') as f:
        test_content = b"Test file content for checksum verification"
        f.write(test_content)
        test_file_path = Path(f.name)
    
    try:
        # Calculate expected checksum
        expected_checksum = hashlib.sha256(test_content).hexdigest()
        
        # Create a game and add to queue
        game = GameData(
            title="Test Game",
            game_url="https://example.com/game/1",
            category="Xbox",
            discs=[DiscInfo(
                disc_number="1",
                media_id="12345",
                download_url="https://example.com/download/12345",
                file_size=len(test_content)
            )],
            scraped_at=datetime.now()
        )
        
        tasks = manager.add_batch_to_queue([game])
        task = tasks[0]
        
        # Manually set destination to our test file and mark as completed
        task.destination = test_file_path
        task.status = DownloadStatus.COMPLETED
        
        # Run verification
        async def run_verification() -> bool:
            return await manager.verify_file_integrity(task.task_id, expected_checksum)
        
        result = asyncio.run(run_verification())
        
        # Verify checksum passed
        assert result is True
        
        # Test with wrong checksum
        async def run_bad_verification() -> bool:
            return await manager.verify_file_integrity(task.task_id, "wrong_checksum")
        
        bad_result = asyncio.run(run_bad_verification())
        assert bad_result is False
        
    finally:
        # Clean up test file
        if test_file_path.exists():
            test_file_path.unlink()


def test_retry_failed_download() -> None:
    """Unit test for retry logic on corrupted/failed downloads.
    
    _Requirements: 4.4_
    """
    mock_http_client, mock_filesystem = create_mock_services()
    
    manager = DownloadManagerService(
        http_client=mock_http_client,
        filesystem=mock_filesystem,
        download_directory=Path("/tmp/downloads"),
        concurrent_downloads=3
    )
    
    # Create a game and add to queue
    game = GameData(
        title="Test Game",
        game_url="https://example.com/game/1",
        category="Xbox",
        discs=[DiscInfo(
            disc_number="1",
            media_id="12345",
            download_url="https://example.com/download/12345",
            file_size=1024
        )],
        scraped_at=datetime.now()
    )
    
    tasks = manager.add_batch_to_queue([game])
    task = tasks[0]
    
    # Simulate a failed download
    task.status = DownloadStatus.FAILED
    task.error_message = "Download failed"
    task.bytes_downloaded = 512
    task.retry_count = 2
    
    # Retry the download
    async def run_retry() -> bool:
        return await manager.retry_failed_download(task.task_id)
    
    result = asyncio.run(run_retry())
    
    # Verify retry was successful
    assert result is True
    assert task.status == DownloadStatus.PENDING
    assert task.bytes_downloaded == 0
    assert task.error_message is None
    assert task.retry_count == 0


def test_completion_status_tracking() -> None:
    """Unit test for completion status tracking.
    
    _Requirements: 4.4_
    """
    mock_http_client, mock_filesystem = create_mock_services()
    
    manager = DownloadManagerService(
        http_client=mock_http_client,
        filesystem=mock_filesystem,
        download_directory=Path("/tmp/downloads"),
        concurrent_downloads=3
    )
    
    # Create multiple games
    games = [
        GameData(
            title=f"Game {i}",
            game_url=f"https://example.com/game/{i}",
            category="Xbox",
            discs=[DiscInfo(
                disc_number="1",
                media_id=str(10000 + i),
                download_url=f"https://example.com/download/{10000 + i}",
                file_size=1024
            )],
            scraped_at=datetime.now()
        )
        for i in range(5)
    ]
    
    tasks = manager.add_batch_to_queue(games)
    
    # Set various statuses
    tasks[0].status = DownloadStatus.COMPLETED
    tasks[1].status = DownloadStatus.COMPLETED
    tasks[2].status = DownloadStatus.FAILED
    tasks[3].status = DownloadStatus.DOWNLOADING
    tasks[4].status = DownloadStatus.PENDING
    
    # Verify status tracking
    queue_status = manager.get_queue_status()
    
    assert queue_status.total_tasks == 5
    assert queue_status.completed_tasks == 2
    assert queue_status.failed_tasks == 1
    assert queue_status.downloading_tasks == 1
    assert queue_status.pending_tasks == 1
    
    # Verify helper methods
    completed = manager.get_completed_tasks()
    assert len(completed) == 2
    
    failed = manager.get_failed_tasks()
    assert len(failed) == 1
