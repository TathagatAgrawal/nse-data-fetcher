"""Parses symbols out of pasted text or an existing CSV/Excel file.

Both paths feed the same flat list of candidate symbol strings into the
normal per-symbol resolution (symbols.SymbolResolver), so an unresolvable
entry here is reported the same way an unresolvable typed symbol is.
"""

from __future__ import annotations

import csv
from pathlib import Path

import openpyxl


def parse_pasted_text(text: str) -> list[str]:
    """Split pasted text on commas and/or newlines into a flat symbol list."""
    tokens: list[str] = []
    for line in text.splitlines():
        tokens.extend(line.split(","))
    return [t.strip() for t in tokens if t.strip()]


def parse_file(path: Path) -> list[str]:
    """Read symbols from a CSV or Excel file's symbol column(s).

    For a CSV, the first column (or a column headed 'Symbol') on the single
    sheet is used. For a workbook with multiple sheets, every sheet's symbol
    column is read and merged into one flat, de-duplicated list.
    """
    path = Path(path)
    if path.suffix.lower() == ".csv":
        return _read_csv_symbols(path)
    return _read_workbook_symbols(path)


def _symbol_column_index(header: list[str]) -> int:
    """Return the index of a column headed 'Symbol' (case-insensitive), else 0."""
    for i, cell in enumerate(header):
        if cell is not None and str(cell).strip().upper() == "SYMBOL":
            return i
    return 0


def _read_csv_symbols(path: Path) -> list[str]:
    """Read the symbol column of a CSV file."""
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if not rows:
        return []
    col = _symbol_column_index(rows[0])
    has_header = _symbol_column_index(rows[0]) != 0 or str(rows[0][0]).strip().upper() == "SYMBOL"
    data_rows = rows[1:] if has_header else rows
    return [r[col].strip() for r in data_rows if len(r) > col and r[col].strip()]


def _read_workbook_symbols(path: Path) -> list[str]:
    """Read and merge the symbol column of every sheet in an Excel workbook."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    symbols: list[str] = []
    try:
        for sheet in wb.worksheets:
            rows = list(sheet.iter_rows(values_only=True))
            if not rows:
                continue
            header = [str(c) if c is not None else "" for c in rows[0]]
            col = _symbol_column_index(header)
            has_header = header[col].strip().upper() == "SYMBOL" if col < len(header) else False
            data_rows = rows[1:] if has_header else rows
            for row in data_rows:
                if row and col < len(row) and row[col] is not None and str(row[col]).strip():
                    symbols.append(str(row[col]).strip())
    finally:
        wb.close()
    # De-duplicate while preserving order.
    seen = set()
    deduped = []
    for s in symbols:
        key = s.upper()
        if key not in seen:
            seen.add(key)
            deduped.append(s)
    return deduped
