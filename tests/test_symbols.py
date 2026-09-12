"""Tests for the bundled symbol lookup table and resolver."""

import pytest

from symbols import SymbolNotFoundError, SymbolResolver


@pytest.fixture
def resolver():
    """Return a SymbolResolver loaded from the bundled symbols_table.csv."""
    return SymbolResolver()


def test_resolves_known_equity(resolver):
    """A known equity name resolves to its .NS ticker and equity instrument type."""
    result = resolver.resolve("RELIANCE")
    assert result.ticker == "RELIANCE.NS"
    assert result.instrument_type == "equity"
    assert result.adapter == "yfinance"


def test_resolve_is_case_insensitive(resolver):
    """Resolution ignores case, since non-technical users may type either."""
    assert resolver.resolve("reliance").ticker == "RELIANCE.NS"


def test_resolves_known_index(resolver):
    """A known index name resolves to its caret ticker."""
    result = resolver.resolve("NIFTY 50")
    assert result.ticker == "^NSEI"
    assert result.instrument_type == "index"


def test_unknown_symbol_raises_with_suggestions(resolver):
    """An unrecognized but close name raises SymbolNotFoundError with a suggestion."""
    with pytest.raises(SymbolNotFoundError) as exc_info:
        resolver.resolve("RELAINCE")
    assert "RELIANCE" in exc_info.value.suggestions


def test_suggest_returns_prefix_matches(resolver):
    """suggest() returns names starting with the typed prefix first."""
    suggestions = resolver.suggest("TATA")
    assert "TATAMOTORS" in suggestions
    assert "TATASTEEL" in suggestions
