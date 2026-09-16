"""Core functionality: metadata extraction, GPS conversion, geocoding."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import exifread
except ImportError as exc:  # pragma: no cover - import guard
    raise ImportError("Missing 'exifread'. Install: pip install exifread") from exc

try:
    from geopy.geocoders import Nominatim
    from geopy.exc import GeocoderServiceError, GeocoderTimedOut, GeocoderUnavailable
except ImportError as exc:  # pragma: no cover - import guard
    raise ImportError("Missing 'geopy'. Install: pip install geopy") from exc

from .config import load_config
from .utils import RateLimiter, default_cache, human_size

# exifread logs "File format not recognized." straight to the root logger,
# which polluted stdout when a non-image slipped into a batch.
logging.getLogger("exifread").setLevel(logging.CRITICAL)

# Tags worth surfacing in the compact summary view.
SUMMARY_TAGS = (
    ("Image Make", "Camera make"),
    ("Image Model", "Camera model"),
    ("EXIF LensModel", "Lens"),
    ("EXIF DateTimeOriginal", "Taken"),
    ("EXIF ExposureTime", "Exposure"),
    ("EXIF FNumber", "Aperture"),
    ("EXIF ISOSpeedRatings", "ISO"),
    ("EXIF FocalLength", "Focal length"),
    ("Image Software", "Software"),
    ("Image Artist", "Artist"),
    ("Image Copyright", "Copyright"),
)

_geolocator = None
_rate_limiter: Optional[RateLimiter] = None


def _ratio_to_float(value) -> Optional[float]:
    """Convert an exifread Ratio (or plain number) to float.

    exifread's ``Ratio.num``/``Ratio.den`` are deprecated aliases; the
    supported names are ``numerator``/``denominator``.  Accept both plus plain
    ints/floats so the parser works across exifread 2.x and 3.x.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    numerator = getattr(value, "numerator", None)
    denominator = getattr(value, "denominator", None)
    if numerator is None:
        numerator = getattr(value, "num", None)
        denominator = getattr(value, "den", None)
    if numerator is None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    try:
        denominator = 1 if denominator in (None, 0) else denominator
        return float(numerator) / float(denominator)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def convert_to_decimal(coord) -> Optional[float]:
    """Convert an EXIF GPS coordinate (deg, min, sec) to decimal degrees.

    Tolerates coordinates that carry only degrees, or degrees and minutes,
    which some phones and editing tools write.
    """
    values = getattr(coord, "values", coord)
    if values is None:
        return None
    if isinstance(values, (int, float)):
        return float(values)
    try:
        parts = list(values)
    except TypeError:
        return None
    if not parts:
        return None

    total = 0.0
    for index, divisor in enumerate((1.0, 60.0, 3600.0)):
        if index >= len(parts):
            break
        component = _ratio_to_float(parts[index])
        if component is None:
            return None
        total += component / divisor
    return total


def _ref_letter(ref) -> str:
    """Normalise a GPS reference tag ('N'/'S'/'E'/'W') to a single letter."""
    if ref is None:
        return ""
    values = getattr(ref, "values", ref)
    if isinstance(values, (list, tuple)):
        values = values[0] if values else ""
    if isinstance(values, bytes):
        values = values.decode("ascii", errors="ignore")
    return str(values).strip().upper()[:1]


def _parse_altitude(tags) -> Optional[float]:
    altitude = _ratio_to_float(getattr(tags.get("GPS GPSAltitude"), "values", [None])[0]
                               if tags.get("GPS GPSAltitude") else None)
    if altitude is None:
        return None
    ref = tags.get("GPS GPSAltitudeRef")
    ref_value = getattr(ref, "values", [0]) if ref else [0]
    try:
        below_sea_level = int(ref_value[0]) == 1
    except (TypeError, ValueError, IndexError):
        below_sea_level = False
    return -altitude if below_sea_level else altitude


