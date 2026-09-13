"""Tests for the download pipeline's output filename handling.

Uses a fake DataSource (no real network) so these stay hermetic -- the
fetch/adapter logic itself is exercised elsewhere; this focuses on how
download_all() names the workbook it writes.
"""

from datetime import date

import pandas as pd
import pytest

import downloader
from downloader import Entry, download_all, sanitize_filename


class FakeSource:
    """A DataSource stub that returns one fixed row, regardless of the request."""

    def get_ohlcv(self, request):
        """Return a single-row OHLCV DataFrame, ignoring the request's actual ticker/dates."""
        return pd.DataFrame(
            {"Date": [date(2026, 1, 1)], "Open": [100], "High": [101], "Low": [99], "Close": [100], "Volume": [1000]}
        )


@pytest.fixture(autouse=True)
def fake_adapter(monkeypatch):
    """Route the "yfinance" adapter to FakeSource so no test hits the network."""
    monkeypatch.setitem(downloader._ADAPTERS, "yfinance", FakeSource())


def make_entry(name: str) -> Entry:
    """Build a plain equity Entry for `name`, for use as download_all() input."""
    return Entry(display_name=name, sheet_name=name, ticker=f"{name}.NS", adapter="yfinance", instrument_type="equity")


def test_default_filename_for_single_symbol(tmp_path):
    """With no filename given, a single-symbol download names the file after that symbol and the dates."""
    result = download_all([make_entry("RELIANCE")], "daily", date(2026, 1, 1), date(2026, 1, 31), tmp_path)
    assert result.output_path == tmp_path / "RELIANCE_2026-01-01_2026-01-31.xlsx"
    assert result.output_path.exists()


def test_default_filename_for_multiple_symbols(tmp_path):
    """With no filename given, a multi-symbol download uses the generic NSE_Data name."""
    result = download_all(
        [make_entry("RELIANCE"), make_entry("TCS")], "daily", date(2026, 1, 1), date(2026, 1, 31), tmp_path
    )
    assert result.output_path == tmp_path / "NSE_Data_2026-01-01_2026-01-31.xlsx"


def test_custom_filename_is_used(tmp_path):
    """A given filename overrides the auto-generated one."""
    result = download_all(
        [make_entry("RELIANCE")], "daily", date(2026, 1, 1), date(2026, 1, 31), tmp_path, filename="My Report"
    )
    assert result.output_path == tmp_path / "My Report.xlsx"


def test_custom_filename_with_extension_is_not_doubled(tmp_path):
    """A filename that already ends in .xlsx doesn't get a second extension appended."""
    result = download_all(
        [make_entry("RELIANCE")], "daily", date(2026, 1, 1), date(2026, 1, 31), tmp_path, filename="report.xlsx"
    )
    assert result.output_path == tmp_path / "report.xlsx"


def test_blank_filename_falls_back_to_default(tmp_path):
    """A blank/whitespace-only filename is treated the same as not passing one at all."""
    result = download_all(
        [make_entry("RELIANCE")], "daily", date(2026, 1, 1), date(2026, 1, 31), tmp_path, filename="   "
    )
    assert result.output_path == tmp_path / "RELIANCE_2026-01-01_2026-01-31.xlsx"


def test_sanitize_filename_strips_illegal_characters():
    """Characters illegal in a Windows filename are replaced, not left in place."""
    assert sanitize_filename('Q1/Q2:Report?"*') == "Q1_Q2_Report___"


def test_sanitize_filename_empty_result_falls_back():
    """A filename that's blank or only trailing dots/spaces doesn't produce an empty name."""
    assert sanitize_filename("   ") == "NSE_Data"
    assert sanitize_filename("...") == "NSE_Data"
