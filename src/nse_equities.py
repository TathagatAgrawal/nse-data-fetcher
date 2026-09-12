"""Best-effort live fetch of every symbol currently listed on NSE.

NSE publishes its full equity master list as a plain CSV at a stable,
unofficial URL (the same one nsepython's nse_eq_symbols() wraps) -- see
docs/DESIGN.md §6/§16 for why this is best-effort and never raises: the
endpoint is undocumented and can be blocked or fail depending on
network/IP, so callers should fall back to a guess/cache when it returns [].
"""

from __future__ import annotations

import csv
import io
import logging

logger = logging.getLogger(__name__)

EQUITY_LIST_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"


def fetch_equity_symbols() -> list[str]:
    """Best-effort fetch of every symbol currently listed on NSE (~2500 as of 2026).

    Returns an empty list (never raises) if the lookup fails.
    """
    try:
        import requests

        response = requests.get(EQUITY_LIST_URL, timeout=10)
        response.raise_for_status()
        rows = csv.DictReader(io.StringIO(response.text))
        return [row["SYMBOL"].strip() for row in rows if row.get("SYMBOL", "").strip()]
    except Exception:
        logger.warning("Live NSE equity list fetch failed", exc_info=True)
        return []
