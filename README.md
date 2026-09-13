# NSE Data Fetcher

A simple desktop app to download historical OHLCV (Open, High, Low, Close, Volume) data for Indian stocks and indices, and save it as an Excel workbook (one sheet per symbol). No coding or terminal required to use it.

See [docs/DESIGN.md](docs/DESIGN.md) for the full design doc.

## Status

Core implementation in place: symbol/list resolution, multi-symbol batch download, selectable intervals, paste/file import, and a Tkinter GUI. Not yet packaged as a standalone `.app`/`.exe` (see Packaging below).

## Running it (for developers)

The GUI needs a Python build with Tk support. On macOS, Homebrew's Python often lacks this — use the system Python (or any Python built with `--with-tcl-tk`) to create the virtualenv:

```bash
/usr/bin/python3 -m venv .venv        # macOS: system Python has tkinter built in
source .venv/bin/activate             # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cd src
python main.py
```

Run the test suite from the project root (with the venv active):

```bash
python -m pytest tests/
```

## Notes on data sources

- Equities and major indices are fetched via `yfinance` (Yahoo Finance) and generally work reliably.
- Index constituents and the full NSE equity list are fetched live from NSE's own unofficial public endpoints (via plain `requests` calls), used to validate symbols and refresh bundled index lists. These endpoints are undocumented and can be blocked or fail depending on network/IP — during development, calls to them were blocked entirely from this sandboxed environment. Any failure here falls back to the bundled/cached data rather than crashing, but real-world reliability of the live-fetch path should be verified from a normal home/office network before relying on it. These live fetches run on a background thread at startup so the app's first autocomplete lookup doesn't have to wait on them.

## Packaging as a standalone app

The plan (§13 of the design doc) is to use PyInstaller, run separately on each target OS (it does not cross-compile). `symbols_table.csv` and the bundled `lists/` folder are plain data files, not Python modules, so PyInstaller won't pick them up on its own -- they must be passed explicitly via `--add-data`, or `SymbolResolver`/`ListResolver` will raise `FileNotFoundError` at startup looking for them inside the `_MEIxxxxx` temp extraction folder. The `--add-data SRC:DEST` separator is `:` on macOS/Linux and `;` on Windows:

```bash
pip install pyinstaller
cd src
# macOS/Linux:
pyinstaller --onedir --windowed --name "NSE Data Fetcher" --add-data "symbols_table.csv:." --add-data "lists:lists" main.py
# Windows:
pyinstaller --onedir --windowed --name "NSE Data Fetcher" --add-data "symbols_table.csv;." --add-data "lists;lists" main.py
```

Use `--onedir`, not `--onefile`: a onefile build has to re-extract its entire archive to a fresh temp folder on *every* launch, which is the main reason it's slow to start -- onedir pays that cost once (when it's built), then launches directly from the already-unpacked folder. Zip the resulting `dist/NSE Data Fetcher/` folder (macOS: the `dist/NSE Data Fetcher.app` bundle) for distribution -- see `.github/workflows/release.yml`, which already does this.

## Publishing a release

`.github/workflows/release.yml` builds both the Windows and macOS apps (each on its native runner, since PyInstaller doesn't cross-compile), zips each one, and attaches both to a GitHub Release. To cut one:

```bash
git tag v1.0.0
git push origin v1.0.0
```

That triggers the workflow, which publishes a Release named after the tag with `NSE-Data-Fetcher-Windows.zip` and `NSE-Data-Fetcher-macOS.zip` attached — from there anyone can grab the file straight from the repo's Releases page, no Python or building required. Pushing to a branch, or running the workflow manually from the Actions tab, builds and uploads the same files as workflow artifacts without publishing a Release, so a build can be sanity-checked first.
