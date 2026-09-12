"""Tests for pasted-text and file-based symbol importing."""

import csv

import openpyxl

from importer import parse_file, parse_pasted_text


def test_parse_pasted_text_handles_commas_and_newlines():
    """Symbols separated by commas or newlines (or both) are all extracted and trimmed."""
    text = "RELIANCE, TCS\nHDFCBANK\n INFY , ITC"
    assert parse_pasted_text(text) == ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ITC"]


def test_parse_pasted_text_ignores_blank_lines():
    """Blank lines/entries in pasted text don't produce empty symbol strings."""
    text = "RELIANCE\n\n, TCS,"
    assert parse_pasted_text(text) == ["RELIANCE", "TCS"]


def test_parse_csv_with_header(tmp_path):
    """A CSV with a 'Symbol' header column is read correctly, skipping the header row."""
    path = tmp_path / "portfolio.csv"
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Symbol", "Quantity"])
        writer.writerow(["RELIANCE", 10])
        writer.writerow(["TCS", 5])

    assert parse_file(path) == ["RELIANCE", "TCS"]


def test_parse_workbook_merges_multiple_sheets(tmp_path):
    """Every sheet's symbol column is read and merged, with duplicates removed."""
    path = tmp_path / "lists.xlsx"
    wb = openpyxl.Workbook()
    sheet1 = wb.active
    sheet1.title = "Sheet1"
    sheet1.append(["Symbol"])
    sheet1.append(["RELIANCE"])
    sheet1.append(["TCS"])
    sheet2 = wb.create_sheet("Sheet2")
    sheet2.append(["Symbol"])
    sheet2.append(["TCS"])
    sheet2.append(["INFY"])
    wb.save(path)

    assert parse_file(path) == ["RELIANCE", "TCS", "INFY"]
