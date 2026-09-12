"""Tests for bundled and custom stock-list resolution."""

import pytest

from lists import ListNotFoundError, ListResolver


@pytest.fixture
def resolver():
    """Return a ListResolver pointed at a My Lists.xlsx that doesn't exist yet."""
    return ListResolver()


def test_resolves_bundled_list(resolver):
    """A bundled index list resolves to a non-empty list of member symbols."""
    symbols = resolver.resolve("NIFTY 50")
    assert "RELIANCE" in symbols
    assert len(symbols) > 40


def test_unknown_list_raises(resolver):
    """An unrecognized list name raises ListNotFoundError."""
    with pytest.raises(ListNotFoundError):
        resolver.resolve("NOT A REAL LIST")


def test_save_and_resolve_custom_list(tmp_path):
    """A custom list saved to the workbook can be resolved back by name."""
    workbook_path = tmp_path / "My Lists.xlsx"
    resolver = ListResolver(workbook_path=workbook_path)

    resolver.save_custom_list("MY WATCHLIST", ["RELIANCE", "TCS", "HDFCBANK"])

    assert workbook_path.exists()
    assert resolver.resolve("MY WATCHLIST") == ["RELIANCE", "TCS", "HDFCBANK"]
    assert "MY WATCHLIST" in resolver.custom_list_names()


def test_overwriting_custom_list_replaces_contents(tmp_path):
    """Saving a list under an existing name replaces its member symbols."""
    workbook_path = tmp_path / "My Lists.xlsx"
    resolver = ListResolver(workbook_path=workbook_path)

    resolver.save_custom_list("MY WATCHLIST", ["RELIANCE"])
    resolver.save_custom_list("MY WATCHLIST", ["TCS", "INFY"])

    assert resolver.resolve("MY WATCHLIST") == ["TCS", "INFY"]
