"""Resolves a stock-list name to its member symbols.

Two sources are merged: bundled index-constituent CSVs shipped with the app
(NIFTY 50, NIFTY BANK, SENSEX, ...), and the user's own custom lists, which
live as separate sheets in a single, user-visible workbook (My Lists.xlsx)
so the user can view/edit them directly in Excel (see docs/DESIGN.md §9).
"""

from __future__ import annotations

import json
from pathlib import Path

import openpyxl
from openpyxl.utils.exceptions import InvalidFileException

BUNDLED_LISTS_DIR = Path(__file__).parent / "lists"
BUNDLED_META_PATH = BUNDLED_LISTS_DIR / "meta.json"


def default_documents_dir() -> Path:
    """Return the OS's Documents folder, which is the same call on macOS/Windows."""
    return Path.home() / "Documents"


def custom_lists_workbook_path() -> Path:
    """Return the path to the user's My Lists.xlsx workbook."""
    return default_documents_dir() / "NSE Data Fetcher" / "My Lists.xlsx"


class ListNotFoundError(Exception):
    """Raised when a requested list name matches neither a bundled nor custom list."""

    def __init__(self, name: str):
        """Store the list name the user asked for."""
        self.name = name
        super().__init__(f"List not found: {name!r}")


class WorkbookLockedError(Exception):
    """Raised when My Lists.xlsx can't be written because it's open elsewhere."""


class ListResolver:
    """Looks up bundled and custom stock lists by name."""

    def __init__(self, bundled_dir: Path = BUNDLED_LISTS_DIR, workbook_path: Path | None = None):
        """Load bundled list metadata; the custom workbook is read lazily on demand."""
        self._bundled_dir = bundled_dir
        self._workbook_path = workbook_path or custom_lists_workbook_path()
        try:
            self._bundled_meta = json.loads((bundled_dir / "meta.json").read_text())
        except FileNotFoundError:
            self._bundled_meta = {}

    def bundled_list_names(self) -> list[str]:
        """Return the display names of every bundled index list, e.g. 'NIFTY 50 (as of Mar 2026)'."""
        return [f"{name} (as of {meta['last_updated']})" for name, meta in self._bundled_meta.items()]

    def custom_list_names(self) -> list[str]:
        """Return the sheet names in My Lists.xlsx, i.e. the user's saved custom lists."""
        if not self._workbook_path.exists():
            return []
        try:
            wb = openpyxl.load_workbook(self._workbook_path, read_only=True)
        except InvalidFileException:
            return []
        try:
            return list(wb.sheetnames)
        finally:
            wb.close()

    def all_list_names(self) -> list[str]:
        """Return every list name (bundled + custom) for the entry field's autocomplete."""
        return list(self._bundled_meta.keys()) + self.custom_list_names()

    def resolve(self, name: str) -> list[str]:
        """Return the member symbols for a bundled or custom list name.

        Raises ListNotFoundError if the name matches neither.
        """
        if name in self._bundled_meta:
            return self._read_symbol_column(self._bundled_dir / self._bundled_meta[name]["file"])

        if self._workbook_path.exists():
            try:
                wb = openpyxl.load_workbook(self._workbook_path, read_only=True)
            except InvalidFileException:
                wb = None
            if wb is not None:
                try:
                    matches = [s for s in wb.sheetnames if s.upper() == name.upper()]
                    if matches:
                        return self._read_sheet_symbols(wb[matches[0]])
                finally:
                    wb.close()

        raise ListNotFoundError(name)

    def save_custom_list(self, name: str, symbols: list[str]) -> None:
        """Write `symbols` as a sheet named `name` in My Lists.xlsx, overwriting any existing sheet.

        Raises WorkbookLockedError if the file is open (e.g. in Excel) and can't be saved.
        """
        self._workbook_path.parent.mkdir(parents=True, exist_ok=True)
        if self._workbook_path.exists():
            try:
                wb = openpyxl.load_workbook(self._workbook_path)
            except InvalidFileException:
                wb = openpyxl.Workbook()
                wb.remove(wb.active)
        else:
            wb = openpyxl.Workbook()
            wb.remove(wb.active)

        if name in wb.sheetnames:
            del wb[name]
        sheet = wb.create_sheet(title=name[:31])
        sheet.append(["Symbol"])
        for symbol in symbols:
            sheet.append([symbol])

        try:
            wb.save(self._workbook_path)
        except PermissionError as exc:
            raise WorkbookLockedError(
                f"Please close '{self._workbook_path.name}' in Excel, then try again."
            ) from exc

    def _read_symbol_column(self, csv_path: Path) -> list[str]:
        """Read the Symbol column of a bundled list CSV."""
        import csv

        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        return [r[0].strip() for r in rows[1:] if r and r[0].strip()]

    def _read_sheet_symbols(self, sheet) -> list[str]:
        """Read the first non-empty column of a worksheet as a symbol list, skipping blanks."""
        symbols = []
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            return symbols
        start = 1 if rows[0] and str(rows[0][0]).strip().upper() == "SYMBOL" else 0
        for row in rows[start:]:
            if row and row[0] is not None and str(row[0]).strip():
                symbols.append(str(row[0]).strip())
        return symbols
