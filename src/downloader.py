"""Orchestrates the full download pipeline: resolve symbols, fetch, write Excel.

This is the layer the GUI calls into; it knows nothing about Tkinter and
could equally be driven from a script or test.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

import pandas as pd

from datasources.base import INTRADAY_LOOKBACK_DAYS, DataSourceError, FetchRequest, clamp_start_for_interval
from datasources.yfinance_source import YFinanceSource
from excel_writer import write_workbook
from symbols import SymbolResolver

logger = logging.getLogger(__name__)

_ADAPTERS = {
    "yfinance": YFinanceSource(),
}

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')

_INTERVAL_LABELS = {"5min": "5-minute", "15min": "15-minute", "1hour": "1-hour"}


def sanitize_filename(name: str) -> str:
    """Strip characters illegal in a filename on Windows (the most restrictive of the OSes this runs on)."""
    cleaned = _INVALID_FILENAME_CHARS.sub("_", name).strip().rstrip(". ")
    return cleaned or "NSE_Data"


def validate_date_range(interval: str, start: date, end: date) -> str | None:
    """Return a plain-language error if (interval, start, end) can't produce any data, else None.

    Doesn't reject a range that's merely too *wide* for an intraday interval
    -- download_all()/clamp_start_for_interval() already narrow that
    silently (and tell the user via DownloadResult.was_clamped). This is
    only for ranges that can't work at all: reversed, in the future, or
    (for an intraday interval) entirely outside Yahoo Finance's lookback
    window, which clamping alone would silently turn into a 0-row result
    with no explanation.
    """
    if start > end:
        return "The 'From' date must be before the 'To' date."
    if end > date.today():
        return "The 'To' date can't be in the future."

    clamped_start, was_clamped = clamp_start_for_interval(interval, start, end)
    if was_clamped and clamped_start > end:
        max_days = INTRADAY_LOOKBACK_DAYS[interval]
        label = _INTERVAL_LABELS.get(interval, interval)
        return (
            f"{label} data is only available for the last {max_days} days. "
            "The selected range doesn't overlap with that window at all -- "
            "pick a more recent range, or switch to Daily."
        )
    return None


@dataclass(frozen=True)
class Entry:
    """One resolved item in the user's selection list, ready to fetch."""

    display_name: str
    sheet_name: str
    ticker: str
    adapter: str
    instrument_type: str


@dataclass
class DownloadResult:
    """Outcome of a batch download: which symbols made it in, and which didn't."""

    output_path: Path
    succeeded: list[str]
    failed: list[tuple[str, str]]  # (display_name, reason)
    was_clamped: bool
    clamped_start: date | None


def entry_from_symbol(resolver: SymbolResolver, name: str) -> Entry:
    """Build an Entry from a plain stock/index name via the symbol resolver."""
    resolved = resolver.resolve(name)
    return Entry(
        display_name=resolved.display_name,
        sheet_name=resolved.display_name,
        ticker=resolved.ticker,
        adapter=resolved.adapter,
        instrument_type=resolved.instrument_type,
    )


def download_all(
    entries: list[Entry],
    interval: str,
    start: date,
    end: date,
    output_dir: Path,
    filename: str | None = None,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> DownloadResult:
    """Fetch every entry and write the results into one workbook in output_dir.

    filename, if given (and non-blank), names the output workbook (".xlsx"
    is appended if missing); otherwise a name is generated from the
    symbol(s) and date range, same as before this was configurable.

    on_progress, if given, is called as (index, total, display_name) before
    each fetch so the UI can show "Fetching X (i/n)...".
    """
    clamped_start, was_clamped = clamp_start_for_interval(interval, start, end)
    effective_start = clamped_start if was_clamped else start

    data: dict[str, pd.DataFrame] = {}
    succeeded: list[str] = []
    failed: list[tuple[str, str]] = []

    for i, entry in enumerate(entries, start=1):
        if on_progress:
            on_progress(i, len(entries), entry.display_name)
        logger.info(
            "Fetching %s (%d/%d): ticker=%s adapter=%s interval=%s start=%s end=%s",
            entry.display_name, i, len(entries), entry.ticker, entry.adapter, interval, effective_start, end,
        )
        try:
            source = _ADAPTERS[entry.adapter]
            request = FetchRequest(
                ticker=entry.ticker,
                interval=interval,
                start=effective_start,
                end=end,
                instrument_type=entry.instrument_type,
            )
            df = source.get_ohlcv(request)
            data[entry.sheet_name] = df
            succeeded.append(entry.display_name)
            logger.info("Fetched %s: %d rows", entry.display_name, len(df))
        except DataSourceError as exc:
            # exc_info logs the full traceback -- exc.message is only the
            # short, user-facing text shown in the app, which for e.g. a
            # swallowed network/SSL error looks identical to a genuine
            # "no data" result; the traceback is what actually tells them apart.
            logger.warning("Failed to fetch %s (%s): %s", entry.display_name, entry.ticker, exc.message, exc_info=True)
            failed.append((entry.display_name, exc.message))
        except Exception as exc:
            logger.warning("Failed to fetch %s (%s): %s", entry.display_name, entry.ticker, exc, exc_info=True)
            failed.append((entry.display_name, str(exc)))

    if filename and filename.strip():
        base_name = sanitize_filename(filename.strip())
        if not base_name.lower().endswith(".xlsx"):
            base_name += ".xlsx"
    elif len(entries) == 1:
        base_name = f"{entries[0].sheet_name}_{start.isoformat()}_{end.isoformat()}.xlsx"
    else:
        base_name = f"NSE_Data_{start.isoformat()}_{end.isoformat()}.xlsx"
    output_path = Path(output_dir) / base_name

    if data:
        write_workbook(data, output_path)

    return DownloadResult(
        output_path=output_path,
        succeeded=succeeded,
        failed=failed,
        was_clamped=was_clamped,
        clamped_start=clamped_start if was_clamped else None,
    )
