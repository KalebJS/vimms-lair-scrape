"""Data view screen for browsing and searching scraped game data."""

from typing import ClassVar, override

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import Button, DataTable, Input, Static, Select

import structlog

from src.models.game import GameData

from .base import BaseScreen

log = structlog.stdlib.get_logger()


def filter_games(
    games: list[GameData],
    search_query: str,
    category_filter: str | None = None,
) -> list[GameData]:
    """Filter games based on search query and category.
    
    This function implements the game search filtering logic.
    
    Args:
        games: List of games to filter
        search_query: Search query string (matches title)
        category_filter: Optional category to filter by
        
    Returns:
        Filtered list of games matching the criteria
        
    **Feature: tui-game-scraper, Property 13: Game search filtering**
    **Validates: Requirements 8.2**
    """
    result = games
    
    # Filter by search query (case-insensitive title match)
    if search_query:
        query_lower = search_query.lower().strip()
        result = [g for g in result if query_lower in g.title.lower()]
    
    # Filter by category
    if category_filter and category_filter != "All":
        result = [g for g in result if g.category == category_filter]
    
    return result


def get_game_display_info(game: GameData) -> dict[str, str]:
    """Get display information for a game.
    
    This function extracts all relevant display information from a game.
    
    Args:
        game: The game to get display info for
        
    Returns:
        Dictionary with display information including title, category,
        disc count, and all disc details
        
    **Feature: tui-game-scraper, Property 14: Game selection information display**
    **Validates: Requirements 8.3**
    """
    disc_details = []
    for disc in game.discs:
        size_str = _format_file_size(disc.file_size) if disc.file_size else "Unknown"
        disc_details.append({
            "disc_number": disc.disc_number,
            "media_id": disc.media_id,
            "download_url": disc.download_url,
            "file_size": size_str,
        })
    
    return {
        "title": game.title,
        "category": game.category,
        "game_url": game.game_url,
        "disc_count": str(len(game.discs)),
        "scraped_at": game.scraped_at.isoformat(),
        "discs": str(disc_details),  # Serialized for display
    }


def _format_file_size(size: int | None) -> str:
    """Format file size for display."""
    if size is None:
        return "Unknown"
    if size >= 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024 * 1024):.1f} GB"
    elif size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    elif size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


