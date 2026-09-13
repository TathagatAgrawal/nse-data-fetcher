# NSE Data Fetcher — Help

## What this app does

Downloads historical OHLCV (Open, High, Low, Close, Volume) data for Indian
stocks and indices from Yahoo Finance, and saves it as a single Excel
workbook — one sheet per symbol.

## Adding symbols

Type a stock name, an index name, or a saved list name into the entry field.
Suggestions appear as you type — use the **Up/Down arrow keys** to highlight
one and press **Enter** to add it, or click a suggestion directly.

- A handful of well-known names (e.g. `RELIANCE`, `NIFTY 50`) are matched
  instantly from a bundled table.
- Anything else is checked against a **live fetch of NSE's full equity
  list** the first time you use it — if that succeeds, any real,
  currently-listed NSE symbol works, not just the bundled ones. If NSE is
  unreachable, the app falls back to accepting anything shaped like a
  ticker and lets Yahoo Finance be the final judge of whether it exists.
- A typo close to a known name (e.g. `RELAINCE`) is rejected with a
  suggestion rather than silently guessed wrong.
- You can also paste a comma/newline-separated list of symbols, or import
  them from a CSV/Excel file, via **Import / Paste...**.

## Lists

Typing a list name (instead of a single symbol) adds every symbol in that
list at once.

- **Bundled lists** — NIFTY 50, NIFTY BANK, SENSEX — are refreshed from a
  **live fetch of NSE's index constituents** where possible (SENSEX is a
  BSE index, so it always uses the bundled, possibly slightly stale, copy).
  Any other real NSE index name (e.g. `NIFTY AUTO`) works too, even though
  it isn't one of the three bundled ones.
- **Custom lists** are your own saved selections, stored as separate sheets
  in a `My Lists.xlsx` workbook (see **Settings** below for where). Save
  the current selection via **Save current selection as list...**.

## Intervals and date ranges

Yahoo Finance limits how far back intraday data is available, measured
**from today**, not from whatever end date you pick:

| Interval | Data available for |
|---|---|
| 5 min | the last 60 days |
| 15 min | the last 60 days |
| 1 hour | the last 730 days (~2 years) |
| Daily | effectively unlimited history |

If your chosen range starts further back than that, the app silently
narrows the *start* date to fit and tells you it did so in the status line
after downloading. If your entire range falls outside the window (e.g. a
narrow 5-minute range from 6 months ago), it's rejected upfront with an
explanation, rather than quietly returning nothing.

## Settings

The **Settings...** button lets you change two folders, persisted across
launches:

- **Default download folder** — where the Excel workbook is saved by
  default (still overridable per-download via **Browse...**).
- **Custom lists folder** — where `My Lists.xlsx` lives.

You can also give the output workbook a custom **File name** on the main
screen; leaving it blank keeps the auto-generated name (symbol+dates, or
`NSE_Data_<start>_<end>` for multiple symbols).

## Troubleshooting / common failures

**"Symbol not found"** — the name doesn't match any known symbol, live NSE
symbol, or close typo. Check spelling; a suggestion is offered if one's
close enough.

**"List not found"** — same idea, for list names. Note this is also the
last-resort path for an unrecognized name shaped like neither a symbol nor
a bundled list — if NSE is reachable, it's tried as a live NSE index name
before finally giving up.

**"No trading data found for X in that date range"** (per symbol, shown in
the status line, doesn't stop the rest of the batch) — usually a genuinely
empty result (wrong/delisted ticker, or a date range with no trading days),
but can also mean the live fetch failed silently (blocked network, expired
SSL, etc.) and Yahoo returned nothing. Check `app.log` (see below) to tell
the two apart — it captures Yahoo's own internal warnings, which look
identical in the short message shown here.

**"Invalid date range"** — shown upfront, before any fetching starts, for:
the 'From' date being after the 'To' date, the 'To' date being in the
future, or an intraday range that falls entirely outside the interval's
lookback window (see the table above).

**"Couldn't save list" / workbook locked** — `My Lists.xlsx` is open in
Excel (or another program) and can't be written to. Close it and try again.

**Live NSE fetches (index list refresh, symbol validation) failing** — NSE's
endpoints are unofficial and undocumented; they can be blocked or rate
-limited depending on network/IP. Every such fetch is best-effort: on
failure, the app falls back to its bundled data rather than crashing, but
some features (matching a very new symbol, seeing brand-new indices) won't
work until NSE is reachable again.

## Logs

The packaged app has no console, so failures that don't show a dialog are
logged to a file instead:

- **Windows**: `Documents\NSE Data Fetcher\app.log`
- **macOS**: `Documents/NSE Data Fetcher/app.log`

If something goes wrong and the on-screen message isn't enough to explain
why, this file usually has the full detail (including tracebacks and
Yahoo/NSE's own error text).
