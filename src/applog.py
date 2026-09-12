"""File-based logging for diagnosing failures in the packaged .exe/.app.

A --windowed PyInstaller build has no console, so uncaught exceptions and
library warnings (yfinance's own network/parsing failures in particular --
it logs to Python's `logging` module rather than raising for most fetch
failures) are otherwise invisible to the user; there's nowhere for them to
print to. Logging to a file next to My Lists.xlsx keeps a record a user can
actually find and send back when something goes wrong.
"""

from __future__ import annotations

import logging

from lists import default_documents_dir

LOG_PATH = default_documents_dir() / "NSE Data Fetcher" / "app.log"


def setup_logging() -> None:
    """Configure the root logger to append to LOG_PATH, creating its folder if needed.

    Configuring the root logger (rather than just this app's own modules)
    also captures yfinance's internal logger output -- it uses the standard
    `logging` module and propagates to root by default, so its warnings
    about delisted/unavailable symbols end up in the same file.
    """
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=LOG_PATH,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger().info("---- NSE Data Fetcher started ----")
