#!/usr/bin/env python3
"""Build the compact time-zone raster PhotoSleuth ships.

``timezonefinder`` is accurate but its boundary data is 32 MB - more than a
tenth of the whole application, for one consistency check. This bakes that data
down to a coarse grid of zone indices, which compresses to a few hundred
kilobytes because oceans and large countries are vast runs of one value.

The cost is precision at borders, which the runtime handles by refusing to
return a hard verdict for any point whose neighbours disagree.

This is a build-time tool: ``timezonefinder`` is a development dependency only.

    pip install timezonefinder
    python tools/build_timezone_raster.py
"""

from __future__ import annotations

import json
import struct
import sys
import zlib
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "photosleuth" / "assets" / "timezones.bin"

# 0.25 degrees is about 28 km at the equator. Borders are handled by the
# neighbour check at runtime rather than by brute-force resolution.
STEP = 0.25
FORMAT_VERSION = 1


def main() -> int:
    try:
        from timezonefinder import TimezoneFinder
    except ImportError:
        print("timezonefinder is required to build the raster:", file=sys.stderr)
        print("    pip install timezonefinder", file=sys.stderr)
        return 1

    finder = TimezoneFinder()

    longitudes = np.arange(-180.0, 180.0, STEP)
    latitudes = np.arange(-90.0, 90.0, STEP)
    rows, cols = len(latitudes), len(longitudes)
    print(f"Sampling {rows} x {cols} = {rows * cols:,} cells at {STEP}°…")

    names: list = [""]                      # index 0 means "no zone here"
    lookup = {"": 0}
    grid = np.zeros((rows, cols), dtype=np.uint16)

    for row, latitude in enumerate(latitudes):
        # Sample cell centres, not corners.
        centre_lat = float(latitude) + STEP / 2.0
        for col, longitude in enumerate(longitudes):
            centre_lon = float(longitude) + STEP / 2.0
            zone = finder.timezone_at(lat=centre_lat, lng=centre_lon) or ""
            index = lookup.get(zone)
            if index is None:
                index = len(names)
                lookup[zone] = index
                names.append(zone)
            grid[row, col] = index
        if row % 100 == 0:
            print(f"  row {row}/{rows} ({row / rows:.0%})")

    payload = json.dumps(names, separators=(",", ":")).encode("utf-8")
    body = zlib.compress(grid.tobytes(), level=9)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "wb") as handle:
        handle.write(b"PSTZ")
        handle.write(struct.pack("<HHHf", FORMAT_VERSION, rows, cols, STEP))
        handle.write(struct.pack("<I", len(payload)))
        handle.write(payload)
        handle.write(struct.pack("<I", len(body)))
        handle.write(body)

    size = OUTPUT.stat().st_size
    print(f"\nWrote {OUTPUT}")
    print(f"  {len(names) - 1} zones, {rows}x{cols} grid")
    print(f"  {size / 1024:.0f} KB  (raw grid would be {grid.nbytes / 1024 / 1024:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
