"""NSE-scrape-backed adapter for futures and options contracts (via nsepython).

Unlike yfinance, this hits NSE's own unofficial public endpoints, which are
undocumented, can change shape without notice, and can be blocked or
rate-limited depending on network/IP (observed directly during development,
matching the instability called out in docs/DESIGN.md §6). Every call is
wrapped so a failure here always surfaces as a plain-language DataSourceError
rather than a raw exception or stack trace.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from datasources.base import DataSource, DataSourceError, FetchRequest, NoDataError

_DATE_FMT = "%d-%m-%Y"


def _fmt(d: date) -> str:
    """Format a date the way nsepython's endpoints expect (DD-MM-YYYY)."""
    return d.strftime(_DATE_FMT)


class NseSource(DataSource):
    """Fetches daily OHLC + Open Interest for NSE futures and options contracts."""

    def get_ohlcv(self, request: FetchRequest) -> pd.DataFrame:
        """Dispatch to the futures or options fetch path based on instrument_type."""
        if request.interval != "daily":
            raise DataSourceError(
                f"{request.ticker}: only Daily data is available for futures and options contracts."
            )
        try:
            import nsepython
        except ImportError as exc:
            raise DataSourceError("The nsepython package isn't installed.") from exc

        try:
            if request.instrument_type == "future":
                df = self._fetch_future(nsepython, request)
            elif request.instrument_type == "option":
                df = self._fetch_option(nsepython, request)
            else:
                raise DataSourceError(f"Unsupported instrument type: {request.instrument_type}")
        except DataSourceError:
            raise
        except Exception as exc:
            raise DataSourceError(
                f"Couldn't fetch NSE data for {request.ticker}. NSE's data service may be "
                f"temporarily unavailable or blocking this connection. ({exc})"
            ) from exc

        if df is None or df.empty:
            raise NoDataError(f"No trading data found for {request.ticker} in that date range.")
        return self._normalize(df)

    def _fetch_future(self, nsepython, request: FetchRequest) -> pd.DataFrame:
        """Fetch a futures contract's history. request.ticker is 'SYMBOL|DD-MMM-YYYY'."""
        underlying, expiry = request.ticker.split("|")
        instrument = "FUTIDX" if underlying.upper() in ("NIFTY", "BANKNIFTY") else "FUTSTK"
        return nsepython.derivative_history(
            underlying, _fmt(request.start), _fmt(request.end), instrument, expiry
        )

    def _fetch_option(self, nsepython, request: FetchRequest) -> pd.DataFrame:
        """Fetch an options contract's history. ticker is 'SYMBOL|EXPIRY|STRIKE|CE_OR_PE'."""
        underlying, expiry, strike, option_type = request.ticker.split("|")
        instrument = "OPTIDX" if underlying.upper() in ("NIFTY", "BANKNIFTY") else "OPTSTK"
        return nsepython.derivative_history(
            underlying, _fmt(request.start), _fmt(request.end), instrument, expiry, strike, option_type
        )

    def _normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        """Rename NSE's raw column names to our schema and sort oldest-first."""
        rename_map = {
            "FH_TIMESTAMP": "Date",
            "FH_OPENING_PRICE": "Open",
            "FH_TRADE_HIGH_PRICE": "High",
            "FH_TRADE_LOW_PRICE": "Low",
            "FH_CLOSING_PRICE": "Close",
            "FH_LAST_TRADED_PRICE": "LTP",
            "FH_SETTLE_PRICE": "Settle Price",
            "FH_TOT_TRADED_QTY": "Volume",
            "FH_OPEN_INT": "Open Interest",
            "FH_CHANGE_IN_OI": "Change in OI",
        }
        df = df.rename(columns=rename_map)
        keep = [c for c in ["Date", "Open", "High", "Low", "Close", "Settle Price", "Volume", "Open Interest", "Change in OI"] if c in df.columns]
        df = df[keep]
        df["Date"] = pd.to_datetime(df["Date"]).dt.date
        return df.sort_values("Date").reset_index(drop=True)
