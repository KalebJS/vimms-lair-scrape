"""Test to verify the project setup is working correctly."""

import pytest
from hypothesis import given, strategies as st


def test_basic_setup() -> None:
    """Test that basic Python functionality works."""
    assert 1 + 1 == 2


@given(st.integers())
def test_hypothesis_setup(x: int) -> None:
    """Test that Hypothesis property-based testing works."""
    assert x + 0 == x


def test_async_setup() -> None:
    """Test that async testing setup works."""
    import asyncio
    
    async def async_function() -> str:
        return "test"
    
    result = asyncio.run(async_function())
    assert result == "test"