def _parse_exif_datetime(value: str) -> Optional[str]:
    """Parse the EXIF 'YYYY:MM:DD HH:MM:SS' form into an ISO-8601 string."""
    if not value:
        return None
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y:%m:%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(value).strip(), fmt).isoformat()
        except ValueError:
            continue
    return None


def _geocoding_settings() -> Dict[str, Any]:
    settings = dict(load_config().get("geocoding", {}))
    settings.setdefault("enabled", True)
    settings.setdefault("user_agent", "photosleuth")
    settings.setdefault("min_delay_seconds", 1.0)
    settings.setdefault("timeout_seconds", 10)
    return settings


def _get_geolocator():
    """Build the Nominatim client once and reuse it (keeps the connection warm)."""
    global _geolocator, _rate_limiter
    settings = _geocoding_settings()
    if _geolocator is None:
        _geolocator = Nominatim(
            user_agent=str(settings["user_agent"]),
            timeout=int(settings["timeout_seconds"]),
        )
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(float(settings["min_delay_seconds"]))
    return _geolocator, _rate_limiter


def reset_geocoder() -> None:
    """Forget the cached geolocator so config changes take effect."""
    global _geolocator, _rate_limiter
    _geolocator = None
    _rate_limiter = None


def reverse_geocode(lat: float, lon: float, use_cache: bool = True) -> str:
    """Return a human-readable address for coordinates, with caching.

    Honours Nominatim's one-request-per-second policy; without the delay a
    batch of geotagged photos would get the client rate-limited or blocked.
    """
    if lat is None or lon is None:
        return "No coordinates"
    if not _geocoding_settings()["enabled"]:
        return "Geocoding disabled"

    cache = default_cache()
    if use_cache:
        cached = cache.get(lat, lon)
        if cached:
            return cached

    # Offline, a previously cached address is the best that can be offered -
    # and asking the network anyway would just stall the whole batch.
    from .connectivity import is_online

    if not is_online():
        return "Offline - address not looked up"

    geolocator, limiter = _get_geolocator()
    try:
        limiter.wait()
        location = geolocator.reverse(f"{lat:.6f}, {lon:.6f}")
        address = location.address if location else "Address not found"
    except (GeocoderTimedOut, GeocoderUnavailable, GeocoderServiceError):
        return "Geocoding service unavailable"
    except Exception:
        return "Error during geocoding"

    # Only transient failures are skipped above, so this result is cacheable.
    if use_cache:
        cache.set(lat, lon, address)
    return address


def extract_metadata(image_path, geocode: bool = True) -> Dict[str, Any]:
    """Extract EXIF metadata, parse GPS, and return a structured dict."""
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    try:
        with open(path, "rb") as handle:
            tags = exifread.process_file(handle, details=False)
    except (OSError, ValueError, MemoryError) as exc:
        raise OSError(f"Could not read {path}: {exc}") from exc
    tags = tags or {}

    stat = path.stat()
    metadata: Dict[str, Any] = {
        "file": str(path),
        "name": path.name,
        "size": stat.st_size,
        "size_human": human_size(stat.st_size),
        "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        .astimezone()
        .isoformat(timespec="seconds"),
        "exif": {},
        "summary": {},
        "has_exif": False,
    }

    for tag, value in tags.items():
        if tag in ("JPEGThumbnail", "TIFFThumbnail", "Filename", "EXIF MakerNote"):
            continue
        try:
            metadata["exif"][tag] = str(value)
        except Exception:
            metadata["exif"][tag] = repr(value)

    metadata["has_exif"] = bool(metadata["exif"])

    for tag, label in SUMMARY_TAGS:
        if tag in metadata["exif"]:
            metadata["summary"][label] = metadata["exif"][tag]

    taken = metadata["exif"].get("EXIF DateTimeOriginal") or metadata["exif"].get("Image DateTime")
    if taken:
        metadata["date_taken"] = _parse_exif_datetime(taken) or taken

    gps_lat = tags.get("GPS GPSLatitude")
    gps_lon = tags.get("GPS GPSLongitude")
    if gps_lat and gps_lon:
        lat = convert_to_decimal(gps_lat)
        lon = convert_to_decimal(gps_lon)
        if lat is not None and lon is not None:
            if _ref_letter(tags.get("GPS GPSLatitudeRef")) == "S":
                lat = -lat
            if _ref_letter(tags.get("GPS GPSLongitudeRef")) == "W":
                lon = -lon
            # Reject impossible coordinates rather than geocoding garbage.
            if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
                metadata["gps"] = {"latitude": lat, "longitude": lon}
                altitude = _parse_altitude(tags)
                if altitude is not None:
                    metadata["gps"]["altitude_m"] = round(altitude, 2)
                metadata["map_url"] = f"https://www.google.com/maps?q={lat:.6f},{lon:.6f}"
                metadata["osm_url"] = (
                    f"https://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lon:.6f}#map=17/{lat:.6f}/{lon:.6f}"
                )
                if geocode:
                    metadata["location"] = reverse_geocode(lat, lon)

    return metadata


