"""yfinance-backed adapter for NSE/BSE equities and major indices."""

from __future__ import annotations

from datetime import timedelta

import pandas as pd
import yfinance as yf

from datasources.base import DataSource, DataSourceError, FetchRequest, NoDataError

_INTERVAL_MAP = {
    "5min": "5m",
    "15min": "15m",
    "1hour": "60m",
    "daily": "1d",
}


class YFinanceSource(DataSource):
    """Fetches OHLCV bars from Yahoo Finance via the yfinance library."""

    def get_ohlcv(self, request: FetchRequest) -> pd.DataFrame:
        """Download bars for request.ticker and normalize them to our schema."""
        yf_interval = _INTERVAL_MAP[request.interval]
        try:
            df = yf.download(
                request.ticker,
                start=request.start,
                # yfinance's `end` is exclusive; add a day so the chosen end date is included.
                end=request.end + timedelta(days=1),
                interval=yf_interval,
                progress=False,
                auto_adjust=False,
                multi_level_index=False,
            )
        except Exception as exc:
            raise DataSourceError(f"Couldn't reach Yahoo Finance for {request.ticker}: {exc}") from exc

        if df is None or df.empty:
            raise NoDataError(f"No trading data found for {request.ticker} in that date range.")

        df = df.reset_index()
        # yfinance names the index column "Date" for daily bars and "Datetime" for intraday.
        timestamp_col = "Datetime" if "Datetime" in df.columns else "Date"
        df = df.rename(columns={timestamp_col: "Date"})

        columns = ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]
        df = df[[c for c in columns if c in df.columns]]

        if request.interval != "daily":
            # Kept as a single combined date+time column rather than split
            # into separate Date/Time columns -- splitting left "Date" as
            # date-only, so sorting by it alone didn't order rows within the
            # same day by time at all. tz_localize(None) drops the tzinfo
            # without shifting the wall-clock time (unlike tz_convert, which
            # would convert to UTC first) -- openpyxl can't write a
            # timezone-aware datetime to Excel at all, it raises ValueError.
            df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)

        return df.sort_values("Date").reset_index(drop=True)
