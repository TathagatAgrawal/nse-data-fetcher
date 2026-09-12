"""Best-effort live fetch of NSE index names and their member symbols.

NSE has no official public API for this, but it publishes both through
unofficial endpoints/files (see docs/DESIGN.md §6/§16). Every function
here is best-effort and never raises: these endpoints are
undocumented and can be blocked or fail depending on network/IP, so
callers should fall back to a bundled/cached list when a call returns [].
"""

from __future__ import annotations

import csv
import io
import logging

logger = logging.getLogger(__name__)


def fetch_index_names() -> list[str]:
    """Best-effort fetch of every live NSE index name (100+ as of 2026).

    Returns an empty list (never raises) if the lookup fails. Note this
    only covers NSE's own indices -- BSE indices like SENSEX aren't
    included since they're published by BSE, not NSE.
    """
    try:
        import nsepython

        payload = nsepython.nsefetch("https://www.nseindia.com/api/allIndices")
        return [row["index"] for row in payload["data"]]
    except Exception:
        logger.warning("Live NSE index name fetch failed", exc_info=True)
        return []


def fetch_index_constituents(index_name: str) -> list[str]:
    """Best-effort fetch of an NSE index's current member symbols.

    NSE publishes each index's constituents as a CSV named
    ind_<slug>list.csv, where slug is the index name lowercased with
    spaces removed (e.g. "NIFTY 50" -> "nifty50", "NIFTY BANK" ->
    "niftybank") -- verified against a dozen NSE indices (NIFTY
    50/BANK/IT/AUTO/FMCG/PHARMA/500/MIDCAP100/...). Non-NSE indices
    (e.g. BSE's SENSEX) have no such file and always fail here.
    Returns an empty list (never raises) if the lookup fails.
    """
    try:
        import requests

        slug = index_name.lower().replace(" ", "")
        url = f"https://archives.nseindia.com/content/indices/ind_{slug}list.csv"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        rows = csv.DictReader(io.StringIO(response.text))
        return [row["Symbol"].strip() for row in rows if row.get("Symbol", "").strip()]
    except Exception:
        logger.warning("Live NSE constituent fetch failed for %r", index_name, exc_info=True)
        return []