class DataViewScreen(BaseScreen):
    """Data view screen for browsing and searching scraped game data.
    
    This screen provides:
    - Searchable and sortable game table
    - Filtering by title, category, and metadata
    - Detailed game information display
    - Data refresh capability
    
    Requirements: 8.1, 8.2, 8.3, 8.4, 8.5
    """
    
    SCREEN_TITLE: ClassVar[str] = "View Data"
    SCREEN_NAME: ClassVar[str] = "data_view"
    
    CSS: ClassVar[str] = """
    DataViewScreen {
        align: center middle;
    }
    
    #data-container {
        width: 95%;
        height: 95%;
        padding: 1 2;
        border: solid $primary;
        background: $surface;
    }
    
    #data-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    
    .section-title {
        text-style: bold;
        color: $secondary;
        margin-top: 1;
        margin-bottom: 0;
    }
    
    #search-section {
        height: auto;
        padding: 1;
        margin-bottom: 1;
    }
    
    #search-row {
        height: 3;
    }
    
    #search-input {
        width: 2fr;
    }
    
    #category-select {
        width: 1fr;
        margin-left: 1;
    }
    
    #search-btn {
        margin-left: 1;
    }
    
    #stats-row {
        height: auto;
        margin-top: 1;
    }
    
    .search-stat {
        color: $text-muted;
        margin-right: 2;
    }
    
    #table-section {
        height: 1fr;
        border: solid $primary-darken-2;
        padding: 1;
    }
    
    #games-table {
        height: 100%;
    }
    
    #details-section {
        height: auto;
        max-height: 15;
        padding: 1;
        border: solid $secondary;
        margin-top: 1;
        display: none;
    }
    
    #details-section.has-selection {
        display: block;
    }
    
    .detail-title {
        text-style: bold;
        color: $secondary;
        margin-bottom: 1;
    }
    
    .detail-row {
        height: auto;
    }
    
    .detail-label {
        color: $text-muted;
        width: 15;
    }
    
    .detail-value {
        color: $text;
    }
    
    #disc-list {
        margin-top: 1;
        padding: 1;
        border: solid $primary-darken-3;
    }
    
    #button-row {
        margin-top: 1;
        height: auto;
        align: center middle;
    }
    
    #button-row Button {
        margin: 0 1;
    }
    
    #no-results {
        text-align: center;
        color: $text-muted;
        padding: 2;
    }
    """
    
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "go_back", "Back", show=True),
        Binding("f", "focus_search", "Search", show=True),
        Binding("r", "refresh_data", "Refresh", show=True),
        Binding("d", "download_selected", "Download", show=True),
    ]
    
    # Instance attributes
    _all_games: list[GameData]
    _filtered_games: list[GameData]
    _selected_game: GameData | None
    _categories: list[str]
    
    def __init__(self) -> None:
        """Initialize the data view screen."""
        super().__init__()
        self._all_games = []
        self._filtered_games = []
        self._selected_game = None
        self._categories = ["All"]

    @override
    def compose(self) -> ComposeResult:
        """Compose the data view screen layout."""
        with Container(id="data-container"):
            yield Static("🎮 Game Data Browser", id="data-title")
            
            # Search Section
            yield Static("Search & Filter", classes="section-title")
            with Vertical(id="search-section"):
                with Horizontal(id="search-row"):
                    yield Input(
                        placeholder="Search by game title...",
                        id="search-input",
                    )
                    yield Select(
                        [(cat, cat) for cat in self._categories],
                        value="All",
                        id="category-select",
                        prompt="Category",
                    )
                    yield Button("Search", id="search-btn", variant="primary")
                
                with Horizontal(id="stats-row"):
                    yield Static("Total: 0", id="stat-total", classes="search-stat")
                    yield Static("Showing: 0", id="stat-showing", classes="search-stat")
            
            # Games Table Section
            yield Static("Games", classes="section-title")
            with ScrollableContainer(id="table-section"):
                yield DataTable(id="games-table")
            
            # Details Section (hidden by default)
            with Vertical(id="details-section"):
                yield Static("📋 Game Details", classes="detail-title")
                with Horizontal(classes="detail-row"):
                    yield Static("Title:", classes="detail-label")
                    yield Static("", id="detail-title", classes="detail-value")
                with Horizontal(classes="detail-row"):
                    yield Static("Category:", classes="detail-label")
                    yield Static("", id="detail-category", classes="detail-value")
                with Horizontal(classes="detail-row"):
                    yield Static("Discs:", classes="detail-label")
                    yield Static("", id="detail-disc-count", classes="detail-value")
                with Horizontal(classes="detail-row"):
                    yield Static("Scraped:", classes="detail-label")
                    yield Static("", id="detail-scraped", classes="detail-value")
                with Vertical(id="disc-list"):
                    yield Static("Available Discs:", classes="detail-label")
                    yield Static("", id="disc-details")
            
            # No Results Message
            yield Static(
                "No games found. Try scraping some games first!",
                id="no-results",
            )
            
            # Control Buttons
            with Horizontal(id="button-row"):
                yield Button("Download Selected", id="btn-download", variant="primary", disabled=True)
                yield Button("Refresh", id="btn-refresh", variant="default")
                yield Button("Back", id="btn-back", variant="default")
    
    @override
    async def on_mount(self) -> None:
        """Handle screen mount - initialize table and load data."""
        await super().on_mount()
        self._setup_table()
        self._load_games_data()
    
    @override
    def on_screen_resume(self) -> None:
        """Handle screen resume - refresh data."""
        super().on_screen_resume()
        self._load_games_data()
    
    def _setup_table(self) -> None:
        """Set up the games table columns."""
        table = self.query_one("#games-table", DataTable)
        table.add_columns("Title", "Category", "Discs", "Scraped")
        table.cursor_type = "row"
    
    def _load_games_data(self) -> None:
        """Load games data from application state.
        
        **Feature: tui-game-scraper, Property 15: Data refresh consistency**
        **Validates: Requirements 8.4**
        """
        games_dict = self.game_app.app_state.games_data
        self._all_games = list(games_dict.values())
        
        # Extract unique categories
        categories = set(g.category for g in self._all_games)
        self._categories = ["All"] + sorted(categories)
        
        # Update category select
        category_select = self.query_one("#category-select", Select)
        category_select.set_options([(cat, cat) for cat in self._categories])
        
        # Apply current filters
        self._apply_filters()
        
        log.info("Games data loaded", total_games=len(self._all_games))
    
    def _apply_filters(self) -> None:
        """Apply search and category filters to the games list."""
        search_input = self.query_one("#search-input", Input)
        category_select = self.query_one("#category-select", Select)
        
        search_query = search_input.value
        category = str(category_select.value) if category_select.value else "All"
        
        # Use the filter function
        self._filtered_games = filter_games(
            self._all_games,
            search_query,
            category,
        )
        
        self._refresh_table()
        self._update_stats()
        self._update_no_results_visibility()
    
    def _refresh_table(self) -> None:
        """Refresh the games table with filtered data."""
        table = self.query_one("#games-table", DataTable)
        table.clear()
        
        for game in self._filtered_games:
            scraped_str = game.scraped_at.strftime("%Y-%m-%d %H:%M")
            table.add_row(
                game.title[:40],
                game.category,
                str(len(game.discs)),
                scraped_str,
                key=game.game_url,
            )
    
    def _update_stats(self) -> None:
        """Update the statistics display."""
        self.query_one("#stat-total", Static).update(f"Total: {len(self._all_games)}")
        self.query_one("#stat-showing", Static).update(f"Showing: {len(self._filtered_games)}")
    
    def _update_no_results_visibility(self) -> None:
        """Update visibility of no results message."""
        no_results = self.query_one("#no-results", Static)
        table_section = self.query_one("#table-section", ScrollableContainer)
        
        if len(self._filtered_games) == 0:
            no_results.display = True
            table_section.display = False
            
            # Update message based on whether we have any games
            if len(self._all_games) == 0:
                no_results.update("No games found. Try scraping some games first!")
            else:
                no_results.update("No games match your search criteria. Try different filters.")
        else:
            no_results.display = False
            table_section.display = True
    
    def _show_game_details(self, game: GameData) -> None:
        """Show details for the selected game.
        
        **Feature: tui-game-scraper, Property 14: Game selection information display**
        **Validates: Requirements 8.3**
        """
        self._selected_game = game
        
        # Get display info
        info = get_game_display_info(game)
        
        # Update detail fields
        self.query_one("#detail-title", Static).update(info["title"])
        self.query_one("#detail-category", Static).update(info["category"])
        self.query_one("#detail-disc-count", Static).update(info["disc_count"])
        self.query_one("#detail-scraped", Static).update(
            game.scraped_at.strftime("%Y-%m-%d %H:%M:%S")
        )
        
        # Update disc details
        disc_text_parts = []
        for disc in game.discs:
            size_str = _format_file_size(disc.file_size)
            disc_text_parts.append(
                f"  • Disc {disc.disc_number}: {size_str} (ID: {disc.media_id})"
            )
        
        disc_details = self.query_one("#disc-details", Static)
        disc_details.update("\n".join(disc_text_parts) if disc_text_parts else "No discs available")
        
        # Show details section
        details_section = self.query_one("#details-section", Vertical)
        _ = details_section.add_class("has-selection")
        
        # Enable download button
        download_btn = self.query_one("#btn-download", Button)
        download_btn.disabled = False
        
        log.debug("Game details shown", game=game.title)
    
    def _hide_game_details(self) -> None:
        """Hide the game details section."""
        self._selected_game = None
        
        details_section = self.query_one("#details-section", Vertical)
        _ = details_section.remove_class("has-selection")
        
        download_btn = self.query_one("#btn-download", Button)
        download_btn.disabled = True

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id
        
        if button_id == "btn-search":
            self._apply_filters()
        elif button_id == "btn-download":
            await self._download_selected()
        elif button_id == "btn-refresh":
            self._load_games_data()
            self.notify_success("Data refreshed")
        elif button_id == "btn-back":
            await self.action_go_back()
    
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle search input submission."""
        if event.input.id == "search-input":
            self._apply_filters()
    
    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes for live filtering."""
        if event.input.id == "search-input":
            # Apply filters on each keystroke for live search
            self._apply_filters()
    
    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle category selection changes."""
        if event.select.id == "category-select":
            self._apply_filters()
    
    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection in the games table."""
        if event.row_key:
            game_url = str(event.row_key.value)
            
            # Find the game by URL
            for game in self._filtered_games:
                if game.game_url == game_url:
                    self._show_game_details(game)
                    return
            
            log.warning("Selected game not found", game_url=game_url)
    
    async def _download_selected(self) -> None:
        """Add selected game to download queue."""
        if not self._selected_game:
            self.notify_warning("No game selected")
            return
        
        # Get or create download manager
        download_manager = self.game_app.download_manager
        if not download_manager:
            self.notify_error("Download manager not available")
            return
        
        # Add all discs to download queue
        game = self._selected_game
        for disc in game.discs:
            download_manager.add_to_queue(game, disc)
        
        self.notify_success(
            f"Added {len(game.discs)} disc(s) from '{game.title}' to download queue"
        )
        log.info(
            "Game added to download queue",
            game=game.title,
            discs=len(game.discs)
        )
    
    def action_focus_search(self) -> None:
        """Focus the search input."""
        search_input = self.query_one("#search-input", Input)
        search_input.focus()
    
    def action_refresh_data(self) -> None:
        """Refresh the games data."""
        self._load_games_data()
        self.notify_success("Data refreshed")
    
    async def action_download_selected(self) -> None:
        """Download the selected game."""
        await self._download_selected()
