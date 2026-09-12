# NSE Data Fetcher — Design Doc

## 1. Problem statement

A non-technical user should be able to download historical OHLCV (Open, High, Low, Close, Volume) data for one or more Indian stocks, indices, or futures contracts, at a chosen time interval (from 5-minute bars up to daily), for a chosen date range, and get it saved as a single Excel workbook — one sheet per symbol — in a folder of their choice, without touching a terminal, writing code, or understanding tickers/APIs.

## 2. Goals

- Support equities, indices, and futures/derivatives traded on NSE (and BSE where reasonable) — e.g. RELIANCE, TCS, NIFTY 50, BANK NIFTY, NIFTY futures contracts.
- Let the user select **multiple symbols** in one go and get back a **single workbook with one sheet per symbol**.
- Let the user pick a **time interval/granularity**: e.g. 5 minutes, 15 minutes, 1 hour, daily.
- Let the user pick a date range (from/to) for the download.
- Let the user pick an output directory on their machine.
- Save the result as a `.xlsx` file with OHLCV columns.
- Ship as a single double-clickable desktop app — no terminal, no Python install required by the end user.
- Give clear, plain-language errors ("Couldn't find that symbol — try RELIANCE or NIFTY 50" rather than a stack trace).

## 3. Non-goals (v1)

- Real-time/streaming quotes.
- Intervals below 1 minute (tick data), and any interval a chosen data source doesn't support for a given symbol.
- Portfolio tracking, charting, or analytics inside the app — this is a downloader, not a terminal.
- Options chain data (futures only for derivatives, in v1).
- Merging multiple symbols onto one sheet — always one sheet per symbol, to keep column meaning unambiguous.

## 4. Users

Non-technical individual investors/traders in India who want raw historical data in Excel for their own analysis (e.g. in a separate spreadsheet model), and are comfortable with a simple form-based desktop app but not with code, terminals, or config files.

## 5. High-level architecture

```
┌─────────────────────────────┐
│        Desktop GUI          │   Tkinter (ships with Python, no extra
│  (symbol list, interval,    │   runtime deps for the GUI layer itself)
│   dates, folder, Download)  │
└──────────────┬───────────────┘
               │ calls, once per selected symbol
┌──────────────▼───────────────┐
│      Symbol Resolver          │   Maps a human-friendly name/search
│  ("NIFTY 50" -> ^NSEI, etc.)  │   term to the ticker the data source
└──────────────┬───────────────┘   layer expects.
               │
┌──────────────▼───────────────┐
│       Data Source Layer       │   Pluggable: one adapter per provider.
│  (yfinance adapter,           │   Takes (symbol, interval, start, end).
│   nsepython adapter for       │   Falls back / can be swapped without
│   futures & NSE-specific data)│   touching the GUI.
└──────────────┬───────────────┘
               │ returns one DataFrame per symbol
               │ (Date/Datetime, Open, High, Low, Close, Volume)
┌──────────────▼───────────────┐
│        Excel Writer           │   pandas + openpyxl -> single .xlsx,
│  (collects all symbols'       │   one sheet per symbol, formatted
│   DataFrames into one book)   │   columns, sheet named after symbol.
└───────────────────────────────┘
```

The orchestration loop fetches one symbol at a time (sequentially, to stay polite to free data sources and keep progress reporting simple), updates the status line as each symbol completes, and only writes the workbook once all symbols have been fetched — a symbol that fails is reported but doesn't block the others from being saved.

## 6. Data source strategy

Indian market data is split across sources with different coverage:

- **yfinance** (Yahoo Finance): easiest to use, free, no API key. Covers NSE/BSE equities via `.NS` / `.BO` suffixes (e.g. `RELIANCE.NS`) and major indices via caret tickers (e.g. `^NSEI` for Nifty 50, `^NSEBANK` for Bank Nifty, `^BSESN` for Sensex). Does **not** reliably cover NSE futures contracts.
- **nsepython / jugaad-data**: scrape/wrap NSE's own public data endpoints. Better coverage for NSE-specific instruments including futures and indices not on Yahoo, but less stable (NSE changes its site/API occasionally) and slower.

Design decision: build a small adapter interface (`get_ohlcv(symbol, interval, start, end) -> DataFrame`) with one implementation per source. Try yfinance first for equities/indices (fast, stable); route futures/derivatives requests to the NSE-specific adapter. This keeps the GUI and Excel-writing code untouched if a data source needs to be swapped or a new one added later.

```python
class DataSource(Protocol):
    def get_ohlcv(self, symbol: str, interval: str, start: date, end: date) -> pd.DataFrame: ...
```

### Interval support and its limits

