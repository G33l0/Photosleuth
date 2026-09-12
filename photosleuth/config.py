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
from typing import Any, Dict, List, Optional

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
    "ui": {
        "theme": "system",              # system | light | dark
        "language": "system",
        "thumbnail_size": 160,
        "restore_session": True,
        "confirm_destructive": True,
        "auto_analyze_on_open": True,
        "max_recent": 12,
    },
    "session": {
        "recent_files": [],
        "recent_folders": [],
        "last_folder": "",
        "window_geometry": "",
        "window_state": "",
        "splitter_sizes": [],
        "last_tab": 0,
    },
    "custody": {
        "enabled": True,
        "log_file": "",
    },
    "updates": {
        "check_on_startup": False,
        "repository": "g33l0/photosleuth",
        "last_check": "",
    },
    "reports": {
        "template": "default",
        "custom_template_dir": "",
        "organisation": "",
        "author": "",
        "logo_path": "",
        "accent_colour": "#1694b2",
        "footer_note": "",
        "include_thumbnails": True,
        "include_map": True,
        "include_forensics": True,
        "include_custody": False,
    },
}

# Engines that accept a stored API key.
SEARCH_ENGINES = ("google_vision", "tineye")

# Every engine selectable as the default, including browser-handoff ones.
ALL_SEARCH_ENGINES = (
    "google_vision", "tineye", "google_lens", "yandex", "bing", "tineye_web",
)


PORTABLE_MARKERS = ("portable.txt", "PhotoSleuth.portable", ".portable")


def install_root() -> Path:
    """Directory holding the running executable (frozen) or the package."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def portable_marker() -> Optional[Path]:
    """Return the portable-mode marker file, if one sits beside the app."""
    root = install_root()
    for name in PORTABLE_MARKERS:
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None


def is_portable() -> bool:
    return portable_marker() is not None


def config_home() -> Path:
    """Return the directory holding config.json and the geocode cache."""
    override = os.environ.get("PHOTOSLEUTH_HOME")
    if override:
        return Path(override).expanduser()

    # Portable mode: keep everything next to the executable so the whole app
    # can live on a USB stick without touching the host machine.
    if is_portable():
        return install_root() / "PhotoSleuthData"
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
    if engine not in ALL_SEARCH_ENGINES:
        raise ValueError(
            f"Unknown search engine: {engine!r}. Expected one of {', '.join(ALL_SEARCH_ENGINES)}."
        )
    update_config(default_search_engine=engine)


def remember_recent(kind: str, path) -> List[str]:
    """Push *path* onto the front of a recent-files/folders list."""
    key = "recent_files" if kind == "file" else "recent_folders"
    config = load_config()
    limit = int(config.get("ui", {}).get("max_recent", 12))
    entries = [str(item) for item in config.get("session", {}).get(key, []) if item]
    text = str(path)
    entries = [item for item in entries if item != text]
    entries.insert(0, text)
    entries = entries[:limit]
    update_config(session={key: entries})
    return entries


def recent(kind: str) -> List[str]:
    key = "recent_files" if kind == "file" else "recent_folders"
    return [str(item) for item in load_config().get("session", {}).get(key, []) if item]


def clear_recent() -> None:
    update_config(session={"recent_files": [], "recent_folders": []})


def set_privacy_options(output_suffix: str | None = None, overwrite: bool | None = None) -> None:
    privacy: Dict[str, Any] = {}
    if output_suffix:
        privacy["output_suffix"] = output_suffix
    if overwrite is not None:
        privacy["overwrite"] = bool(overwrite)
    if privacy:
        update_config(privacy=privacy)
