"""Property-based tests for data view screen functionality."""

from datetime import datetime

import pytest
from hypothesis import given, strategies as st, settings, assume

from src.models.game import GameData, DiscInfo
from src.ui.screens.data_view import filter_games, get_game_display_info


# Strategies for generating test data
valid_game_titles = st.text(
    min_size=1,
    max_size=100,
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Zs"))
).filter(lambda x: x.strip())

valid_categories = st.sampled_from(["Xbox", "PlayStation", "Nintendo", "Sega", "PC"])

valid_disc_numbers = st.text(
    min_size=1,
    max_size=5,
    alphabet=st.characters(whitelist_categories=("Nd",))
).filter(lambda x: x.strip())

valid_media_ids = st.text(
    min_size=1,
    max_size=20,
    alphabet=st.characters(whitelist_categories=("Nd",))
).filter(lambda x: x.strip())

valid_urls = st.text(
    min_size=5,
    max_size=100,
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"))
).map(lambda x: f"https://example.com/{x}")


@st.composite
def disc_info_strategy(draw: st.DrawFn) -> DiscInfo:
    """Generate a valid DiscInfo object."""
    return DiscInfo(
        disc_number=draw(valid_disc_numbers),
        media_id=draw(valid_media_ids),
        download_url=draw(valid_urls),
        file_size=draw(st.integers(min_value=0, max_value=10_000_000_000) | st.none()),
    )


@st.composite
def game_data_strategy(draw: st.DrawFn) -> GameData:
    """Generate a valid GameData object."""
    return GameData(
        title=draw(valid_game_titles),
        game_url=draw(valid_urls),
        category=draw(valid_categories),
        discs=draw(st.lists(disc_info_strategy(), min_size=1, max_size=5)),
        scraped_at=draw(st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime(2025, 12, 31)
        )),
    )


@st.composite
def games_list_strategy(draw: st.DrawFn, min_size: int = 0, max_size: int = 20) -> list[GameData]:
    """Generate a list of GameData objects with unique URLs."""
    games = draw(st.lists(game_data_strategy(), min_size=min_size, max_size=max_size))
    # Ensure unique URLs
    seen_urls: set[str] = set()
    unique_games = []
    for game in games:
        if game.game_url not in seen_urls:
            seen_urls.add(game.game_url)
            unique_games.append(game)
    return unique_games


# Property Tests for Game Search Filtering (Property 13)

@given(
    games=games_list_strategy(min_size=0, max_size=10),
    search_query=st.text(min_size=0, max_size=50),
)
@settings(deadline=2000)
def test_game_search_filtering_returns_subset(
    games: list[GameData],
    search_query: str,
) -> None:
    """
    **Feature: tui-game-scraper, Property 13: Game search filtering**
    **Validates: Requirements 8.2**
    
    For any search criteria, the search function should return only games 
    that match the specified criteria. The result should always be a subset
    of the original games list.
    """
    result = filter_games(games, search_query)
    
    # Result should be a subset of original games
    assert len(result) <= len(games)
    
    # All results should be from the original list
    for game in result:
        assert game in games


@given(
    games=games_list_strategy(min_size=1, max_size=10),
    search_query=st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
)
@settings(deadline=2000)
def test_game_search_filtering_matches_title(
    games: list[GameData],
    search_query: str,
) -> None:
    """
    **Feature: tui-game-scraper, Property 13: Game search filtering**
    **Validates: Requirements 8.2**
    
    For any search query, all returned games should have titles that contain
    the search query (case-insensitive).
    """
    result = filter_games(games, search_query)
    
    query_lower = search_query.lower().strip()
    
    # All results should match the search query in their title
    for game in result:
        assert query_lower in game.title.lower(), \
            f"Game '{game.title}' does not contain query '{search_query}'"


@given(
    games=games_list_strategy(min_size=1, max_size=10),
    category=valid_categories,
)
@settings(deadline=2000)
def test_game_search_filtering_by_category(
    games: list[GameData],
    category: str,
) -> None:
    """
    **Feature: tui-game-scraper, Property 13: Game search filtering**
    **Validates: Requirements 8.2**
    
    For any category filter, all returned games should belong to that category.
    """
    result = filter_games(games, "", category)
    
    # All results should match the category
    for game in result:
        assert game.category == category, \
            f"Game '{game.title}' has category '{game.category}', expected '{category}'"


