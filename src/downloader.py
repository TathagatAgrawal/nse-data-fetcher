"""Orchestrates the full download pipeline: resolve symbols, fetch, write Excel.

This is the layer the GUI calls into; it knows nothing about Tkinter and
could equally be driven from a script or test.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

import pandas as pd

from datasources.base import DataSourceError, FetchRequest, clamp_start_for_interval
from datasources.yfinance_source import YFinanceSource
from excel_writer import write_workbook
from symbols import SymbolResolver

_ADAPTERS = {
    "yfinance": YFinanceSource(),
}


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
    on_progress: Callable[[int, int, str], None] | None = None,
) -> DownloadResult:
    """Fetch every entry and write the results into one workbook in output_dir.

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
        except DataSourceError as exc:
            failed.append((entry.display_name, exc.message))
        except Exception as exc:
            failed.append((entry.display_name, str(exc)))

    if len(entries) == 1:
        filename = f"{entries[0].sheet_name}_{start.isoformat()}_{end.isoformat()}.xlsx"
    else:
        filename = f"NSE_Data_{start.isoformat()}_{end.isoformat()}.xlsx"
    output_path = Path(output_dir) / filename

    if data:
        write_workbook(data, output_path)

    return DownloadResult(
        output_path=output_path,
        succeeded=succeeded,
        failed=failed,
        was_clamped=was_clamped,
        clamped_start=clamped_start if was_clamped else None,
    )
