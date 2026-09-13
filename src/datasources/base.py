"""Shared interface and errors for all data source adapters.

Every adapter implements DataSource.get_ohlcv with the same signature so the
rest of the app (orchestration, Excel writer) never needs to know which
provider actually served a given symbol.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

# Intervals the UI exposes, and the days-of-history each one supports before
# the underlying data source stops returning intraday bars.
INTERVALS = ["5min", "15min", "1hour", "daily"]

INTRADAY_LOOKBACK_DAYS = {
    "5min": 60,
    "15min": 60,
    "1hour": 730,
}


@dataclass(frozen=True)
class FetchRequest:
    """Everything an adapter needs to fetch one symbol's OHLCV history."""

    ticker: str
    interval: str
    start: date
    end: date
    instrument_type: str = "equity"


class DataSourceError(Exception):
    """Raised when an adapter can't fetch data, with a plain-language reason."""

    def __init__(self, message: str):
        """Store the plain-language message shown to the user."""
        super().__init__(message)
        self.message = message


class NoDataError(DataSourceError):
    """Raised when the request was valid but no rows came back."""


class DataSource(ABC):
    """Common interface implemented by each provider-specific adapter."""

    @abstractmethod
    def get_ohlcv(self, request: FetchRequest) -> pd.DataFrame:
        """Return a DataFrame of historical bars for the given request.

        Columns are at least Date (or Datetime), Open, High, Low, Close,
        Volume. Raises DataSourceError (or a subclass) on failure.
        """
        raise NotImplementedError


def clamp_start_for_interval(interval: str, start: date, end: date) -> tuple[date, bool]:
    """Clamp a start date to what the given interval's lookback window allows.

    Yahoo Finance's intraday lookback limits are a fixed window measured
    back from *today* (e.g. "the last 60 days"), not from the query's own
    end date -- a 30-day-wide 5-minute request from 6 months ago fails
    entirely, even though its width is well under the 60-day limit,
    because none of it falls within the last 60 days. So `earliest_allowed`
    is anchored to today, not to `end`.

    The window is also one day narrower than advertised: Yahoo checks
    against the exact current moment, but a start date is always midnight,
    so "today minus 60 days" at 00:00 is already slightly *more* than 60
    real days before "now" (which includes today's elapsed hours) --
    verified directly, a start of exactly today-60 was rejected ("must be
    within the last 60 days") while today-59 succeeded. Subtracting one
    extra day keeps the clamped start safely inside the real boundary.

    Returns (possibly-adjusted start date, whether it was clamped) so callers
    can tell the user their range was shortened rather than silently doing it.
    """
    max_days = INTRADAY_LOOKBACK_DAYS.get(interval)
    if max_days is None:
        return start, False
    earliest_allowed = date.today() - timedelta(days=max_days - 1)
    if start < earliest_allowed:
        return earliest_allowed, True
    return start, False
