"""Write GPS coordinates into an image's EXIF (manual geotagging)."""

from __future__ import annotations

import os
import shutil
import tempfile
from fractions import Fraction
from pathlib import Path
from typing import Optional, Tuple

try:
    import piexif
except ImportError as exc:  # pragma: no cover - import guard
    raise ImportError("Missing 'piexif'. Install: pip install piexif") from exc

WRITABLE_SUFFIXES = {".jpg", ".jpeg", ".jpe", ".tif", ".tiff", ".webp"}


def _to_dms(value: float) -> Tuple[Tuple[int, int], Tuple[int, int], Tuple[int, int]]:
    """Convert decimal degrees to the EXIF rational (deg, min, sec) triple."""
    value = abs(float(value))
    degrees = int(value)
    minutes_full = (value - degrees) * 60
    minutes = int(minutes_full)
    seconds = (minutes_full - minutes) * 60
    # Thousandths of a second is ~3 cm of precision: plenty, and keeps the
    # rationals small enough for every EXIF reader.
    seconds_rational = Fraction(round(seconds * 1000), 1000).limit_denominator(10000)
    return (
        (degrees, 1),
        (minutes, 1),
        (seconds_rational.numerator, seconds_rational.denominator),
    )


def validate_coordinates(latitude: float, longitude: float) -> Tuple[float, float]:
    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except (TypeError, ValueError) as exc:
        raise ValueError("Latitude and longitude must be numbers.") from exc
    if not -90.0 <= latitude <= 90.0:
        raise ValueError(f"Latitude {latitude} is outside the valid range -90 to 90.")
    if not -180.0 <= longitude <= 180.0:
        raise ValueError(f"Longitude {longitude} is outside the valid range -180 to 180.")
    return latitude, longitude


def write_gps(
    image_path,
    latitude: float,
    longitude: float,
    altitude: Optional[float] = None,
    output_path=None,
    backup: bool = True,
) -> Path:
    """Write GPS tags into *image_path* (or a copy at *output_path*).

    The file is rewritten via a temporary file, so an interrupted write cannot
    corrupt the original.
    """
    source = Path(image_path)
    if not source.is_file():
        raise FileNotFoundError(f"File not found: {source}")

    suffix = source.suffix.lower()
    if suffix not in WRITABLE_SUFFIXES:
        raise ValueError(
            f"Cannot write EXIF GPS into '{suffix or 'unknown'}' files. "
            f"Supported: {', '.join(sorted(WRITABLE_SUFFIXES))}"
        )

    latitude, longitude = validate_coordinates(latitude, longitude)
    destination = Path(output_path) if output_path else source

    try:
        exif_dict = piexif.load(str(source))
    except Exception:
        exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
    exif_dict.setdefault("GPS", {})

    gps = {
        piexif.GPSIFD.GPSVersionID: (2, 3, 0, 0),
        piexif.GPSIFD.GPSLatitudeRef: "N" if latitude >= 0 else "S",
        piexif.GPSIFD.GPSLatitude: _to_dms(latitude),
        piexif.GPSIFD.GPSLongitudeRef: "E" if longitude >= 0 else "W",
        piexif.GPSIFD.GPSLongitude: _to_dms(longitude),
    }
    if altitude is not None:
        altitude = float(altitude)
        rational = Fraction(round(abs(altitude) * 100), 100).limit_denominator(10000)
        gps[piexif.GPSIFD.GPSAltitudeRef] = 0 if altitude >= 0 else 1
        gps[piexif.GPSIFD.GPSAltitude] = (rational.numerator, rational.denominator)

    exif_dict["GPS"].update(gps)

    try:
        exif_bytes = piexif.dump(exif_dict)
    except Exception:
        # Some cameras write maker notes piexif cannot round-trip; drop the
        # unparseable sections rather than failing the whole operation.
        exif_dict.pop("thumbnail", None)
        exif_dict["1st"] = {}
        exif_bytes = piexif.dump({"0th": exif_dict.get("0th", {}), "Exif": exif_dict.get("Exif", {}),
                                  "GPS": exif_dict["GPS"], "1st": {}, "thumbnail": None})

    if backup and destination == source:
        shutil.copy2(source, _backup_path(source))

    if destination.parent and not destination.parent.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)

    handle = tempfile.NamedTemporaryFile(
        dir=str(destination.parent or "."), prefix=".geotag-", suffix=source.suffix, delete=False
    )
    handle.close()
    temp_path = Path(handle.name)
    try:
        shutil.copy2(source, temp_path)
        piexif.insert(exif_bytes, str(temp_path))
        os.replace(temp_path, destination)
    except BaseException:
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise

    return destination


def _backup_path(source: Path) -> Path:
    backup = source.with_name(source.name + ".bak")
    counter = 1
    while backup.exists():
        backup = source.with_name(f"{source.name}.bak{counter}")
        counter += 1
    return backup


def remove_gps(image_path, output_path=None, backup: bool = True) -> Path:
    """Strip only the GPS block, leaving the rest of the EXIF intact."""
    source = Path(image_path)
    if not source.is_file():
        raise FileNotFoundError(f"File not found: {source}")
    destination = Path(output_path) if output_path else source

    try:
        exif_dict = piexif.load(str(source))
    except Exception as exc:
        raise ValueError(f"Could not read EXIF from {source.name}: {exc}") from exc

    exif_dict["GPS"] = {}
    exif_bytes = piexif.dump(exif_dict)

    if backup and destination == source:
        shutil.copy2(source, _backup_path(source))

    handle = tempfile.NamedTemporaryFile(
        dir=str(destination.parent or "."), prefix=".geotag-", suffix=source.suffix, delete=False
    )
    handle.close()
    temp_path = Path(handle.name)
    try:
        shutil.copy2(source, temp_path)
        piexif.insert(exif_bytes, str(temp_path))
        os.replace(temp_path, destination)
    except BaseException:
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise
    return destination


def parse_coordinate_text(text: str) -> Tuple[float, float]:
    """Parse 'lat, lon' in decimal or 48°51'29.5\"N 2°17'40.1\"E form."""
    import re

    text = (text or "").strip()
    if not text:
        raise ValueError("No coordinates given.")

    # Accept a pasted Google Maps URL.
    url_match = re.search(r"[?&]q=(-?\d+\.?\d*),\s*(-?\d+\.?\d*)", text)
    if not url_match:
        url_match = re.search(r"@(-?\d+\.?\d*),(-?\d+\.?\d*)", text)
    if url_match:
        return validate_coordinates(float(url_match.group(1)), float(url_match.group(2)))

    dms = re.findall(
        r"(\d+(?:\.\d+)?)\s*[°d:]\s*(?:(\d+(?:\.\d+)?)\s*['m:]\s*)?(?:(\d+(?:\.\d+)?)\s*[\"s]?\s*)?([NSEW])",
        text,
        re.IGNORECASE,
    )
    if len(dms) == 2:
        values = []
        for degrees, minutes, seconds, ref in dms:
            value = float(degrees) + float(minutes or 0) / 60 + float(seconds or 0) / 3600
            if ref.upper() in ("S", "W"):
                value = -value
            values.append((ref.upper(), value))
        latitude = next(v for ref, v in values if ref in ("N", "S"))
        longitude = next(v for ref, v in values if ref in ("E", "W"))
        return validate_coordinates(latitude, longitude)

    numbers = re.findall(r"-?\d+\.?\d*", text)
    if len(numbers) >= 2:
        return validate_coordinates(float(numbers[0]), float(numbers[1]))

    raise ValueError(f"Could not read coordinates from {text!r}.")
