"""Offline time-zone lookup from a compact raster.

``timezonefinder`` carries 32 MB of boundary polygons - more than a tenth of
the installed application - to answer one question: which zone is this point in?
PhotoSleuth ships a 43 KB raster of the same answer instead, sampled on a
quarter-degree grid (see ``tools/build_timezone_raster.py``).

The honest cost is precision at borders, roughly 28 km at the equator. Rather
than pretend otherwise, :func:`zone_at` reports when a point sits near a
boundary so callers can soften their verdict instead of asserting something
they cannot know.

If ``timezonefinder`` happens to be installed it is used instead, exactly.
"""

from __future__ import annotations

import json
import struct
import threading
import zlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

RASTER = Path(__file__).resolve().parent.parent / "assets" / "timezones.bin"
MAGIC = b"PSTZ"


@dataclass(frozen=True)
class ZoneLookup:
    """Which zone a point is in, and how much to trust it."""

    name: Optional[str]
    near_border: bool = False
    source: str = "raster"

    @property
    def found(self) -> bool:
        return bool(self.name)


class _Raster:
    """Lazily decompressed grid of zone indices."""

    def __init__(self, path: Path = RASTER) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._loaded = False
        self._names: List[str] = []
        self._grid = None
        self._rows = 0
        self._cols = 0
        self._step = 0.25

    def _load(self) -> bool:
        if self._loaded:
            return self._grid is not None
        with self._lock:
            if self._loaded:
                return self._grid is not None
            self._loaded = True
            try:
                import numpy as np

                with open(self.path, "rb") as handle:
                    if handle.read(4) != MAGIC:
                        return False
                    _version, rows, cols, step = struct.unpack("<HHHf", handle.read(10))
                    (names_length,) = struct.unpack("<I", handle.read(4))
                    names = json.loads(handle.read(names_length).decode("utf-8"))
                    (body_length,) = struct.unpack("<I", handle.read(4))
                    body = zlib.decompress(handle.read(body_length))

                grid = np.frombuffer(body, dtype=np.uint16).reshape(rows, cols)
                self._names = list(names)
                self._grid = grid
                self._rows, self._cols, self._step = rows, cols, float(step)
            except Exception:
                self._grid = None
        return self._grid is not None

    def _cell(self, latitude: float, longitude: float) -> Tuple[int, int]:
        row = int((latitude + 90.0) / self._step)
        col = int((((longitude + 180.0) % 360.0)) / self._step)
        row = max(0, min(self._rows - 1, row))
        col = max(0, min(self._cols - 1, col))
        return row, col

    def lookup(self, latitude: float, longitude: float) -> ZoneLookup:
        if not self._load():
            return ZoneLookup(None, source="unavailable")

        row, col = self._cell(latitude, longitude)
        index = int(self._grid[row, col])
        name = self._names[index] if index < len(self._names) else ""

        # If any neighbouring cell holds a different zone, this point is within
        # about a cell of a boundary and the answer cannot be trusted outright.
        near_border = False
        for row_offset in (-1, 0, 1):
            for col_offset in (-1, 0, 1):
                if row_offset == 0 and col_offset == 0:
                    continue
                neighbour_row = min(max(row + row_offset, 0), self._rows - 1)
                neighbour_col = (col + col_offset) % self._cols
                if int(self._grid[neighbour_row, neighbour_col]) != index:
                    near_border = True
                    break
            if near_border:
                break

        return ZoneLookup(name or None, near_border=near_border)


_raster = _Raster()
_finder = None
_finder_checked = False


def _precise_finder():
    """Use timezonefinder when it is installed; it is exact."""
    global _finder, _finder_checked
    if _finder_checked:
        return _finder
    _finder_checked = True
    try:
        from timezonefinder import TimezoneFinder

        _finder = TimezoneFinder()
    except Exception:
        _finder = None
    return _finder


def zone_at(latitude: float, longitude: float) -> ZoneLookup:
    """The IANA zone name for a point, with a border warning if relevant."""
    finder = _precise_finder()
    if finder is not None:
        try:
            name = finder.timezone_at(lat=float(latitude), lng=float(longitude))
            return ZoneLookup(name or None, near_border=False, source="timezonefinder")
        except Exception:
            pass
    return _raster.lookup(float(latitude), float(longitude))


def offset_at(latitude: float, longitude: float, moment: datetime) -> Tuple[Optional[float], ZoneLookup]:
    """UTC offset in hours at a point on a date, plus the zone it came from."""
    lookup = zone_at(latitude, longitude)
    if not lookup.found:
        return None, lookup
    try:
        from zoneinfo import ZoneInfo

        aware = moment.replace(tzinfo=ZoneInfo(lookup.name))
        return aware.utcoffset().total_seconds() / 3600.0, lookup
    except Exception:
        return None, lookup


def nautical_offset(longitude: float) -> float:
    """Fallback for points at sea, where no political zone applies."""
    return round(float(longitude) / 15.0)


def available() -> bool:
    return _precise_finder() is not None or _raster._load()