def format_output(metadata: Dict[str, Any], show_all: bool = False) -> str:
    """Return a formatted string for console output."""
    lines = [
        "",
        f"📄 File: {metadata.get('file', 'unknown')}",
        f"📦 Size: {metadata.get('size_human') or metadata.get('size', 0)}",
        f"🕒 Modified: {metadata.get('modified', 'unknown')}",
    ]
    if metadata.get("date_taken"):
        lines.append(f"📷 Taken: {metadata['date_taken']}")

    gps = metadata.get("gps")
    if gps:
        lines.append(f"📍 GPS: {gps['latitude']:.6f}, {gps['longitude']:.6f}")
        if "altitude_m" in gps:
            lines.append(f"⛰️  Altitude: {gps['altitude_m']} m")
        if metadata.get("location"):
            lines.append(f"🏠 Address: {metadata['location']}")
        if metadata.get("map_url"):
            lines.append(f"🗺️  Map: {metadata['map_url']}")
    else:
        lines.append("📍 GPS: Not found")

    summary = metadata.get("summary") or {}
    if summary and not show_all:
        lines.append("")
        for label, value in summary.items():
            lines.append(f"   {label}: {value}")

    if show_all:
        exif = metadata.get("exif") or {}
        if exif:
            lines.append("")
            lines.append(f"📋 All EXIF Tags ({len(exif)}):")
            for tag in sorted(exif):
                lines.append(f"   {tag}: {exif[tag]}")
        else:
            lines.append("")
            lines.append("📋 No EXIF tags found in this file.")

    return "\n".join(lines)


def save_report(metadata, output_file, fmt: str = "json") -> Path:
    """Save metadata (a dict, or a list of dicts) to JSON or plain text."""
    fmt = (fmt or "json").lower().lstrip(".")
    path = Path(output_file)
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "json":
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(metadata, handle, indent=2, default=str, ensure_ascii=False)
    elif fmt in ("txt", "text"):
        records = metadata if isinstance(metadata, list) else [metadata]
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n\n".join(format_output(record, show_all=True) for record in records))
    else:
        raise ValueError(f"Unsupported format {fmt!r}. Use 'json' or 'txt'.")
    return path


def format_for_file(output_file) -> str:
    """Pick a report format from the output file's extension."""
    return "json" if str(output_file).lower().endswith(".json") else "txt"


def analyze_path(target, recursive: bool = False, geocode: bool = True):
    """Analyse a file or a directory, yielding ``(path, metadata, error)``.

    A file that cannot be parsed yields an error instead of aborting the batch.
    """
    from .utils import iter_images

    path = Path(target)
    candidates = [path] if path.is_file() else list(iter_images(path, recursive=recursive))
    for candidate in candidates:
        try:
            yield candidate, extract_metadata(candidate, geocode=geocode), None
        except Exception as exc:  # noqa: BLE001 - one bad file must not stop a batch
            yield candidate, None, exc
