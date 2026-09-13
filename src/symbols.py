"""Resolves human-friendly stock/index names to (ticker, adapter, instrument_type).

The lookup table is a bundled CSV (symbols_table.csv) mapping the names a
non-technical user would type -- "RELIANCE", "NIFTY 50" -- to the ticker
syntax a data source actually expects, plus which adapter should serve it.
For anything not in that table, a best-effort live fetch of NSE's full
equity list (see nse_equities.py) is used to confirm or reject a guessed
ticker instead of accepting any ticker-shaped input unchecked.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from difflib import get_close_matches
from pathlib import Path

from nse_equities import fetch_equity_symbols

SYMBOLS_TABLE_PATH = Path(__file__).parent / "symbols_table.csv"

# A plain ticker-shaped token (letters/digits/&/- only, no spaces) that isn't
# in the bundled table is assumed to be a valid but untabulated NSE equity
# symbol, rather than rejected outright -- the bundled table only covers a
# few dozen names, but NSE lists 1500+ stocks.
_RAW_TICKER_PATTERN = re.compile(r"^[A-Z0-9&\-]{1,20}$")


@dataclass(frozen=True)
class ResolvedSymbol:
    """One row of the symbol lookup table, resolved for a user's input."""

    display_name: str
    ticker: str
    adapter: str
    instrument_type: str


class SymbolNotFoundError(Exception):
    """Raised when a user's input doesn't match any known symbol."""

    def __init__(self, query: str, suggestions: list[str]):
        """Store the original query and any close-match suggestions found."""
        self.query = query
        self.suggestions = suggestions
        super().__init__(f"Symbol not found: {query!r}")


class SymbolResolver:
    """Loads the bundled symbol table and resolves user input against it."""

    def __init__(self, table_path: Path = SYMBOLS_TABLE_PATH):
        """Load the lookup table from disk into memory, keyed by uppercase name."""
        self._by_name: dict[str, ResolvedSymbol] = {}
        with open(table_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                name = row["name"].strip()
                self._by_name[name.upper()] = ResolvedSymbol(
                    display_name=name,
                    ticker=row["ticker"].strip(),
                    adapter=row["adapter"].strip(),
                    instrument_type=row["instrument_type"].strip(),
                )
        # Cached per instance so repeated lookups (e.g. autocomplete on every
        # keystroke) don't re-hit the network -- None means "not fetched yet",
        # distinct from an empty list, which means "fetched and unreachable".
        self._live_equity_symbols_cache: list[str] | None = None

    def warm_cache(self) -> None:
        """Trigger and cache the live NSE equity list fetch ahead of time.

        Meant to be called from a background thread at app startup so the
        first autocomplete lookup or symbol resolution (which otherwise pays
        for this fetch on the UI thread) is instant.
        """
        self._live_equity_symbols()

    def all_names(self) -> list[str]:
        """Return every known display name, for autocomplete suggestions."""
        return [s.display_name for s in self._by_name.values()]

    def resolve(self, query: str) -> ResolvedSymbol:
        """Resolve a user-typed name to its ticker/adapter/instrument type.

        Exact matches against the bundled table win first. Failing that, if
        the input is a close typo of a known name, raise SymbolNotFoundError
        with that suggestion rather than guessing wrong. Otherwise, if the
        input is shaped like a plain ticker (e.g. "SBI", "IRCTC") -- not a
        multi-word index/list name -- it's checked against a live fetch of
        NSE's full equity list: a real, current symbol resolves immediately;
        one NSE doesn't recognize gets a suggestion from that same live list
        instead of a blind guess. If NSE is unreachable, this falls back to
        the old behavior of accepting any ticker-shaped input unchecked --
        whether it's actually valid is then discovered at fetch time (via
        NoDataError), same as any other symbol.
        """
        key = query.strip().upper()
        match = self._by_name.get(key)
        if match is not None:
            return match

        # A high cutoff here matters: at the more permissive 0.6, unrelated
        # tickers like "IRCTC" were fuzzy-matching "ITC" and getting rejected
        # instead of falling through to the raw-ticker guess below -- 0.85
        # still catches real typos (e.g. "RELAINCE" -> RELIANCE) without
        # blocking distinct, untabulated symbols.
        suggestions = get_close_matches(key, self._by_name.keys(), n=3, cutoff=0.85)
        if suggestions:
            raise SymbolNotFoundError(query, [self._by_name[s].display_name for s in suggestions])

        if _RAW_TICKER_PATTERN.match(key):
            live_symbols = self._live_equity_symbols()
            if not live_symbols or key in live_symbols:
                return ResolvedSymbol(
                    display_name=key, ticker=f"{key}.NS", adapter="yfinance", instrument_type="equity"
                )
            # A lower cutoff is safe here (unlike the 0.85 above): this only
            # ever affects which suggestion accompanies a rejection, since
            # key is already confirmed absent from the live list -- it can't
            # cause a valid, distinct ticker to be wrongly rejected.
            live_suggestions = get_close_matches(key, live_symbols, n=3, cutoff=0.8)
            raise SymbolNotFoundError(query, live_suggestions)

        raise SymbolNotFoundError(query, [])

    def suggest(self, prefix: str, limit: int = 10) -> list[str]:
        """Return names starting with or containing the given prefix.

        Draws from both the bundled table and a live fetch of NSE's full
        equity list (falling back to just the bundled table if that fetch
        fails), to drive the entry field's autocomplete dropdown.
        """
        prefix = prefix.strip().upper()
        if not prefix:
            return []
        seen: set[str] = set()
        starts_with = []
        contains = []
        for name in self.all_names() + self._live_equity_symbols():
            upper = name.upper()
            if upper in seen:
                continue
            seen.add(upper)
            if upper.startswith(prefix):
                starts_with.append(name)
            elif prefix in upper:
                contains.append(name)
        return (starts_with + contains)[:limit]

    def _live_equity_symbols(self) -> list[str]:
        """Fetch and cache every live NSE-listed equity symbol for this resolver's lifetime."""
        if self._live_equity_symbols_cache is None:
            self._live_equity_symbols_cache = fetch_equity_symbols()
        return self._live_equity_symbols_cache
