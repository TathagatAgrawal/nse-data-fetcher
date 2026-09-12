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
- Index constituents and the full NSE equity list are fetched live from NSE's own unofficial public endpoints (via `nsepython`/`requests`), used to validate symbols and refresh bundled index lists. These endpoints are undocumented and can be blocked or fail depending on network/IP — during development, calls to them were blocked entirely from this sandboxed environment. Any failure here falls back to the bundled/cached data rather than crashing, but real-world reliability of the live-fetch path should be verified from a normal home/office network before relying on it.

## Packaging as a standalone app

Not yet built. The plan (§13 of the design doc) is to use PyInstaller, run separately on each target OS (it does not cross-compile):

```bash
pip install pyinstaller
cd src
pyinstaller --onefile --windowed --name "NSE Data Fetcher" main.py
```
