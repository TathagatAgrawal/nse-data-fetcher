# NSE Data Fetcher — Design Doc

## 1. Problem statement

A non-technical user should be able to download historical OHLCV (Open, High, Low, Close, Volume) data for an Indian stock, index, or futures contract, for a chosen date range, and get it saved as an Excel file in a folder of their choice — without touching a terminal, writing code, or understanding tickers/APIs.

## 2. Goals

- Support equities, indices, and futures/derivatives traded on NSE (and BSE where reasonable) — e.g. RELIANCE, TCS, NIFTY 50, BANK NIFTY, NIFTY futures contracts.
- Let the user pick a date range (from/to) for the download.
- Let the user pick an output directory on their machine.
- Save the result as a `.xlsx` file with OHLCV columns.
- Ship as a single double-clickable desktop app — no terminal, no Python install required by the end user.
- Give clear, plain-language errors ("Couldn't find that symbol — try RELIANCE or NIFTY 50" rather than a stack trace).

## 3. Non-goals (v1)

- Real-time/streaming quotes.
- Intraday data below daily granularity (can be a v2 extension if a data source supports it).
- Portfolio tracking, charting, or analytics inside the app — this is a downloader, not a terminal.
- Options chain data (futures only for derivatives, in v1).

## 4. Users

Non-technical individual investors/traders in India who want raw historical data in Excel for their own analysis (e.g. in a separate spreadsheet model), and are comfortable with a simple form-based desktop app but not with code, terminals, or config files.

## 5. High-level architecture

```
┌─────────────────────────────┐
│        Desktop GUI          │   Tkinter (ships with Python, no extra
│  (symbol, dates, folder,    │   runtime deps for the GUI layer itself)
│   Download button, status)  │
└──────────────┬───────────────┘
               │ calls
┌──────────────▼───────────────┐
│      Symbol Resolver          │   Maps a human-friendly name/search
│  ("NIFTY 50" -> ^NSEI, etc.)  │   term to the ticker the data source
└──────────────┬───────────────┘   layer expects.
               │
┌──────────────▼───────────────┐
│       Data Source Layer       │   Pluggable: one adapter per provider.
│  (yfinance adapter,           │   Falls back / can be swapped without
│   nsepython adapter for       │   touching the GUI.
│   futures & NSE-specific data)│
└──────────────┬───────────────┘
               │ returns DataFrame (Date, Open, High, Low, Close, Volume)
┌──────────────▼───────────────┐
│        Excel Writer           │   pandas + openpyxl -> .xlsx, formatted
│                                │   columns, sheet named after symbol.
└───────────────────────────────┘
```

## 6. Data source strategy

Indian market data is split across sources with different coverage:

- **yfinance** (Yahoo Finance): easiest to use, free, no API key. Covers NSE/BSE equities via `.NS` / `.BO` suffixes (e.g. `RELIANCE.NS`) and major indices via caret tickers (e.g. `^NSEI` for Nifty 50, `^NSEBANK` for Bank Nifty, `^BSESN` for Sensex). Does **not** reliably cover NSE futures contracts.
- **nsepython / jugaad-data**: scrape/wrap NSE's own public data endpoints. Better coverage for NSE-specific instruments including futures and indices not on Yahoo, but less stable (NSE changes its site/API occasionally) and slower.

Design decision: build a small adapter interface (`get_ohlcv(symbol, start, end) -> DataFrame`) with one implementation per source. Try yfinance first for equities/indices (fast, stable); route futures/derivatives requests to the NSE-specific adapter. This keeps the GUI and Excel-writing code untouched if a data source needs to be swapped or a new one added later.

```python
class DataSource(Protocol):
    def get_ohlcv(self, symbol: str, start: date, end: date) -> pd.DataFrame: ...
```

## 7. Symbol resolution

Non-technical users won't know ticker suffixes or index codes. A small bundled lookup table (CSV/JSON shipped with the app) maps common names to the right ticker + adapter:

