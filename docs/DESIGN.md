# NSE Data Fetcher — Design Doc

## 1. Problem statement

A non-technical user should be able to download historical OHLCV (Open, High, Low, Close, Volume) data — plus Open Interest for derivatives — for one or more Indian stocks, indices, futures, or options contracts, at a chosen time interval (from 5-minute bars up to daily), for a chosen date range, and get it saved as a single Excel workbook — one sheet per symbol — in a folder of their choice, without touching a terminal, writing code, or understanding tickers/APIs. Symbols can be added by typing, by picking a saved list, by pasting a comma-separated list, or by pointing at an existing CSV/Excel file.

## 2. Goals

- Support equities, indices, and futures/derivatives traded on NSE (and BSE where reasonable) — e.g. RELIANCE, TCS, NIFTY 50, BANK NIFTY, NIFTY futures contracts.
- Support **options contracts** on NSE indices and stocks — the user picks an underlying, expiry, strike, and CE/PE, and gets historical OHLC + Open Interest for that specific contract.
- Let the user select **multiple symbols** in one go and get back a **single workbook with one sheet per symbol**.
- Let the user type the name of a **stock list** (e.g. "NIFTY 50", "MY WATCHLIST") and have it expand into all the symbols in that list, instead of adding each stock one by one.
- Let the user **import symbols** by pasting a comma-separated list into the app, or by selecting an existing CSV/Excel file from their computer, as an alternative to typing or picking a saved list.
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
- A live options chain view, Greeks, or IV — v1 fetches historical OHLC + OI for specific contracts the user names, not a chain snapshot.
- Merging multiple symbols onto one sheet — always one sheet per symbol, to keep column meaning unambiguous.

## 4. Users

Non-technical individual investors/traders in India who want raw historical data in Excel for their own analysis (e.g. in a separate spreadsheet model), and are comfortable with a simple form-based desktop app but not with code, terminals, or config files.

## 5. High-level architecture

```
┌───────────────────────────────────────────────────┐
│                   Desktop GUI                      │   Tkinter. Four ways to add symbols
│  (type a symbol/list, paste text, import a file,   │   feed the same selection list; interval,
│   or add an options contract via a sub-form)        │   dates, folder, Download button.
└───────────────┬───────────────┬─────────────┬───────┘
                │               │             │
    typed entry │   pasted text/│   options    │
    or list name│   imported    │   sub-form   │
                │   file        │              │
┌───────────────▼───┐  ┌────────▼──────┐  ┌────▼─────────────┐
│   List Resolver    │  │ Import Parser │  │ Options Resolver  │
│ ("NIFTY 50" ->      │  │ (comma-split  │  │ (underlying+expiry│
│  [RELIANCE, TCS,    │  │  text, or     │  │  +strike+CE/PE -> │
│  HDFCBANK, ...])    │  │  CSV/XLSX     │  │  one contract      │
│ Bundled index lists │  │  file's first │  │  symbol)           │
│ + My Lists.xlsx     │  │  symbol column│  │                    │
└───────────────┬─────┘  └────────┬──────┘  └────┬───────────────┘
                │                 │              │
                └────────┬────────┴──────┬───────┘
                         │ flattened, de-duplicated symbol list
                ┌────────▼────────────────▼────┐
                │      Symbol Resolver          │   Maps each human-friendly name/search
                │  ("RELIANCE" -> RELIANCE.NS)  │   term to the ticker the data source
                └────────────────┬───────────────┘   layer expects.
                                 │ calls, once per resolved symbol
                ┌────────────────▼───────────────┐
                │       Data Source Layer         │   Pluggable: one adapter per provider.
                │  (yfinance adapter,             │   Takes (symbol, interval, start, end).
                │   nsepython adapter for         │   Falls back / can be swapped without
                │   futures, options & other      │   touching the GUI.
                │   NSE-specific data)            │
                └────────────────┬───────────────┘
                                 │ returns one DataFrame per symbol
                                 │ (Date/Datetime, Open, High, Low, Close,
                                 │  Volume, [Open Interest for derivatives])
                ┌────────────────▼───────────────┐
                │        Excel Writer             │   pandas + openpyxl -> single .xlsx,
                │  (collects all symbols'         │   one sheet per symbol, formatted
                │   DataFrames into one book)     │   columns, sheet named after symbol.
                └─────────────────────────────────┘
```