@given(games=games_list_strategy(min_size=0, max_size=10))
@settings(deadline=2000)
def test_game_search_filtering_empty_query_returns_all(
    games: list[GameData],
) -> None:
    """
    **Feature: tui-game-scraper, Property 13: Game search filtering**
    **Validates: Requirements 8.2**
    
    An empty search query with "All" category should return all games.
    """
    result = filter_games(games, "", "All")
    
    assert len(result) == len(games)
    for game in games:
        assert game in result


# Property Tests for Game Selection Display (Property 14)

@given(game=game_data_strategy())
@settings(deadline=2000)
def test_game_selection_display_contains_title(game: GameData) -> None:
    """
    **Feature: tui-game-scraper, Property 14: Game selection information display**
    **Validates: Requirements 8.3**
    
    For any game selected by the user, the display info should contain the game title.
    """
    info = get_game_display_info(game)
    
    assert "title" in info
    assert info["title"] == game.title


@given(game=game_data_strategy())
@settings(deadline=2000)
def test_game_selection_display_contains_category(game: GameData) -> None:
    """
    **Feature: tui-game-scraper, Property 14: Game selection information display**
    **Validates: Requirements 8.3**
    
    For any game selected by the user, the display info should contain the category.
    """
    info = get_game_display_info(game)
    
    assert "category" in info
    assert info["category"] == game.category


@given(game=game_data_strategy())
@settings(deadline=2000)
def test_game_selection_display_contains_disc_count(game: GameData) -> None:
    """
    **Feature: tui-game-scraper, Property 14: Game selection information display**
    **Validates: Requirements 8.3**
    
    For any game selected by the user, the display info should contain the correct disc count.
    """
    info = get_game_display_info(game)
    
    assert "disc_count" in info
    assert info["disc_count"] == str(len(game.discs))


@given(game=game_data_strategy())
@settings(deadline=2000)
def test_game_selection_display_contains_all_required_fields(game: GameData) -> None:
    """
    **Feature: tui-game-scraper, Property 14: Game selection information display**
    **Validates: Requirements 8.3**
    
    For any game selected by the user, the detailed view should display complete 
    information including all available discs and download options.
    """
    info = get_game_display_info(game)
    
    # Check all required fields are present
    required_fields = ["title", "category", "game_url", "disc_count", "scraped_at", "discs"]
    for field in required_fields:
        assert field in info, f"Missing required field: {field}"
    
    # Verify values match the game data
    assert info["title"] == game.title
    assert info["category"] == game.category
    assert info["game_url"] == game.game_url
    assert info["disc_count"] == str(len(game.discs))
    
    # Verify scraped_at is a valid ISO format string
    assert game.scraped_at.isoformat() == info["scraped_at"]


@given(game=game_data_strategy())
@settings(deadline=2000)
def test_game_selection_display_disc_details(game: GameData) -> None:
    """
    **Feature: tui-game-scraper, Property 14: Game selection information display**
    **Validates: Requirements 8.3**
    
    For any game, the display info should include details for all discs.
    """
    info = get_game_display_info(game)
    
    # The discs field should be a string representation containing disc info
    discs_str = info["discs"]
    
    # Verify each disc's information is represented
    for disc in game.discs:
        assert disc.disc_number in discs_str, \
            f"Disc number '{disc.disc_number}' not found in disc details"
        assert disc.media_id in discs_str, \
            f"Media ID '{disc.media_id}' not found in disc details"


# Property Tests for Data Refresh Consistency (Property 15)

@given(
    initial_games=games_list_strategy(min_size=0, max_size=5),
    new_games=games_list_strategy(min_size=0, max_size=5),
)
@settings(deadline=2000)
def test_data_refresh_consistency_filter_reflects_changes(
    initial_games: list[GameData],
    new_games: list[GameData],
) -> None:
    """
    **Feature: tui-game-scraper, Property 15: Data refresh consistency**
    **Validates: Requirements 8.4**
    
    For any change to the underlying game data, filtering should reflect 
    the new data accurately.
    """
    # Filter initial games
    initial_result = filter_games(initial_games, "")
    assert len(initial_result) == len(initial_games)
    
    # Filter new games
    new_result = filter_games(new_games, "")
    assert len(new_result) == len(new_games)
    
    # Results should match the respective input lists
    for game in initial_games:
        assert game in initial_result
    
    for game in new_games:
        assert game in new_result


