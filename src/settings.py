"""Persists user-configurable default paths: the download folder and the
custom-lists folder.

Stored as a small JSON file in the app's own Documents subfolder -- the
same fixed location app.log and (by default) My Lists.xlsx already use.
That location has to stay fixed even though the paths it stores can move
the lists/downloads elsewhere, so there's always one well-known place to
bootstrap everything else from.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def default_documents_dir() -> Path:
    """Return the OS's Documents folder, which is the same call on macOS/Windows."""
    return Path.home() / "Documents"


SETTINGS_PATH = default_documents_dir() / "NSE Data Fetcher" / "settings.json"


def _load() -> dict:
    """Read the settings file, returning {} if it's missing, corrupt, or unreadable."""
    try:
        return json.loads(SETTINGS_PATH.read_text())
    except (FileNotFoundError, ValueError):
        return {}
    except OSError:
        logger.warning("Couldn't read settings file", exc_info=True)
        return {}


def _update(key: str, value: Path) -> None:
    """Merge `key: str(value)` into the settings file, creating its folder if needed."""
    settings = _load()
    settings[key] = str(value)
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2))


def get_download_folder() -> Path:
    """Return the user's configured default download folder, or Documents if unset."""
    saved = _load().get("download_folder")
    return Path(saved) if saved else default_documents_dir()


def set_download_folder(path: Path) -> None:
    """Persist `path` as the default download folder."""
    _update("download_folder", path)


def get_lists_folder() -> Path:
    """Return the user's configured custom-lists folder, or the app's default subfolder if unset."""
    saved = _load().get("lists_folder")
    return Path(saved) if saved else default_documents_dir() / "NSE Data Fetcher"


def set_lists_folder(path: Path) -> None:
    """Persist `path` as the custom-lists folder."""
    _update("lists_folder", path)