The orchestration loop fetches one symbol at a time (sequentially, to stay polite to free data sources and keep progress reporting simple), updates the status line as each symbol completes, and only writes the workbook once all symbols have been fetched — a symbol that fails is reported but doesn't block the others from being saved.

## 6. Data source strategy

Indian market data is split across sources with different coverage:

- **yfinance** (Yahoo Finance): easiest to use, free, no API key. Covers NSE/BSE equities via `.NS` / `.BO` suffixes (e.g. `RELIANCE.NS`) and major indices via caret tickers (e.g. `^NSEI` for Nifty 50, `^NSEBANK` for Bank Nifty, `^BSESN` for Sensex). Does **not** reliably cover NSE futures or options contracts.
- **nsepython / jugaad-data**: scrape/wrap NSE's own public data endpoints. Better coverage for NSE-specific instruments including futures, options, and indices not on Yahoo, but less stable (NSE changes its site/API occasionally) and slower. This is the adapter options contracts route through — NSE's historical derivatives endpoint takes the underlying, expiry, strike, and option type as separate parameters and returns daily OHLC, Settle Price, and Open Interest per contract.

Design decision: build a small adapter interface (`get_ohlcv(symbol, interval, start, end) -> DataFrame`) with one implementation per source. Try yfinance first for equities/indices (fast, stable); route futures/options requests to the NSE-specific adapter. This keeps the GUI and Excel-writing code untouched if a data source needs to be swapped or a new one added later.

```python
class DataSource(Protocol):
    def get_ohlcv(self, symbol: str, interval: str, start: date, end: date) -> pd.DataFrame:
        """Returns Date/Datetime, Open, High, Low, Close, Volume — plus an
        Open Interest column when the symbol is a futures or options contract."""
```

### Interval support and its limits

