"""Tests for YFinanceSource's output shape, in particular intraday sorting."""

from datetime import date

import pandas as pd
import pytest

import datasources.yfinance_source as yfinance_source
from datasources.base import FetchRequest
from datasources.yfinance_source import YFinanceSource


def _fake_intraday_download(*_args, **_kwargs):
    """Return an intraday DataFrame with rows deliberately out of time order within a day.

    Mimics what a non-stable sort_values("Date") could produce after Date
    was truncated to date-only and Time split into a separate column: same
    Date value for every row, so the sort key alone can't recover order.
    The index is timezone-aware, matching yfinance's real intraday output
    for NSE tickers (Asia/Kolkata), since only intraday carries tzinfo --
    daily bars come back naive.
    """
    index = pd.DatetimeIndex(
        ["2026-01-02 09:15", "2026-01-01 09:25", "2026-01-01 09:15", "2026-01-02 09:05"],
        name="Datetime",
    ).tz_localize("Asia/Kolkata")
    return pd.DataFrame(
        {
            "Open": [4, 2, 1, 3],
            "High": [4, 2, 1, 3],
            "Low": [4, 2, 1, 3],
            "Close": [4, 2, 1, 3],
            "Adj Close": [4, 2, 1, 3],
            "Volume": [4, 2, 1, 3],
        },
        index=index,
    )


@pytest.fixture(autouse=True)
def fake_download(monkeypatch):
    """Route yfinance_source's yf.download to the fake intraday data, avoiding real network calls."""
    monkeypatch.setattr(yfinance_source.yf, "download", _fake_intraday_download)


def test_intraday_result_has_a_single_combined_date_column():
    """Intraday output keeps one "Date" column carrying full date+time, not a split Date/Time pair."""
    request = FetchRequest(ticker="RELIANCE.NS", interval="5min", start=date(2026, 1, 1), end=date(2026, 1, 2))
    df = YFinanceSource().get_ohlcv(request)
    assert "Time" not in df.columns
    assert "Date" in df.columns
    assert pd.api.types.is_datetime64_any_dtype(df["Date"])


def test_intraday_rows_are_sorted_by_full_date_and_time():
    """Rows sort into true chronological order, not just grouped by date with times scrambled."""
    request = FetchRequest(ticker="RELIANCE.NS", interval="5min", start=date(2026, 1, 1), end=date(2026, 1, 2))
    df = YFinanceSource().get_ohlcv(request)
    assert list(df["Date"]) == sorted(df["Date"])
    # the fake data's Close values were set to match chronological order (1, 2, 3, 4)
    assert list(df["Close"]) == [1, 2, 3, 4]


def test_intraday_date_column_is_not_timezone_aware():
    """The combined Date column is naive, even though yfinance's own intraday index carries a timezone.

    openpyxl can't write a timezone-aware datetime to Excel at all -- it
    raises ValueError -- so every intraday download would fail at the
    write step if this leaked through unstripped.
    """
    request = FetchRequest(ticker="RELIANCE.NS", interval="5min", start=date(2026, 1, 1), end=date(2026, 1, 2))
    df = YFinanceSource().get_ohlcv(request)
    assert df["Date"].dt.tz is None


def test_intraday_result_is_actually_writable_to_excel(tmp_path):
    """The full pipeline this bug broke: fetch -> write_workbook must not raise on tz-aware source data."""
    from excel_writer import write_workbook

    request = FetchRequest(ticker="RELIANCE.NS", interval="5min", start=date(2026, 1, 1), end=date(2026, 1, 2))
    df = YFinanceSource().get_ohlcv(request)
    output_path = tmp_path / "test.xlsx"
    write_workbook({"RELIANCE": df}, output_path)  # raises ValueError before the fix
    assert output_path.exists()
