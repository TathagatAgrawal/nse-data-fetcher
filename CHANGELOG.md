# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses simple `MAJOR.MINOR.PATCH` version tags rather than strict [Semantic Versioning](https://semver.org/) guarantees while it's still pre-1.0.

## [Unreleased]

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
