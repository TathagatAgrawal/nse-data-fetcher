"""Resolves human-friendly stock/index names to (ticker, adapter, instrument_type).

The lookup table is a bundled CSV (symbols_table.csv) mapping the names a
non-technical user would type -- "RELIANCE", "NIFTY 50" -- to the ticker
syntax a data source actually expects, plus which adapter should serve it.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from difflib import get_close_matches
from pathlib import Path

SYMBOLS_TABLE_PATH = Path(__file__).parent / "symbols_table.csv"


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

    def all_names(self) -> list[str]:
        """Return every known display name, for autocomplete suggestions."""
        return [s.display_name for s in self._by_name.values()]

    def resolve(self, query: str) -> ResolvedSymbol:
        """Resolve a user-typed name to its ticker/adapter/instrument type.

        Raises SymbolNotFoundError (with close-match suggestions) if the
        name isn't recognized.
        """
        key = query.strip().upper()
        match = self._by_name.get(key)
        if match is not None:
            return match
        suggestions = get_close_matches(key, self._by_name.keys(), n=3, cutoff=0.6)
        raise SymbolNotFoundError(query, [self._by_name[s].display_name for s in suggestions])

    def suggest(self, prefix: str, limit: int = 10) -> list[str]:
        """Return display names starting with or containing the given prefix.

        Used to drive the entry field's autocomplete dropdown as the user types.
        """
        prefix = prefix.strip().upper()
        if not prefix:
            return []
        starts_with = [s.display_name for s in self._by_name.values() if s.display_name.upper().startswith(prefix)]
        contains = [
            s.display_name
            for s in self._by_name.values()
            if prefix in s.display_name.upper() and not s.display_name.upper().startswith(prefix)
        ]
        return (starts_with + contains)[:limit]