The UI offers a fixed dropdown of intervals — **5 minutes, 15 minutes, 1 hour, Daily** (weekly/monthly can be added later trivially since they're just a resample of daily data). Two things constrain what's actually deliverable:

- **Yahoo/yfinance's own lookback limits on intraday data**: roughly the last 60 days for 5-minute/15-minute bars, and the last ~730 days for 1-hour bars. Daily (and above) has no such limit and can go back years.
- **NSE-specific instruments (futures, options) via the scrape-based adapter**: intraday granularity is far less reliable there than daily, since it depends on what NSE's own public endpoints expose — NSE's public historical-data pages are daily-bhavcopy based, so v1 effectively offers **Daily only** for options contracts, with the interval selector disabling/greying out the intraday options when an options contract is in the current selection and explaining why.

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

## 8. Options contracts

An options contract can't be identified by a single friendly name the way a stock or index can — it needs an underlying, an expiry date, a strike price, and CE (call) or PE (put). Typing all of that as one free-text string would defeat the "non-technical user" goal, so options get their own small sub-form rather than sharing the plain symbol/list entry field:

```
Add an options contract:
  Underlying:  [ NIFTY          ▼ ]   (same autocomplete as stocks/indices)
  Expiry:      [ 26-Sep-2026     ▼ ]   (dropdown of real upcoming expiries)
  Strike:      [ 25000           ▼ ]   (dropdown of real available strikes)
  Type:        ( ) CE   (•) PE
                [ + Add contract ]
```

- Reached via a small "Add options contract..." link/button next to the main entry field (so it doesn't clutter the default flow for someone who just wants stock data).
- **Expiry and Strike are dropdowns of real values fetched from NSE for the chosen underlying**, not free-text fields — this avoids the single biggest way a non-technical user could get this wrong (typing an expiry/strike that doesn't exist and getting a confusing "no data" error later). If the live lookup fails (e.g. no internet), the fields fall back to plain date/number entry with a note that it wasn't validated against NSE.
- Adding a contract appends one row to the same selection list used for stocks/lists (e.g. "NIFTY 26-Sep-2026 25000 CE"), and it downloads and gets its own sheet exactly like any other symbol — the rest of the pipeline (§11 interval/date selection, §12 Excel writer) doesn't need to know it's "special" beyond carrying an extra Open Interest column.
- Only one option contract at a time is added per use of the sub-form (no "all strikes" or "whole chain" bulk-add in v1 — see non-goals in §3); a user wanting several strikes adds each one individually, same as adding several stocks.

## 9. Stock list resolution

Instead of adding stocks one at a time, a user can type/select the name of a **list** and have it expand into all of that list's member symbols in one step. Two kinds of lists:

- **Bundled index lists** — shipped with the app, covering common index constituents: NIFTY 50, NIFTY NEXT 50, NIFTY BANK, NIFTY 100, SENSEX, etc. Stored as one CSV file per list (`lists/NIFTY_50.csv` etc.), each just a flat list of the symbol names already used in the symbol lookup table (§7), so resolution is a two-step lookup: list name → member symbol names → tickers.
- **User-defined custom lists** — all of the user's own lists live together in **one Excel workbook**, `My Lists.xlsx`, saved to a visible, ordinary folder (`~/Documents/NSE Data Fetcher/My Lists.xlsx`, alongside where downloads go by default) rather than a hidden config directory. Each **sheet is one list** — the sheet name is the list name (e.g. a sheet named "MY WATCHLIST"), and the sheet's `Symbol` column just lists the member symbols, one per row:

  ```
  Sheet: MY WATCHLIST         Sheet: SWING TRADES
  ┌──────────┐                ┌──────────┐
  │ Symbol   │                │ Symbol   │
  ├──────────┤                ├──────────┤
  │ RELIANCE │                │ TATASTEEL│
  │ TCS      │                │ ADANIENT │
  │ HDFCBANK │                └──────────┘
  └──────────┘
  ```

  This is a deliberate design choice: because it's a plain workbook in a normal folder, the user can open it directly in Excel, add/remove rows on a sheet, add a whole new sheet for a new list, rename a sheet to rename a list, or delete a sheet to delete a list — no in-app editor is required for basic editing, though the app also provides one (below) for convenience.

```python
class ListResolver:
    def resolve(self, list_name: str) -> list[str]:
        """Returns the member symbol names for a bundled list or a sheet
        in the user's My Lists.xlsx workbook."""
```

- **Saving from the app**: clicking "Save current selection as list..." prompts for a name, then opens `My Lists.xlsx` (creating it with a short instructional first sheet if it doesn't exist yet), writes the current symbols into a sheet with that name (overwriting it if the name already exists, after a confirm), and saves the workbook back to disk. Because the file is a normal, user-visible workbook, it's also possible the user has it open in Excel at the same time — if the save fails because the file is locked, the app shows: *"Please close 'My Lists.xlsx' in Excel, then try again."*
- **Reading lists**: every time the entry field's autocomplete needs to know what lists exist (on startup, and after a save), the app re-reads `My Lists.xlsx` and lists every sheet name as an available custom list, alongside the bundled index lists. This means edits made directly in Excel (adding a sheet, editing rows) are picked up automatically the next time the app is opened — no import/sync step needed.
- Blank rows or a header typo'd away are tolerated (first non-empty column is treated as the symbol column, blank rows skipped); a row whose text doesn't resolve to a known symbol is reported at list-load time rather than failing the whole list, e.g. *"List 'MY WATCHLIST' loaded 7 of 8 symbols. Couldn't recognize: 'RELAINCE' — check for a typo."*

Typing a list name behaves exactly like the existing "+ Add" flow for a single symbol, just adding many rows at once — the user can still remove individual symbols afterward before downloading, or add more symbols/lists on top of it. Duplicate symbols (e.g. a user adds both "NIFTY 50" and "RELIANCE" individually) are silently de-duplicated before fetching, so no symbol is downloaded twice or gets two sheets.

**Staleness caveat**: bundled index constituent lists go stale as index composition changes (NSE rebalances NIFTY indices periodically). v1 ships a snapshot and documents in the README that it may drift over time; refreshing it is a matter of updating the bundled CSV files, not code — a "last updated" date is stored alongside each bundled list and shown in the list picker (e.g. "NIFTY 50 (as of Mar 2026)") so the user knows it isn't necessarily live.

## 10. Importing symbols

Beyond typing a symbol or a saved-list name, two more ways to populate the selection list, both one-off imports rather than named/reusable lists (a user who wants an import to be reusable can still hit "Save current selection as list" afterward, per §9):

- **Paste a comma-separated list**: an "Import / Paste..." button opens a small text box where the user pastes text like `RELIANCE, TCS, HDFCBANK` (or one per line — both accepted, since users copy from all kinds of sources). The app splits on commas and/or newlines, trims whitespace, and resolves each token exactly like a typed symbol.
- **Import from a file**: the same dialog offers "Choose a file..." (native file picker, filtered to `.csv`/`.xlsx`/`.xls`). The app reads it using the same convention as `My Lists.xlsx` (§9): the first column with a recognizable header (`Symbol`, or just the first non-empty column if unlabeled) is treated as the symbol column, blank rows skipped. For a `.csv` this is one column on one implicit sheet; for a workbook with **multiple sheets**, every sheet's symbol column is read and merged into one flat list (since an ad-hoc import isn't trying to preserve named groupings the way `My Lists.xlsx` does).
- Both paths feed into the same de-duplication and per-symbol resolution as everything else (§7) — an unresolvable entry doesn't block the rest: *"Imported 18 of 20 symbols from 'my_portfolio.csv'. Couldn't recognize: 'RELAINCE', 'INFY.BSE' — check for typos."*
- Only the symbol column is read; any other columns in the imported file (notes, quantities, purchase price, etc. — common in a personal portfolio spreadsheet) are ignored rather than causing an error, so users can point the importer directly at a spreadsheet they already keep for other purposes.

## 11. UI design

Single-window form, no menus, no tabs:

```
┌─────────────────────────────────────────────────┐
│  NSE Data Fetcher                                │
│                                                   │
│  Add a stock, index, or a saved list:            │
│  [ NIFTY 50                    ▼ ]  [ + Add ]    │
│    (type a symbol like RELIANCE, or a list       │
│     like "NIFTY 50" / "MY WATCHLIST")            │
│                                                   │
│  [ Import / Paste... ]  [ Add options contract...]│
│                                                   │
│   • RELIANCE            [x]                      │
│   • TCS                 [x]                      │
│   • HDFCBANK             [x]      (47 more...)   │
│   • NIFTY 26-Sep-2026 25000 CE  [x]              │
│                                                   │
│              [ Save current selection as list ]  │
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

- Entry field: one autocomplete dropdown that suggests both individual symbols and list names (visually distinguished, e.g. lists shown in bold or with a small folder icon and a count, "NIFTY 50 — 50 stocks"); "+ Add" either appends one symbol row or expands a list into many rows at once. At least one symbol is required before Download is enabled.
- "Import / Paste...": opens the small dialog described in §10 — a text box for pasting comma/newline-separated symbols, or a "Choose a file..." button for an existing CSV/Excel file.
- "Add options contract...": opens the underlying/expiry/strike/CE-PE sub-form described in §8; adds one contract row to the selection list per use.
- Selection list: shows every resolved symbol individually (even ones added via a list) so the user can remove specific stocks after loading a list; long lists collapse to a scrollable area rather than growing the window unboundedly.
- "Save current selection as list": prompts for a name and persists the current symbol selection as a new sheet in the user's `My Lists.xlsx` workbook (§9), so a user's own frequently-downloaded basket doesn't need to be rebuilt by hand each time, and can hold multiple such lists side by side (one per sheet).
- Interval: a small set of radio buttons (not a free-text field) — 5 min, 15 min, 1 hour, Daily — so users are never asked to type interval syntax.
- Date pickers: calendar widgets (no manual date-format guessing), defaulting To-date to today and From-date to one year back (adjusted automatically — with a message — when the chosen interval can't support that far back, per §6).
- Folder field: pre-filled with the OS's default Documents folder, with a native "Browse..." dialog.
- Download button: disabled while a request is in flight; status line shows per-symbol progress ("Fetching RELIANCE (1/50)...", then "Saved to ~/Documents/NSE_Data_2024-01-01_2024-12-31.xlsx") or a plain-language error. If some symbols fail and others succeed, the status line names both the saved file and which symbols were skipped and why.
- Output filename auto-generated as `NSE_Data_<from>_<to>.xlsx` for multi-symbol downloads (or `<SYMBOL>_<from>_<to>.xlsx` when only one symbol is selected), so users don't have to name files themselves.

## 12. Excel output format

- One workbook per download; **one sheet per symbol**, named after the symbol (sheet names sanitized/truncated for Excel's naming restrictions, e.g. 31-char limit and no `: \ / ? * [ ]` — an options contract's long name like "NIFTY 26-Sep-2026 25000 CE" is abbreviated to fit, e.g. "NIFTY_26Sep26_25000CE").
- Columns for equities/indices/futures: `Date, Open, High, Low, Close, Volume` for Daily/1-hour data, or `Date, Time, Open, High, Low, Close, Volume` for intraday (5 min/15 min) so the timestamp is legible without a combined datetime column. Adjusted Close included for equities where the source provides it. Futures sheets additionally include `Open Interest`.
- Columns for options contracts: `Date, Open, High, Low, Close, Settle Price, Volume, Open Interest, Change in OI` (Daily only, per §6) — the header row and column set differ from an equity sheet in the same workbook, since the two instrument types carry genuinely different information; the app doesn't force option sheets into the equity column shape just for superficial consistency.
- Header row bold, column widths auto-sized, date/time columns formatted as date/time (not text) — done via `openpyxl`.
- Rows sorted oldest → newest, within each sheet.
- A symbol that fails to fetch does **not** get an empty/blank sheet — it's simply omitted from the workbook and reported in the status line, so the user never has to figure out which sheets are empty and why.

## 13. Tech stack

- **Language**: Python 3.11+
- **GUI**: `tkinter` (stdlib — no extra install for end users) with `tkcalendar` for date pickers
- **Data fetch**: `yfinance`, `nsepython` (or `jugaad-data`) for NSE-specific/futures data
- **Excel**: `pandas` + `openpyxl`
- **Packaging**: `PyInstaller` to produce a single-file `.app` (macOS) / `.exe` (Windows) so the end user just double-clicks — no Python, no pip, no terminal.

## 14. Error handling (user-facing)

| Situation                          | Message shown to user |
|-------------------------------------|--------------------------|
| Symbol not found / no match          | "We couldn't find '<input>'. Try a name like RELIANCE, NIFTY 50, or TCS." |
| List name not found / no match       | "We couldn't find a list called '<input>'. Try NIFTY 50, NIFTY BANK, or one of your saved lists." |
| A row in a custom list doesn't resolve to a known symbol | "List 'MY WATCHLIST' loaded 7 of 8 symbols. Couldn't recognize: 'RELAINCE' — check for a typo." |
| `My Lists.xlsx` is open in Excel when the app tries to save to it | "Please close 'My Lists.xlsx' in Excel, then try again." |
| Pasted/imported text has one or more unrecognized entries | "Imported 18 of 20 symbols from 'my_portfolio.csv'. Couldn't recognize: 'RELAINCE', 'INFY.BSE' — check for typos." |
| Imported file has no recognizable symbol column | "We couldn't find a column of symbols in that file. Make sure one column is headed 'Symbol' (or is the first column)." |
| No expiries/strikes could be fetched for an options underlying | "Couldn't load expiry/strike list for NIFTY right now — you can still type them in manually, but they won't be checked." |
| Requested option contract doesn't exist (bad strike/expiry combo) | "No contract found for NIFTY 26-Sep-2026 25000 CE. Double-check the strike and expiry." |
| No internet connection               | "No internet connection. Please check your connection and try again." |
| No data for the date range (e.g. holiday-only range, future dates) | "No trading data found for that date range." |
| Date range too long for the chosen interval | "5-minute data is only available for the last 60 days. Download from 2026-07-14 to today instead?" (Yes clamps and continues, No lets the user change the interval or dates.) |
| One symbol fails, others in the batch succeed | Workbook is still saved with the successful symbols; status line reads "Saved 2 of 3 symbols. TCS was skipped: no data found." |
| Folder not writable                  | "Can't save to that folder — please choose a different one." |

No stack traces or raw exceptions ever reach the UI; all exceptions are caught at the adapter/orchestration boundary and translated to one of the above.

## 15. Project layout (proposed)

```
nse-data-fetcher/
├── docs/
│   └── DESIGN.md
├── src/
│   ├── main.py               # GUI entry point
│   ├── symbols.py            # symbol lookup + fuzzy match
│   ├── symbols_table.csv     # bundled name -> ticker/adapter mapping
│   ├── lists.py               # ListResolver: bundled CSVs + My Lists.xlsx
│   ├── lists/                 # bundled index constituent lists
│   │   ├── NIFTY_50.csv
│   │   ├── NIFTY_BANK.csv
│   │   └── SENSEX.csv
│   ├── options.py             # options sub-form logic: underlying/expiry/
│   │                           # strike/CE-PE -> one contract symbol
│   ├── importer.py            # paste-text and CSV/Excel file import parsing
│   ├── datasources/
│   │   ├── base.py           # DataSource protocol
│   │   ├── yfinance_source.py
│   │   └── nse_source.py     # futures, options & NSE-specific fallback
│   └── excel_writer.py
├── tests/
├── requirements.txt
└── README.md
```

Custom user-defined lists are **not** bundled with the app — they live in `~/Documents/NSE Data Fetcher/My Lists.xlsx`, a normal, user-visible workbook (one sheet per list) separate from the app's own installed files, so they survive an app update/reinstall and can be opened and edited directly in Excel (§9).

## 16. Open questions / future scope

- Should futures contract selection (which expiry) be automatic ("nearest") or user-selectable? v1: default to nearest/current-month expiry, revisit if requested.
- BSE-only symbols and smaller-cap coverage may be inconsistent across data sources — acceptable gap for v1, documented in the README.
- Is there a practical cap on how many symbols can go in one batch (e.g. 20) to keep a single download from taking too long / hitting rate limits? v1: no hard cap, but fetch sequentially with visible per-symbol progress so a large batch is at least transparent, not frozen.
- How often should bundled index lists (NIFTY 50 etc.) be refreshed, and by whom? v1: manual refresh of the bundled CSVs as part of releases; no in-app auto-update from a live index-constituent source.
- `My Lists.xlsx` location on Windows: `~/Documents/NSE Data Fetcher/` resolves the same way as on macOS (the OS's Documents folder), so no separate `%APPDATA%` path is needed for this file, unlike the earlier per-user config directory idea it replaces.
- Should a whole options chain (all strikes for one underlying/expiry) be addable in one action, rather than one contract at a time? v1 deliberately keeps it one-at-a-time (§8) to keep the sub-form simple; revisit if users find that tedious.
- NSE's options/futures historical-data endpoints are unofficial and scrape-based — they may change format or rate-limit more aggressively than the equity endpoints; worth monitoring once real usage starts.
- Possible v2: weekly/monthly intervals (trivial resample of daily), CSV export option, remembering the user's last-used symbol list/interval between sessions, bulk-adding an entire options chain.
