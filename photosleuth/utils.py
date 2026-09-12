"""Shared helpers: banner, console-safe output, geocode cache, image discovery."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional

from .config import config_home

BANNER = r"""
   ██████╗ ██╗  ██╗ ██████╗ ████████╗ ██████╗ ███████╗██╗     ███████╗██╗   ██╗████████╗██╗  ██╗
   ██╔══██╗██║  ██║██╔═══██╗╚══██╔══╝██╔═══██╗██╔════╝██║     ██╔════╝██║   ██║╚══██╔══╝██║  ██║
   ██████╔╝███████║██║   ██║   ██║   ██║   ██║█████╗  ██║     █████╗  ██║   ██║   ██║   ███████║
   ██╔═══╝ ██╔══██║██║   ██║   ██║   ██║   ██║██╔══╝  ██║     ██╔══╝  ██║   ██║   ██║   ██╔══██║
   ██║     ██║  ██║╚██████╔╝   ██║   ╚██████╔╝███████╗███████╗███████╗╚██████╔╝   ██║   ██║  ██║
   ╚═╝     ╚═╝  ╚═╝ ╚═════╝    ╚═╝    ╚═════╝ ╚══════╝╚══════╝╚══════╝ ╚═════╝    ╚═╝   ╚═╝  ╚═╝

   PhotoSleuth  |  Unleash the secrets of your images
"""

IMAGE_EXTENSIONS = (
    ".jpg", ".jpeg", ".jpe", ".png", ".tif", ".tiff",
    ".bmp", ".gif", ".webp", ".heic", ".heif", ".dng", ".cr2", ".nef", ".arw",
)

# Cosmetic glyphs are replaced when the console cannot represent them, which is
# the default on Windows terminals using a legacy code page (cp1252/cp437).
_ASCII_FALLBACKS = {
    "📄": "[file]", "📦": "[size]", "🕒": "[time]", "📍": "[gps]",
    "🏠": "[addr]", "🗺️": "[map]", "🗺": "[map]", "📋": "[exif]",
    "✅": "[ok]", "❌": "[!]", "⚠️": "[warn]", "⚠": "[warn]",
    "🔍": "[*]", "👋": "", "📷": "[cam]", "⛰️": "[alt]", "⛰": "[alt]",
    "🔗": "[link]", "🧭": "[dir]", "🧹": "[clean]",
}


def supports_unicode(stream=None) -> bool:
    """True when *stream* can encode the box-drawing/emoji characters we use."""
    stream = stream if stream is not None else sys.stdout
    encoding = getattr(stream, "encoding", None) or "ascii"
    try:
        "█─📄✅".encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return False
    return True


def to_console_safe(text: str, stream=None) -> str:
    """Downgrade *text* so it can always be printed to *stream*."""
    if supports_unicode(stream):
        return text
    for glyph, replacement in _ASCII_FALLBACKS.items():
        text = text.replace(glyph, replacement)
    encoding = getattr(stream if stream is not None else sys.stdout, "encoding", None) or "ascii"
    return text.encode(encoding, errors="replace").decode(encoding, errors="replace")


def safe_print(text: str = "", stream=None, **kwargs) -> None:
    """print() that never dies with UnicodeEncodeError on a legacy console."""
    stream = stream if stream is not None else sys.stdout
    try:
        print(text, file=stream, **kwargs)
    except UnicodeEncodeError:
        print(to_console_safe(text, stream), file=stream, **kwargs)


def banner(stream=None) -> str:
    """The banner, rendered in ASCII when the console cannot do better."""
    if supports_unicode(stream):
        return BANNER
    return (
        "\n"
        "   ==========================================\n"
        "     P H O T O S L E U T H\n"
        "     Unleash the secrets of your images\n"
        "   ==========================================\n"
    )


class RateLimiter:
    """Blocks so that successive calls are at least *min_interval* apart.

    Nominatim's usage policy allows one request per second; exceeding it gets
    the client blocked, which is what made batch geocoding fail.
    """

    def __init__(self, min_interval: float = 1.0):
        self.min_interval = max(0.0, float(min_interval))
        self._lock = threading.Lock()
        self._last_call = 0.0

    def wait(self) -> None:
        if self.min_interval <= 0:
            return
        with self._lock:
            elapsed = time.monotonic() - self._last_call
            remaining = self.min_interval - elapsed
            if remaining > 0:
                time.sleep(remaining)
            self._last_call = time.monotonic()


class GeocodeCache:
    """Geocode cache that persists between runs, as the README promises."""

    def __init__(self, path: Optional[Path] = None, enabled: bool = True):
        self.path = Path(path) if path else config_home() / "geocode_cache.json"
        self.enabled = enabled
        self._lock = threading.Lock()
        self._entries: Dict[str, str] = {}
        self._loaded = False

    @staticmethod
    def _key(lat: float, lon: float) -> str:
        return f"{float(lat):.5f},{float(lon):.5f}"

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.enabled:
            return
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                self._entries = {str(k): str(v) for k, v in data.items()}
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            self._entries = {}

    def get(self, lat: float, lon: float) -> Optional[str]:
        if not self.enabled:
            return None
        with self._lock:
            self._load()
            return self._entries.get(self._key(lat, lon))

    def set(self, lat: float, lon: float, address: str) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._load()
            self._entries[self._key(lat, lon)] = address
            self._flush()

    def clear(self) -> None:
        with self._lock:
            self._loaded = True
            self._entries = {}
            self._flush()

    def _flush(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle = tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=str(self.path.parent),
                prefix=".cache-", suffix=".tmp", delete=False,
            )
            try:
                with handle:
                    json.dump(self._entries, handle)
                os.replace(handle.name, self.path)
            except BaseException:
                try:
                    os.unlink(handle.name)
                except OSError:
                    pass
                raise
        except OSError:
            # A read-only config dir must not break analysis.
            pass


_default_cache: Optional[GeocodeCache] = None


def default_cache() -> GeocodeCache:
    global _default_cache
    if _default_cache is None:
        from .config import load_config
        settings = load_config().get("geocoding", {})
        _default_cache = GeocodeCache(enabled=bool(settings.get("cache_enabled", True)))
    return _default_cache


def reset_default_cache() -> None:
    """Drop the memoised cache instance (used by tests and by config changes)."""
    global _default_cache
    _default_cache = None


def get_cached_geocode(lat: float, lon: float) -> Optional[str]:
    return default_cache().get(lat, lon)


def set_cached_geocode(lat: float, lon: float, address: str) -> None:
    default_cache().set(lat, lon, address)


def iter_images(
    directory,
    recursive: bool = False,
    extensions: Iterable[str] = IMAGE_EXTENSIONS,
) -> Iterator[Path]:
    """Yield image files in *directory*, sorted, skipping directories.

    ``Path.iterdir()`` alone also yielded directories whose *name* ended in an
    image extension, which then blew up during metadata extraction.
    """
    root = Path(directory)
    suffixes = {ext.lower() for ext in extensions}
    walker = root.rglob("*") if recursive else root.iterdir()
    for entry in sorted(walker):
        try:
            if entry.is_file() and entry.suffix.lower() in suffixes:
                yield entry
        except OSError:
            continue


def find_images(directory, recursive: bool = False) -> List[Path]:
    return list(iter_images(directory, recursive=recursive))


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024.0 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} GB"
