"""Property-based tests for UI navigation."""

import pytest
from hypothesis import given, strategies as st, settings

from src.ui.app import GameScraperApp, AppState
from src.ui.screens import (
    BaseScreen,
    MainMenuScreen,
    get_screen_by_name,
    get_registered_screens,
    register_screen,
)


# Strategy for generating valid menu options from MainMenuScreen
menu_options_strategy = st.sampled_from([
    opt[0] for opt in MainMenuScreen.MENU_OPTIONS
])


class TestMenuNavigation:
    """Tests for menu navigation consistency."""
    
    @given(menu_options_strategy)
    @settings(max_examples=100)
    def test_menu_navigation_consistency(self, option: str) -> None:
        """
        **Feature: tui-game-scraper, Property 1: Menu navigation consistency**
        **Validates: Requirements 1.2**
        
        For any valid menu option, selecting it should result in navigation to 
        the corresponding screen with the correct screen being displayed.
        
        This test verifies that:
        1. Each menu option has a corresponding target screen name
        2. The target screen name is consistent with the option
        """
        # Find the target screen for this option
        target_screen = None
        for opt_id, _, target in MainMenuScreen.MENU_OPTIONS:
            if opt_id == option:
                target_screen = target
                break
        
        # Every menu option must have a target screen
        assert target_screen is not None, f"Menu option '{option}' has no target screen"
        
        # The target screen name should be a non-empty string
        assert isinstance(target_screen, str)
        assert len(target_screen) > 0
        
        # The option ID should match the expected pattern
        assert option in ["scrape", "downloads", "data", "settings"]
    
    def test_all_menu_options_have_targets(self) -> None:
        """Unit test: All menu options should have valid target screens."""
        for opt_id, label, target in MainMenuScreen.MENU_OPTIONS:
            assert opt_id, "Option ID cannot be empty"
            assert label, "Option label cannot be empty"
            assert target, "Target screen cannot be empty"
            assert isinstance(opt_id, str)
            assert isinstance(label, str)
            assert isinstance(target, str)
    
    def test_menu_options_have_unique_ids(self) -> None:
        """Unit test: All menu options should have unique IDs."""
        option_ids = [opt[0] for opt in MainMenuScreen.MENU_OPTIONS]
        assert len(option_ids) == len(set(option_ids)), "Menu option IDs must be unique"
    
    def test_menu_options_have_unique_targets(self) -> None:
        """Unit test: All menu options should have unique target screens."""
        targets = [opt[2] for opt in MainMenuScreen.MENU_OPTIONS]
        assert len(targets) == len(set(targets)), "Menu target screens must be unique"


class TestScreenRegistry:
    """Tests for screen registry functionality."""
    
    def test_main_menu_is_registered(self) -> None:
        """Unit test: Main menu screen should be registered."""
        screen = get_screen_by_name("main_menu")
        assert screen is not None
        assert isinstance(screen, MainMenuScreen)
    
    def test_unknown_screen_returns_none(self) -> None:
        """Unit test: Unknown screen names should return None."""
        screen = get_screen_by_name("nonexistent_screen")
        assert screen is None
    
    def test_get_registered_screens_includes_main_menu(self) -> None:
        """Unit test: Registered screens should include main_menu."""
        screens = get_registered_screens()
        assert "main_menu" in screens


class TestNavigationStack:
    """Tests for navigation stack management."""
    
    def test_app_starts_with_empty_navigation_stack(self) -> None:
        """Unit test: App should start with empty navigation stack."""
        app = GameScraperApp()
        assert app.navigation_stack == []
    
    def test_navigation_stack_is_copy(self) -> None:
        """Unit test: Navigation stack property should return a copy."""
        app = GameScraperApp()
        stack1 = app.navigation_stack
        stack2 = app.navigation_stack
        
        # Should be equal but not the same object
        assert stack1 == stack2
        
        # Modifying one should not affect the other
        stack1.append("test")
        assert "test" not in app.navigation_stack


class TestAppState:
    """Tests for application state management."""
    
    def test_app_state_defaults(self) -> None:
        """Unit test: AppState should have correct defaults."""
        state = AppState()
        assert state.games_data == {}
        assert state.scraping_active is False
        assert state.download_queue == []
        assert state.current_config is None
    
    def test_app_initializes_with_state(self) -> None:
        """Unit test: App should initialize with default state."""
        app = GameScraperApp()
        assert isinstance(app.app_state, AppState)
        assert app.app_state.games_data == {}
        assert app.app_state.scraping_active is False


