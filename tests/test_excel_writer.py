"""Tests for the multi-sheet Excel output writer."""

import openpyxl
import pandas as pd

from excel_writer import sanitize_sheet_name, write_workbook


def test_sanitize_sheet_name_strips_illegal_characters():
    """Characters Excel forbids in sheet names are replaced, and length is capped at 31."""
    assert sanitize_sheet_name("NIFTY:26/09?2026") == "NIFTY_26_09_2026"
    assert len(sanitize_sheet_name("X" * 50)) == 31


def test_write_workbook_creates_one_sheet_per_symbol(tmp_path):
    """Each entry in the input dict becomes its own sheet, named accordingly."""
    data = {
        "RELIANCE": pd.DataFrame({"Date": ["2026-01-01"], "Close": [1300]}),
        "TCS": pd.DataFrame({"Date": ["2026-01-01"], "Close": [3900]}),
    }
    output_path = tmp_path / "out.xlsx"

    write_workbook(data, output_path)

    wb = openpyxl.load_workbook(output_path)
    assert set(wb.sheetnames) == {"RELIANCE", "TCS"}
    assert wb["RELIANCE"]["A1"].value == "Date"
    assert wb["RELIANCE"]["B2"].value == 1300