@given(
    games=games_list_strategy(min_size=1, max_size=10),
    search_query=st.text(min_size=0, max_size=20),
)
@settings(deadline=2000)
def test_data_refresh_consistency_idempotent(
    games: list[GameData],
    search_query: str,
) -> None:
    """
    **Feature: tui-game-scraper, Property 15: Data refresh consistency**
    **Validates: Requirements 8.4**
    
    Filtering the same data with the same query should always produce 
    the same result (idempotent).
    """
    result1 = filter_games(games, search_query)
    result2 = filter_games(games, search_query)
    
    assert result1 == result2


# Example-based tests for edge cases

def test_filter_games_empty_list() -> None:
    """Test filtering an empty games list."""
    result = filter_games([], "test")
    assert result == []


def test_filter_games_no_match() -> None:
    """Test filtering when no games match."""
    games = [
        GameData(
            title="Super Mario",
            game_url="https://example.com/mario",
            category="Nintendo",
            discs=[DiscInfo("1", "123", "https://example.com/download")],
            scraped_at=datetime.now(),
        )
    ]
    
    result = filter_games(games, "Zelda")
    assert result == []


def test_filter_games_case_insensitive() -> None:
    """Test that search is case-insensitive."""
    games = [
        GameData(
            title="Super Mario Bros",
            game_url="https://example.com/mario",
            category="Nintendo",
            discs=[DiscInfo("1", "123", "https://example.com/download")],
            scraped_at=datetime.now(),
        )
    ]
    
    # Should match regardless of case
    result_lower = filter_games(games, "mario")
    result_upper = filter_games(games, "MARIO")
    result_mixed = filter_games(games, "MaRiO")
    
    assert len(result_lower) == 1
    assert len(result_upper) == 1
    assert len(result_mixed) == 1


def test_filter_games_combined_filters() -> None:
    """Test combining search query and category filter."""
    games = [
        GameData(
            title="Super Mario Bros",
            game_url="https://example.com/mario",
            category="Nintendo",
            discs=[DiscInfo("1", "123", "https://example.com/download")],
            scraped_at=datetime.now(),
        ),
        GameData(
            title="Mario Kart",
            game_url="https://example.com/kart",
            category="Nintendo",
            discs=[DiscInfo("1", "124", "https://example.com/download2")],
            scraped_at=datetime.now(),
        ),
        GameData(
            title="Halo",
            game_url="https://example.com/halo",
            category="Xbox",
            discs=[DiscInfo("1", "125", "https://example.com/download3")],
            scraped_at=datetime.now(),
        ),
    ]
    
    # Search for "Mario" in Nintendo category
    result = filter_games(games, "Mario", "Nintendo")
    assert len(result) == 2
    
    # Search for "Mario" in Xbox category (should be empty)
    result = filter_games(games, "Mario", "Xbox")
    assert len(result) == 0
    
    # Search for "Halo" in Xbox category
    result = filter_games(games, "Halo", "Xbox")
    assert len(result) == 1


def test_get_game_display_info_with_file_sizes() -> None:
    """Test display info includes formatted file sizes."""
    game = GameData(
        title="Test Game",
        game_url="https://example.com/test",
        category="Xbox",
        discs=[
            DiscInfo("1", "123", "https://example.com/d1", file_size=1024 * 1024 * 500),  # 500 MB
            DiscInfo("2", "124", "https://example.com/d2", file_size=1024 * 1024 * 1024 * 2),  # 2 GB
        ],
        scraped_at=datetime.now(),
    )
    
    info = get_game_display_info(game)
    
    assert info["disc_count"] == "2"
    # File sizes should be formatted in the discs string
    assert "MB" in info["discs"] or "GB" in info["discs"]


def test_get_game_display_info_with_unknown_file_size() -> None:
    """Test display info handles unknown file sizes."""
    game = GameData(
        title="Test Game",
        game_url="https://example.com/test",
        category="Xbox",
        discs=[
            DiscInfo("1", "123", "https://example.com/d1", file_size=None),
        ],
        scraped_at=datetime.now(),
    )
    
    info = get_game_display_info(game)
    
    assert "Unknown" in info["discs"]