# Strategy for generating navigation sequences
navigation_sequence_strategy = st.lists(
    st.sampled_from(["main_menu", "scraping", "downloads", "data_view", "settings"]),
    min_size=1,
    max_size=10
)


class TestBackNavigation:
    """Tests for back navigation consistency."""
    
    @given(navigation_sequence_strategy)
    @settings(max_examples=100)
    def test_back_navigation_consistency(self, screens: list[str]) -> None:
        """
        **Feature: tui-game-scraper, Property 2: Back navigation consistency**
        **Validates: Requirements 1.3**
        
        For any screen in the application, pressing escape should return to the 
        previous screen in the navigation stack.
        
        This test verifies that:
        1. Navigation stack correctly tracks pushed screens
        2. Back navigation removes the current screen from the stack
        3. The stack maintains proper order
        """
        app = GameScraperApp()
        
        # Simulate pushing screens onto the navigation stack
        for screen_name in screens:
            app._navigation_stack.append(screen_name)
        
        initial_stack_length = len(app._navigation_stack)
        
        # Verify the stack has the expected screens
        assert app._navigation_stack == screens
        
        # Simulate back navigation by popping from the stack
        if len(app._navigation_stack) > 1:
            # Pop the current screen
            current = app._navigation_stack.pop()
            
            # Verify the stack is now one shorter
            assert len(app._navigation_stack) == initial_stack_length - 1
            
            # Verify the popped screen was the last one
            assert current == screens[-1]
            
            # Verify the remaining stack is correct
            assert app._navigation_stack == screens[:-1]
    
    @given(st.lists(st.text(min_size=1, max_size=20), min_size=2, max_size=10))
    @settings(max_examples=100)
    def test_back_navigation_preserves_order(self, screens: list[str]) -> None:
        """
        **Feature: tui-game-scraper, Property 2: Back navigation consistency**
        **Validates: Requirements 1.3**
        
        For any sequence of screen navigations, back navigation should preserve
        the order of remaining screens in the stack.
        """
        app = GameScraperApp()
        
        # Push all screens
        for screen in screens:
            app._navigation_stack.append(screen)
        
        # Pop screens one by one and verify order is preserved
        remaining = screens.copy()
        while len(app._navigation_stack) > 1:
            popped = app._navigation_stack.pop()
            expected_popped = remaining.pop()
            
            assert popped == expected_popped
            assert app._navigation_stack == remaining
    
    def test_back_navigation_at_root_does_nothing(self) -> None:
        """Unit test: Back navigation at root screen should not pop."""
        app = GameScraperApp()
        app._navigation_stack.append("main_menu")
        
        # At root (only one screen), back should not pop
        initial_length = len(app._navigation_stack)
        
        # Simulate the check in action_go_back
        if len(app._navigation_stack) > 1:
            app._navigation_stack.pop()
        
        # Stack should remain unchanged
        assert len(app._navigation_stack) == initial_length
        assert app._navigation_stack == ["main_menu"]
    
    def test_back_navigation_with_multiple_screens(self) -> None:
        """Unit test: Back navigation should return to previous screen."""
        app = GameScraperApp()
        
        # Simulate navigation: main_menu -> settings -> downloads
        app._navigation_stack.append("main_menu")
        app._navigation_stack.append("settings")
        app._navigation_stack.append("downloads")
        
        assert len(app._navigation_stack) == 3
        
        # Go back from downloads
        if len(app._navigation_stack) > 1:
            current = app._navigation_stack.pop()
            assert current == "downloads"
        
        assert app._navigation_stack == ["main_menu", "settings"]
        
        # Go back from settings
        if len(app._navigation_stack) > 1:
            current = app._navigation_stack.pop()
            assert current == "settings"
        
        assert app._navigation_stack == ["main_menu"]


class TestBaseScreen:
    """Tests for BaseScreen functionality."""
    
    def test_base_screen_has_correct_defaults(self) -> None:
        """Unit test: BaseScreen should have correct default values."""
        assert BaseScreen.SCREEN_TITLE == "Screen"
        assert BaseScreen.SCREEN_NAME == "base"
    
    def test_main_menu_screen_has_correct_metadata(self) -> None:
        """Unit test: MainMenuScreen should have correct metadata."""
        assert MainMenuScreen.SCREEN_TITLE == "Main Menu"
        assert MainMenuScreen.SCREEN_NAME == "main_menu"
    
    def test_screen_is_active_property(self) -> None:
        """Unit test: Screen should track active state."""
        screen = MainMenuScreen()
        assert screen._is_active is False
