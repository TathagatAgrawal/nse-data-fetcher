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


def test_untabulated_ticker_falls_back_to_guessed_nse_symbol(resolver):
    """A plausible ticker not in the bundled table (e.g. IRCTC) still resolves, as IRCTC.NS.

    The bundled table only covers a few dozen names; NSE lists 1500+ stocks,
    so an unrecognized plain ticker shouldn't be rejected outright.
    """
    result = resolver.resolve("IRCTC")
    assert result.ticker == "IRCTC.NS"
    assert result.instrument_type == "equity"


def test_close_typo_of_known_name_is_not_guessed(resolver):
    """A near-miss of a known name still raises with a suggestion, not a wrong guess."""
    with pytest.raises(SymbolNotFoundError) as exc_info:
        resolver.resolve("RELAINCE")
    assert "RELIANCE" in exc_info.value.suggestions


def test_multi_word_input_does_not_fall_back(resolver):
    """A multi-word input that isn't a known name raises, rather than guessing a bad ticker."""
    with pytest.raises(SymbolNotFoundError):
        resolver.resolve("SOME RANDOM THING")
