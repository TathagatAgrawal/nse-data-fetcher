"""Tests for bundled, live-NSE-index, and custom stock-list resolution."""

import pytest

import lists
from lists import ListNotFoundError, ListResolver


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Stub out the live NSE fetch functions so tests never hit the network.

    Individual tests override these via monkeypatch.setattr(lists, ...) to
    simulate NSE being reachable or unreachable.
    """
    monkeypatch.setattr(lists, "fetch_index_names", lambda: [])
    monkeypatch.setattr(lists, "fetch_index_constituents", lambda name: [])


@pytest.fixture
def resolver():
    """Return a ListResolver pointed at a My Lists.xlsx that doesn't exist yet."""
    return ListResolver()


def test_resolves_bundled_list(resolver):
    """A bundled index list resolves to a non-empty list of member symbols."""
    symbols = resolver.resolve("NIFTY 50")
    assert "RELIANCE" in symbols
    assert len(symbols) > 40


def test_bundled_list_falls_back_when_nse_unreachable(resolver):
    """With the live fetch stubbed to fail, a bundled list still resolves from its CSV."""
    symbols = resolver.resolve("NIFTY 50")
    assert "RELIANCE" in symbols


def test_bundled_list_prefers_live_constituents(monkeypatch, resolver):
    """When NSE is reachable, a bundled index's live constituents win over the bundled CSV."""
    monkeypatch.setattr(lists, "fetch_index_constituents", lambda name: ["FRESHCO", "NEWCO"])
    assert resolver.resolve("NIFTY 50") == ["FRESHCO", "NEWCO"]


def test_non_bundled_name_resolves_as_live_nse_index(monkeypatch, resolver):
    """A name that isn't one of the three bundled lists still resolves via a live NSE fetch."""
    monkeypatch.setattr(
        lists, "fetch_index_constituents", lambda name: ["TATAMOTORS", "M&M"] if name == "NIFTY AUTO" else []
    )
    assert resolver.resolve("NIFTY AUTO") == ["TATAMOTORS", "M&M"]


def test_all_list_names_merges_live_indices_without_duplicating_bundled(monkeypatch, resolver):
    """Live NSE index names are merged into the name list, but bundled ones aren't duplicated."""
    monkeypatch.setattr(lists, "fetch_index_names", lambda: ["NIFTY 50", "NIFTY AUTO"])
    names = resolver.all_list_names()
    assert names.count("NIFTY 50") == 1
    assert "NIFTY AUTO" in names


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
