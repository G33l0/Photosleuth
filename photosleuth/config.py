"""Persistent configuration: API keys, privacy defaults, cache location.

The config file lives in a per-user directory (``%APPDATA%\\PhotoSleuth`` on
Windows, ``~/.config/photosleuth`` elsewhere) so that PhotoSleuth behaves the
same no matter which directory it is launched from.  Set ``PHOTOSLEUTH_HOME``
to override the location (handy for tests and portable installs).
"""

from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

APP_NAME = "PhotoSleuth"

DEFAULT_CONFIG: Dict[str, Any] = {
    "api_keys": {
        "google_vision": "",
        "tineye": "",
    },
    "default_search_engine": "google_vision",
    "privacy": {
        "output_suffix": "_clean",
        "overwrite": False,
    },
    "geocoding": {
        "enabled": True,
        "user_agent": "photosleuth",
        "min_delay_seconds": 1.0,
        "timeout_seconds": 10,
        "cache_enabled": True,
    },
}

SEARCH_ENGINES = ("google_vision", "tineye")


def config_home() -> Path:
    """Return the directory holding config.json and the geocode cache."""
    override = os.environ.get("PHOTOSLEUTH_HOME")
    if override:
        return Path(override).expanduser()
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return Path(base) / APP_NAME
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    return base / "photosleuth"


def config_path() -> Path:
    return config_home() / "config.json"


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively overlay *override* on a copy of *base*."""
    merged = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config() -> Dict[str, Any]:
    """Load config, always returning a dict containing every default key.

    A missing, unreadable, corrupt or partially hand-edited file never raises:
    the defaults are merged in so callers can index keys without guarding.
    """
    path = config_path()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            stored = json.load(handle)
    except FileNotFoundError:
        config = copy.deepcopy(DEFAULT_CONFIG)
        try:
            save_config(config)
        except OSError:
            pass
        return config
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        # Keep the damaged file around for the user rather than overwriting it.
        try:
            backup = path.with_suffix(".json.bak")
            os.replace(path, backup)
        except OSError:
            pass
        return copy.deepcopy(DEFAULT_CONFIG)

    if not isinstance(stored, dict):
        return copy.deepcopy(DEFAULT_CONFIG)
    return _deep_merge(DEFAULT_CONFIG, stored)


def save_config(config: Dict[str, Any]) -> Path:
    """Write config atomically so an interrupted write cannot truncate it."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=str(path.parent), prefix=".config-", suffix=".tmp", delete=False
    )
    try:
        with handle:
            json.dump(config, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, path)
    except BaseException:
        try:
            os.unlink(handle.name)
        except OSError:
            pass
        raise
    return path


def update_config(**sections: Dict[str, Any]) -> Dict[str, Any]:
    """Merge *sections* into the config on disk and save.

    Always re-reads before writing, so concurrent edits to other sections are
    not clobbered by a stale in-memory copy.
    """
    config = _deep_merge(load_config(), sections)
    save_config(config)
    return config


def get_api_key(engine: str) -> str:
    return load_config().get("api_keys", {}).get(engine, "")


def set_api_key(engine: str, key: str) -> None:
    if engine not in SEARCH_ENGINES:
        raise ValueError(f"Unknown search engine: {engine!r}. Expected one of {', '.join(SEARCH_ENGINES)}.")
    update_config(api_keys={engine: key.strip()})


def set_default_engine(engine: str) -> None:
    if engine not in SEARCH_ENGINES:
        raise ValueError(f"Unknown search engine: {engine!r}. Expected one of {', '.join(SEARCH_ENGINES)}.")
    update_config(default_search_engine=engine)


def set_privacy_options(output_suffix: str | None = None, overwrite: bool | None = None) -> None:
    privacy: Dict[str, Any] = {}
    if output_suffix:
        privacy["output_suffix"] = output_suffix
    if overwrite is not None:
        privacy["overwrite"] = bool(overwrite)
    if privacy:
        update_config(privacy=privacy)
