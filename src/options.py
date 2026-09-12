"""Builds and describes futures/options contract symbols from user-picked fields.

An options or futures contract can't be named with one friendly string the
way a stock can -- it needs an underlying, an expiry, and (for options) a
strike and CE/PE. This module turns those fields into the synthetic ticker
string the NSE adapter expects, and best-effort fetches real expiry/strike
lists from NSE so the UI can offer dropdowns instead of free-text entry.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContractSpec:
    """The fields a user picks in the options/futures sub-form."""

    underlying: str
    expiry: str  # e.g. "26-Sep-2026"
    strike: str | None = None  # None for a futures contract
    option_type: str | None = None  # "CE" or "PE"; None for a futures contract

    @property
    def is_option(self) -> bool:
        """True if this spec describes an options contract rather than a future."""
        return self.strike is not None and self.option_type is not None

    @property
    def display_name(self) -> str:
        """Human-readable label shown in the selection list, e.g. 'NIFTY 26-Sep-2026 25000 CE'."""
        if self.is_option:
            return f"{self.underlying} {self.expiry} {self.strike} {self.option_type}"
        return f"{self.underlying} {self.expiry} FUT"

    @property
    def ticker(self) -> str:
        """Synthetic ticker string consumed by datasources.nse_source.NseSource."""
        if self.is_option:
            return f"{self.underlying}|{self.expiry}|{self.strike}|{self.option_type}"
        return f"{self.underlying}|{self.expiry}"

    @property
    def instrument_type(self) -> str:
        """'option' or 'future', used to route to the right NseSource fetch path."""
        return "option" if self.is_option else "future"

    @property
    def sheet_name(self) -> str:
        """A short, Excel-sheet-name-safe version of display_name."""
        compact_expiry = self.expiry.replace("-", "")[:7]  # e.g. "26Sep26"... trimmed below
        if self.is_option:
            name = f"{self.underlying}_{compact_expiry}_{self.strike}{self.option_type}"
        else:
            name = f"{self.underlying}_{compact_expiry}_FUT"
        return name[:31]


def fetch_expiries(underlying: str) -> list[str]:
    """Best-effort fetch of real upcoming expiry dates for an underlying from NSE.

    Returns an empty list (never raises) if the lookup fails -- NSE's public
    endpoints are unofficial and can be blocked/rate-limited (see
    docs/DESIGN.md §6/§16), so callers should fall back to free-text entry.
    """
    try:
        import nsepython

        return list(nsepython.expiry_list(underlying))
    except Exception:
        return []


def fetch_strikes(underlying: str, expiry: str) -> list[str]:
    """Best-effort fetch of real available strike prices for an underlying/expiry.

    Returns an empty list (never raises) if the lookup fails, same rationale
    as fetch_expiries.
    """
    try:
        import nsepython

        chain = nsepython.nse_optionchain_scrapper(underlying)
        strikes = {
            str(row["strikePrice"])
            for row in chain.get("records", {}).get("data", [])
            if row.get("expiryDate") == expiry
        }
        return sorted(strikes, key=float)
    except Exception:
        return []
