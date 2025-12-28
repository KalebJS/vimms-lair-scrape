"""Property-based tests for game scraper service."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given, strategies as st, settings

from src.models.game import GameData, DiscInfo
from src.models.progress import ScrapingProgress
from src.services.game_scraper import GameScraperService
from src.services.http_client import HttpClientService


# Strategies for generating test data
# Game titles must have at least one non-whitespace character
valid_game_titles = st.text(
    min_size=1, 
    max_size=100, 
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Zs"))
).filter(lambda x: x.strip())
valid_letters = st.lists(
    st.text(min_size=1, max_size=1, alphabet=st.characters(whitelist_categories=("Lu",))),
    min_size=1,
    max_size=5
)
valid_categories = st.sampled_from(["Xbox", "PlayStation", "Nintendo"])


class MockHttpResponse:
    """Mock HTTP response for testing."""
    
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code
    
    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


def create_mock_game_page_html(game_title: str, media_ids: list[str]) -> str:
    """Create mock HTML for a game page."""
    if len(media_ids) == 1:
        # Single disc
        return f"""
        <html>
            <head><title>{game_title}</title></head>
            <body>
                <h1>{game_title}</h1>
                <input name="mediaId" value="{media_ids[0]}" />
            </body>
        </html>
        """
    else:
        # Multiple discs
        script_content = ", ".join([f'{{"ID":{media_id}}}' for media_id in media_ids])
        return f"""
        <html>
            <head><title>{game_title}</title></head>
            <body>
                <h1>{game_title}</h1>
                <script>
                    var discs = [{script_content}];
                </script>
            </body>
        </html>
        """


def create_mock_category_page_html(games: list[tuple[str, str]]) -> str:
    """Create mock HTML for a category page with games."""
    game_rows = ""
    for title, game_id in games:
        game_rows += f'<tr><td><a href="/vault/{game_id}">{title}</a></td></tr>'
    
    return f"""
    <html>
        <body>
            <table class="rounded centered cellpadding1 hovertable striped">
                {game_rows}
            </table>
        </body>
    </html>
    """


@given(
    st.lists(
        st.tuples(valid_game_titles, st.integers(min_value=1000, max_value=9999)),
        min_size=1,
        max_size=3  # Reduce max size to speed up tests
    )
)
@settings(deadline=5000)  # 5 second deadline
@pytest.mark.asyncio
async def test_progress_tracking_updates(games_data: list[tuple[str, int]]) -> None:
    """
    **Feature: tui-game-scraper, Property 5: Progress tracking updates**
    **Validates: Requirements 3.2**
    
    For any game being processed during scraping, the progress tracker should update 
    with the correct game name and completion percentage.
    
    Note: With concurrent scraping, results may arrive in any order.
    """
    # Create mock HTTP client
    mock_http_client = AsyncMock(spec=HttpClientService)
    
    # Create scraper service with sequential scraping for predictable test results
    scraper = GameScraperService(mock_http_client, request_delay=0.0, concurrent_scrapes=1)
    
    # Mock responses for category page and individual game pages
    category_html = create_mock_category_page_html(games_data)
    mock_http_client.get.side_effect = [
        # First call for counting games
        MockHttpResponse(category_html),
        # Second call for actual scraping
        MockHttpResponse(category_html),
        # Individual game page calls
        *[MockHttpResponse(create_mock_game_page_html(title, [str(game_id)])) 
          for title, game_id in games_data]
    ]
    
    # Track progress updates
    progress_updates: list[ScrapingProgress] = []
    
    # Scrape games and collect progress
    games_scraped = []
    async for game_data in scraper.scrape_category("Xbox", ["A"]):
        progress = scraper.get_scraping_progress()
        progress_updates.append(progress)
        games_scraped.append(game_data)
    
    # Verify progress tracking - with concurrent scraping, order may vary
    assert len(progress_updates) == len(games_data)
    
    # Verify all expected titles were scraped (order may vary)
    expected_titles = {title.strip() for title, _ in games_data}
    scraped_titles = {game.title for game in games_scraped}
    assert scraped_titles == expected_titles
    
    # Verify final progress state
    final_progress = scraper.get_scraping_progress()
    assert final_progress.games_processed == len(games_data)
    assert final_progress.total_games == len(games_data)
    assert final_progress.current_letter == "A"


def test_progress_tracking_example() -> None:
    """Unit test example for progress tracking."""
    mock_http_client = AsyncMock(spec=HttpClientService)
    # Use sequential scraping for predictable test results
    scraper = GameScraperService(mock_http_client, request_delay=0.0, concurrent_scrapes=1)
    
    async def run_test() -> None:
        games_data = [("Test Game 1", 1001), ("Test Game 2", 1002)]
        category_html = create_mock_category_page_html(games_data)
        
        mock_http_client.get.side_effect = [
            MockHttpResponse(category_html),  # Count games
            MockHttpResponse(category_html),  # Scrape games
            MockHttpResponse(create_mock_game_page_html("Test Game 1", ["1001"])),
            MockHttpResponse(create_mock_game_page_html("Test Game 2", ["1002"]))
        ]
        
        progress_updates = []
        games_scraped = []
        async for game_data in scraper.scrape_category("Xbox", ["A"]):
            progress = scraper.get_scraping_progress()
            progress_updates.append(progress)
            games_scraped.append(game_data)
        
        # Verify all games were scraped
        assert len(games_scraped) == 2
        scraped_titles = {g.title for g in games_scraped}
        assert scraped_titles == {"Test Game 1", "Test Game 2"}
        
        # Verify final progress
        final_progress = scraper.get_scraping_progress()
        assert final_progress.games_processed == 2
        assert final_progress.total_games == 2
    
    asyncio.run(run_test())


@given(
    st.lists(
        st.tuples(valid_game_titles, st.integers(min_value=1000, max_value=9999)),
        min_size=1,
        max_size=3  # Reduce for faster tests
    ),
    st.integers(min_value=0, max_value=2)  # Number of errors to inject
)
@settings(deadline=5000)  # 5 second deadline
@pytest.mark.asyncio
async def test_error_handling_during_scraping(
    games_data: list[tuple[str, int]], 
    error_count: int
) -> None:
    """
    **Feature: tui-game-scraper, Property 6: Error handling during operations**
    **Validates: Requirements 3.3, 4.3**
    
    For any error that occurs during scraping, the system should display error 
    information while allowing the overall process to continue.
    """
    mock_http_client = AsyncMock(spec=HttpClientService)
    scraper = GameScraperService(mock_http_client, request_delay=0.0, concurrent_scrapes=1)
    
    category_html = create_mock_category_page_html(games_data)
    
    # Create responses with some errors injected
    responses = [
        MockHttpResponse(category_html),  # Count games
        MockHttpResponse(category_html),  # Scrape games
    ]
    
    # Add individual game responses, with some errors
    for i, (title, game_id) in enumerate(games_data):
        if i < error_count:
            # Inject error for this game
            responses.append(MockHttpResponse("Error", 500))
        else:
            # Normal response
            responses.append(MockHttpResponse(create_mock_game_page_html(title, [str(game_id)])))
    
    mock_http_client.get.side_effect = responses
    
    # Scrape games
    games_scraped = []
    async for game_data in scraper.scrape_category("Xbox", ["A"]):
        games_scraped.append(game_data)
    
    # Check that scraping continued despite errors
    expected_successful_games = max(0, len(games_data) - error_count)
    assert len(games_scraped) == expected_successful_games
    
    # Check that errors were recorded
    progress = scraper.get_scraping_progress()
    actual_errors = min(error_count, len(games_data))  # Can't have more errors than games
    assert len(progress.errors) == actual_errors
    
    # Check that all error messages are strings
    for error in progress.errors:
        assert isinstance(error, str)
        assert len(error) > 0
    
    # Check that progress tracking still works correctly
    assert progress.games_processed == expected_successful_games
    assert progress.total_games == len(games_data)


def test_error_handling_example() -> None:
    """Unit test example for error handling during scraping."""
    mock_http_client = AsyncMock(spec=HttpClientService)
    scraper = GameScraperService(mock_http_client, request_delay=0.0, concurrent_scrapes=1)
    
    async def run_test() -> None:
        games_data = [("Good Game", 1001), ("Bad Game", 1002), ("Another Good Game", 1003)]
        category_html = create_mock_category_page_html(games_data)
        
        mock_http_client.get.side_effect = [
            MockHttpResponse(category_html),  # Count games
            MockHttpResponse(category_html),  # Scrape games
            MockHttpResponse(create_mock_game_page_html("Good Game", ["1001"])),  # Success
            MockHttpResponse("Server Error", 500),  # Error for "Bad Game"
            MockHttpResponse(create_mock_game_page_html("Another Good Game", ["1003"]))  # Success
        ]
        
        games_scraped = []
        async for game_data in scraper.scrape_category("Xbox", ["A"]):
            games_scraped.append(game_data)
        
        # Should have scraped 2 games successfully
        assert len(games_scraped) == 2
        assert games_scraped[0].title == "Good Game"
        assert games_scraped[1].title == "Another Good Game"
        
        # Should have recorded 1 error
        progress = scraper.get_scraping_progress()
        assert len(progress.errors) == 1
        assert "Bad Game" in progress.errors[0]
    
    asyncio.run(run_test())


def test_cancellation_support() -> None:
    """Unit test for scraping cancellation support."""
    mock_http_client = AsyncMock(spec=HttpClientService)
    scraper = GameScraperService(mock_http_client, request_delay=0.0, concurrent_scrapes=1)
    
    async def run_test() -> None:
        games_data = [("Game 1", 1001), ("Game 2", 1002), ("Game 3", 1003)]
        category_html = create_mock_category_page_html(games_data)
        
        mock_http_client.get.side_effect = [
            MockHttpResponse(category_html),  # Count games
            MockHttpResponse(category_html),  # Scrape games
            MockHttpResponse(create_mock_game_page_html("Game 1", ["1001"])),
            # Remaining responses won't be used due to cancellation
        ]
        
        games_scraped = []
        async for game_data in scraper.scrape_category("Xbox", ["A"]):
            games_scraped.append(game_data)
            # Cancel after first game
            if len(games_scraped) == 1:
                scraper.cancel_scraping()
        
        # Should have only scraped 1 game before cancellation
        assert len(games_scraped) == 1
        assert games_scraped[0].title == "Game 1"
        
        # Progress should reflect cancellation
        progress = scraper.get_scraping_progress()
        assert progress.games_processed == 1
        assert progress.total_games == 3
    
    asyncio.run(run_test())