| User types      | Resolves to      | Instrument type |
|------------------|-------------------|------------------|
| RELIANCE         | RELIANCE.NS        | Equity (NSE)     |
| NIFTY 50         | ^NSEI              | Index            |
| BANK NIFTY       | ^NSEBANK           | Index            |
| SENSEX           | ^BSESN             | Index (BSE)      |
| NIFTY FUT (near) | NIFTY, current expiry | Futures (NSE, via nsepython) |

The GUI search box does a fuzzy/prefix match against this table as the user types (autocomplete dropdown), so they never have to know the underlying ticker syntax. The table should be easy to extend by editing one data file, not code.

## 8. UI design

Single-window form, no menus, no tabs:

```
┌─────────────────────────────────────────────┐
│  NSE Data Fetcher                            │
│                                               │
│  Stock / Index / Futures:                    │
│  [ RELIANCE                    ▼ ]           │
│                                               │
│  From date:   [ 01/01/2024 ]  (calendar icon)│
│  To date:     [ 31/12/2024 ]  (calendar icon)│
│                                               │
│  Save to folder:                             │
│  [ /Users/you/Documents      ] [ Browse... ] │
│                                               │
│              [   Download   ]                │
│                                               │
│  Status: Ready.                              │
└─────────────────────────────────────────────┘
```

- Symbol field: autocomplete dropdown fed by the symbol lookup table.
- Date pickers: calendar widgets (no manual date-format guessing), defaulting To-date to today and From-date to one year back.
- Folder field: pre-filled with the OS's default Documents folder, with a native "Browse..." dialog.
- Download button: disabled while a request is in flight; status line shows progress ("Fetching...", "Saved to ~/Documents/RELIANCE_2024-01-01_2024-12-31.xlsx") or a plain-language error.
- Output filename auto-generated as `<SYMBOL>_<from>_<to>.xlsx` so users don't have to name files themselves.

## 9. Excel output format

- One sheet, named after the symbol (sheet names sanitized for Excel's naming restrictions).
- Columns: `Date, Open, High, Low, Close, Volume` (Adjusted Close included for equities where the source provides it).
- Header row bold, column widths auto-sized, date column formatted as date (not text) — done via `openpyxl`.
- Rows sorted oldest → newest.

## 10. Tech stack

- **Language**: Python 3.11+
- **GUI**: `tkinter` (stdlib — no extra install for end users) with `tkcalendar` for date pickers
- **Data fetch**: `yfinance`, `nsepython` (or `jugaad-data`) for NSE-specific/futures data
- **Excel**: `pandas` + `openpyxl`
- **Packaging**: `PyInstaller` to produce a single-file `.app` (macOS) / `.exe` (Windows) so the end user just double-clicks — no Python, no pip, no terminal.

## 11. Error handling (user-facing)

| Situation                          | Message shown to user |
|-------------------------------------|--------------------------|
| Symbol not found / no match          | "We couldn't find '<input>'. Try a name like RELIANCE, NIFTY 50, or TCS." |
| No internet connection               | "No internet connection. Please check your connection and try again." |
| No data for the date range (e.g. holiday-only range, future dates) | "No trading data found for that date range." |
| Folder not writable                  | "Can't save to that folder — please choose a different one." |

No stack traces or raw exceptions ever reach the UI; all exceptions are caught at the adapter/orchestration boundary and translated to one of the above.

## 12. Project layout (proposed)

```
nse-data-fetcher/
├── docs/
│   └── DESIGN.md
├── src/
│   ├── main.py               # GUI entry point
│   ├── symbols.py            # symbol lookup + fuzzy match
│   ├── symbols_table.csv     # bundled name -> ticker/adapter mapping
│   ├── datasources/
│   │   ├── base.py           # DataSource protocol
│   │   ├── yfinance_source.py
│   │   └── nse_source.py     # futures & NSE-specific fallback
│   └── excel_writer.py
├── tests/
├── requirements.txt
└── README.md
```

## 13. Open questions / future scope

- Should futures contract selection (which expiry) be automatic ("nearest") or user-selectable? v1: default to nearest/current-month expiry, revisit if requested.
- BSE-only symbols and smaller-cap coverage may be inconsistent across data sources — acceptable gap for v1, documented in the README.
- Possible v2: intraday data, options data, batch download (multiple symbols in one run), CSV export option.