The UI offers a fixed dropdown of intervals — **5 minutes, 15 minutes, 1 hour, Daily** (weekly/monthly can be added later trivially since they're just a resample of daily data). Two things constrain what's actually deliverable:

- **Yahoo/yfinance's own lookback limits on intraday data**: roughly the last 60 days for 5-minute/15-minute bars, and the last ~730 days for 1-hour bars. Daily (and above) has no such limit and can go back years.
- **NSE-specific instruments (futures) via the scrape-based adapter**: intraday granularity is far less reliable there than daily, since it depends on what NSE's own public endpoints expose.

Rather than silently truncating or failing, the app validates the requested (interval, date range) combination up front and, if the range exceeds what the interval supports, tells the user plainly and offers to clamp it: *"5-minute data is only available for the last 60 days. Do you want to download from 2026-07-14 to today instead?"* This keeps the mental model simple (pick any interval, pick any dates) while being honest about real data-source limits instead of returning a silently-truncated file.

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
┌─────────────────────────────────────────────────┐
│  NSE Data Fetcher                                │
│                                                   │
│  Stock / Index / Futures (add one or more):      │
│  [ RELIANCE                    ▼ ]  [ + Add ]    │
│                                                   │
│   • RELIANCE            [x]                      │
│   • TCS                 [x]                      │
│   • NIFTY 50             [x]                      │
│                                                   │
│  Interval:    ( ) 5 min  ( ) 15 min               │
│               ( ) 1 hour  (•) Daily               │
│                                                   │
│  From date:   [ 01/01/2024 ]  (calendar icon)    │
│  To date:     [ 31/12/2024 ]  (calendar icon)    │
│                                                   │
│  Save to folder:                                 │
│  [ /Users/you/Documents      ] [ Browse... ]     │
│                                                   │
│              [   Download   ]                    │
│                                                   │
│  Status: Ready.                                  │
└───────────────────────────────────────────────────┘
```

- Symbol field: autocomplete dropdown fed by the symbol lookup table; "+ Add" appends it to a running list below (with a small "x" to remove); at least one symbol is required before Download is enabled.
- Interval: a small set of radio buttons (not a free-text field) — 5 min, 15 min, 1 hour, Daily — so users are never asked to type interval syntax.
- Date pickers: calendar widgets (no manual date-format guessing), defaulting To-date to today and From-date to one year back (adjusted automatically — with a message — when the chosen interval can't support that far back, per §6).
- Folder field: pre-filled with the OS's default Documents folder, with a native "Browse..." dialog.
- Download button: disabled while a request is in flight; status line shows per-symbol progress ("Fetching RELIANCE (1/3)...", then "Saved to ~/Documents/NSE_Data_2024-01-01_2024-12-31.xlsx") or a plain-language error. If some symbols fail and others succeed, the status line names both the saved file and which symbols were skipped and why.
- Output filename auto-generated as `NSE_Data_<from>_<to>.xlsx` for multi-symbol downloads (or `<SYMBOL>_<from>_<to>.xlsx` when only one symbol is selected), so users don't have to name files themselves.

## 9. Excel output format

- One workbook per download; **one sheet per symbol**, named after the symbol (sheet names sanitized/truncated for Excel's naming restrictions, e.g. 31-char limit and no `: \ / ? * [ ]`).
- Columns: `Date, Open, High, Low, Close, Volume` for Daily/1-hour data, or `Date, Time, Open, High, Low, Close, Volume` for intraday (5 min/15 min) so the timestamp is legible without a combined datetime column. Adjusted Close included for equities where the source provides it.
- Header row bold, column widths auto-sized, date/time columns formatted as date/time (not text) — done via `openpyxl`.
- Rows sorted oldest → newest, within each sheet.
- A symbol that fails to fetch does **not** get an empty/blank sheet — it's simply omitted from the workbook and reported in the status line, so the user never has to figure out which sheets are empty and why.

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
| Date range too long for the chosen interval | "5-minute data is only available for the last 60 days. Download from 2026-07-14 to today instead?" (Yes clamps and continues, No lets the user change the interval or dates.) |
| One symbol fails, others in the batch succeed | Workbook is still saved with the successful symbols; status line reads "Saved 2 of 3 symbols. TCS was skipped: no data found." |
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
- Is there a practical cap on how many symbols can go in one batch (e.g. 20) to keep a single download from taking too long / hitting rate limits? v1: no hard cap, but fetch sequentially with visible per-symbol progress so a large batch is at least transparent, not frozen.
- Possible v2: weekly/monthly intervals (trivial resample of daily), options data, CSV export option, remembering the user's last-used symbol list/interval between sessions.
