# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses simple `MAJOR.MINOR.PATCH` version tags rather than strict [Semantic Versioning](https://semver.org/) guarantees while it's still pre-1.0.

## [Unreleased]

## [0.0.6] - 2026-09-13

### Added

- New upfront date validation: 
  - Future 'To' date → now rejected immediately with a clear message, instead of silently fetching nothing.
  - Intraday range entirely outside Yahoo's window (e.g. a narrow 5-minute range from 6 months ago) → rejected with an explicit "5-minute data is only available for the last 60 days... pick a more recent range, or switch to Daily."
- A help dialogue explaining the basic features, and common failures.

### Fixed

- Every intraday (5 min/15 min/1 hour) download failed at the very last step, after successfully fetching all its data: the combined date+time column introduced in 0.0.5 carried timezone info from Yahoo Finance, and openpyxl cannot write a timezone-aware datetime to Excel at all. The column is now converted to naive (tzinfo dropped, wall-clock time unchanged) before writing.
- A real download failure showed a confusing, unrelated `NameError` instead of the actual error message, because the message was read from a variable inside a `lambda` scheduled to run later -- by the time it ran, Python had already cleared that variable, per its own except-block scoping rules. The message is now captured into a plain variable first.
- The 0.0.5 intraday clamp fix used the *advertised* limit (60/730 days) rather than the real one: Yahoo checks against the exact current moment, but every date here is midnight-only, so a start of exactly today-60 was still rejected ("must be within the last 60 days") -- verified directly against Yahoo. The clamp now targets today-59/729, the boundary that actually works.

Together, the first two bugs are almost certainly what produced a batch of many symbols "downloading" (the status line cycled through all of them) while every single one silently failed -- the real cause (a crash while writing the file, immediately after a successful fetch) was being replaced by an unrelated `NameError` and never surfaced to the user at all.

## [0.0.5] - 2026-09-13

### Fixed

- Intraday (5 min/15 min/1 hour) downloaded rows weren't reliably sorted by time within the same day -- the date and time were split into separate columns, and sorting only by the date-only column left same-day rows in no guaranteed order. Combined back into a single date+time column, which sorts correctly.
- Yahoo Finance's intraday history limits (60 days for 5 min/15 min, 730 days for 1 hour) are measured back from *today*, not from the chosen end date -- a date range that was narrow enough but too far in the past was being sent through unclamped and failing outright. The app now clamps relative to today, matching Yahoo's actual behavior.
- On Windows, the date pickers and the symbol lists rendered with a noticeably smaller font than the rest of the UI, and the bottom status/progress row could get clipped out of the window entirely. Both were caused by the plain Tk widgets mixed into the `customtkinter`-based UI not sharing its DPI-aware scaling; the window is now sized from its actual content instead of a fixed guess, and those widgets use the same scaled font as the rest of the app.

## [0.0.4] - 2026-09-13

### Added

- A modern, dark-mode-aware UI, rebuilt on `customtkinter` (rounded buttons, themed colors) instead of plain Tkinter widgets.
- An app icon, shown in the Dock/taskbar/Cmd+Tab/Alt+Tab for the packaged `.exe`/`.app`.
- An optional "File name" field for the downloaded workbook; leaving it blank keeps the existing auto-generated name.
- Arrow-key navigation through the autocomplete suggestions list, with Enter adding the highlighted entry.

### Fixed

- The date pickers' drop-down calendar closed instantly when clicked, and clicking its month/year navigation arrows appeared to freeze it (the month/year actually changed, but the popup vanished immediately after) -- both caused by focus-handling conflicts between `customtkinter` and `tkcalendar` introduced by this release's UI rewrite.

## [0.0.3] - 2026-09-13

### Added

- A "Settings..." dialog to configure the default download folder and the custom-lists folder, persisted across sessions.

### Changed

- The live NSE index-name and equity-list lookups (used for autocomplete and symbol validation) now warm up on a background thread at startup instead of on the first keystroke, removing a ~1 second delay the first time a user typed into the entry field.
- Packaged builds now use PyInstaller's `--onedir` mode instead of `--onefile`. A onefile build has to re-extract its entire archive to a fresh temp folder on every launch; onedir pays that cost once at build time, which noticeably speeds up cold start. The zipped download size is unchanged.

### Removed

- The `nsepython` dependency, which pulled in `scipy` (~100MB, unused by this app) for a single function. Replaced with a direct `requests` call that does the same thing.

## [0.0.2] - 2026-09-12

### Added

- File logging (`applog.py`) to a log file in the app's Documents folder, so failures in the packaged `.exe`/`.app` (which has no console) can actually be diagnosed. Captures every fetch attempt/outcome, uncaught GUI/startup errors, and `yfinance`'s own internal warnings (which otherwise print to a console that doesn't exist in a windowed build).

## [0.0.1] - 2026-09-12

Initial release.

### Added

- Symbol and list resolution: type a stock/index name or a saved list name, with autocomplete suggestions and typo-tolerant matching.
- Live NSE data: index constituents and the full NSE equity list are fetched live where possible, falling back to bundled data (NIFTY 50, NIFTY BANK, SENSEX) when NSE is unreachable.
- Multi-symbol batch download with selectable intervals (5 min / 15 min / 1 hour / daily) and a date range, written to a single Excel workbook (one sheet per symbol). A symbol with no data for the range is skipped without failing the rest of the batch.
- Paste or import symbols from a CSV/Excel file.
- Save the current selection as a custom list, stored as a sheet in a user-editable `My Lists.xlsx` workbook.
- A Tkinter desktop GUI, packaged as standalone Windows and macOS executables via PyInstaller and GitHub Actions.
