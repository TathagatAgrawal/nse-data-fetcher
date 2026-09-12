"""Tests for the bundled symbol lookup table and resolver."""

import pytest

import symbols
from symbols import SymbolNotFoundError, SymbolResolver


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Stub out the live NSE equity fetch so tests never hit the network.

    Individual tests override this via monkeypatch.setattr(symbols, ...) to
    simulate NSE being reachable.
    """
    monkeypatch.setattr(symbols, "fetch_equity_symbols", lambda: [])


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


def test_untabulated_ticker_confirmed_by_live_nse_list(monkeypatch, resolver):
    """When NSE is reachable, a real but untabulated ticker resolves via the live list."""
    monkeypatch.setattr(symbols, "fetch_equity_symbols", lambda: ["IRCTC", "TATAMOTORS"])
    result = resolver.resolve("IRCTC")
    assert result.ticker == "IRCTC.NS"
    assert result.instrument_type == "equity"


def test_ticker_shaped_input_rejected_when_absent_from_live_nse_list(monkeypatch, resolver):
    """When NSE is reachable, a ticker-shaped input it doesn't recognize is rejected, not guessed."""
    monkeypatch.setattr(symbols, "fetch_equity_symbols", lambda: ["IRCTC", "TATAMOTORS"])
    with pytest.raises(SymbolNotFoundError) as exc_info:
        resolver.resolve("ZZZNOTREAL")
    assert exc_info.value.suggestions == []


def test_typo_of_live_only_symbol_gets_suggestion(monkeypatch, resolver):
    """A near-miss of a real, untabulated NSE symbol is suggested from the live list."""
    monkeypatch.setattr(symbols, "fetch_equity_symbols", lambda: ["IRCTC", "TATAMOTORS"])
    with pytest.raises(SymbolNotFoundError) as exc_info:
        resolver.resolve("IRCTD")
    assert "IRCTC" in exc_info.value.suggestions


def test_suggest_includes_live_equity_symbols(monkeypatch, resolver):
    """suggest() merges live NSE symbols with the bundled table, without duplicates."""
    monkeypatch.setattr(symbols, "fetch_equity_symbols", lambda: ["TATAPOWER", "TATACHEM"])
    suggestions = resolver.suggest("TATA")
    assert "TATAMOTORS" in suggestions  # from the bundled table
    assert "TATAPOWER" in suggestions  # from the live list
    assert suggestions.count("TATAMOTORS") == 1
