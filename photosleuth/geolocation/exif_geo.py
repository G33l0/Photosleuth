"""Geolocation checks that need nothing but the file's own metadata.

These are the cheapest wins available: they run offline, in milliseconds, and
catch spoofed coordinates, wrong clocks and over-trusted fixes before any
expensive technique is attempted.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from .constraints import CirclePrior, Constraint, LongitudeBand, ViewCone

# Typical horizontal accuracy by how the fix was obtained, in metres.
FIX_ACCURACY_M = {
    "gps": 10.0,
    "dgps": 3.0,
    "rtk": 0.5,
    "wlan": 120.0,
    "wifi": 120.0,
    "cellid": 2500.0,
    "cell": 2500.0,
    "manual": 0.0,       # user-entered: no measurement error, but no evidence either
    "network": 500.0,
}

# User-equivalent range error: DOP is multiplied by this to get metres.
UERE_M = 5.0


# --------------------------------------------------------------------------
# EXIF parsing helpers
# --------------------------------------------------------------------------

def _tag(metadata: Dict[str, Any], name: str) -> Optional[str]:
    value = (metadata.get("exif") or {}).get(name)
    return None if value is None else str(value).strip()


def _decode_byte_list(text: str) -> str:
    """Decode the '[65, 83, 67, ...]' form exifread uses for byte-string tags.

    GPSProcessingMethod is an EXIF ``UNDEFINED`` field carrying an encoding
    prefix, so it surfaces as a list of byte values rather than text.
    """
    if not text or not text.startswith("["):
        return text or ""
    try:
        values = [int(part.strip()) for part in text.strip("[]").split(",") if part.strip()]
    except ValueError:
        return text
    return bytes(v & 0xFF for v in values).decode("ascii", errors="ignore")


def _numbers(text: str) -> List[float]:
    values = []
    for token in re.findall(r"-?\d+(?:/\d+)?(?:\.\d+)?", text or ""):
        try:
            if "/" in token:
                numerator, denominator = token.split("/", 1)
                values.append(float(numerator) / float(denominator))
            else:
                values.append(float(token))
        except (ValueError, ZeroDivisionError):
            continue
    return values


def gps_datetime(metadata: Dict[str, Any]) -> Optional[datetime]:
    """The UTC instant recorded by the GPS receiver, if present."""
    # exifread labels this tag "GPS GPSDate"; the EXIF specification calls it
    # GPSDateStamp. Accept either so the check works whatever produced the file.
    stamp = _tag(metadata, "GPS GPSDate") or _tag(metadata, "GPS GPSDateStamp")
    clock = _tag(metadata, "GPS GPSTimeStamp")
    if not stamp or not clock:
        return None

    date_parts = _numbers(stamp.replace(":", " "))
    time_parts = _numbers(clock)
    if len(date_parts) < 3 or len(time_parts) < 2:
        return None
    try:
        return datetime(
            int(date_parts[0]), int(date_parts[1]), int(date_parts[2]),
            int(time_parts[0]), int(time_parts[1]),
            int(time_parts[2]) if len(time_parts) > 2 else 0,
            tzinfo=timezone.utc,
        )
    except ValueError:
        return None


def local_datetime(metadata: Dict[str, Any]) -> Optional[datetime]:
    """The camera's own (local, naive) capture time."""
    for name in ("EXIF DateTimeOriginal", "EXIF DateTimeDigitized", "Image DateTime"):
        text = _tag(metadata, name)
        if not text:
            continue
        for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
    return None


def recorded_offset_hours(metadata: Dict[str, Any]) -> Optional[float]:
    """The UTC offset from EXIF 2.31's OffsetTime tags, in hours."""
    for name in ("EXIF OffsetTimeOriginal", "EXIF OffsetTime", "EXIF OffsetTimeDigitized"):
        text = _tag(metadata, name)
        if not text:
            continue
        match = re.match(r"([+-])(\d{2}):?(\d{2})", text)
        if match:
            sign = 1 if match.group(1) == "+" else -1
            return sign * (int(match.group(2)) + int(match.group(3)) / 60.0)
    return None


def true_offset_hours(latitude: float, longitude: float, moment: datetime) -> Optional[float]:
    """The UTC offset actually in force at a place on a date."""
    from .timezones import offset_at

    offset, _lookup = offset_at(latitude, longitude, moment)
    return offset


def timezone_name(latitude: float, longitude: float) -> Optional[str]:
    from .timezones import zone_at

    return zone_at(latitude, longitude).name


# --------------------------------------------------------------------------
# Check 1 and 2: timezone consistency, and longitude from the UTC offset
# --------------------------------------------------------------------------

# A mismatch this large or smaller has innocent explanations; beyond it, the
# file is claiming something hard to account for. See check_timezone().
QUESTIONABLE_HOURS = 3.0


@dataclass
class TimezoneCheck:
    verdict: str = "unknown"   # consistent | questionable | inconsistent | unknown
    implied_offset: Optional[float] = None
    recorded_offset: Optional[float] = None
    true_offset: Optional[float] = None
    timezone: Optional[str] = None
    near_border: bool = False
    utc_time: Optional[datetime] = None
    local_time: Optional[datetime] = None
    message: str = ""
    constraints: List[Constraint] = field(default_factory=list)

    @property
    def is_inconsistent(self) -> bool:
        return self.verdict == "inconsistent"

    @property
    def needs_attention(self) -> bool:
        return self.verdict in ("questionable", "inconsistent")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "implied_offset": self.implied_offset,
            "recorded_offset": self.recorded_offset,
            "true_offset": self.true_offset,
            "timezone": self.timezone,
            "near_border": self.near_border,
            "utc_time": self.utc_time.isoformat() if self.utc_time else None,
            "local_time": self.local_time.isoformat() if self.local_time else None,
            "message": self.message,
        }


def check_timezone(metadata: Dict[str, Any], tolerance_hours: float = 0.5) -> TimezoneCheck:
    """Cross-check the camera clock, the GPS clock and the coordinates.

    The verdict is graded rather than binary, because a mismatch of an hour or
    two has innocent explanations and calling it tampering would be wrong:

    * a camera clock never changed after crossing a border;
    * daylight saving applied a day early or late;
    * places whose official time is deliberately far from their sun. Xinjiang
      is the clearest case - the IANA zone ``Asia/Urumqi`` is UTC+6, but people
      there keep Beijing time at UTC+8, so an honest photo looks two hours out.

    Only a discrepancy beyond :data:`QUESTIONABLE_HOURS` is reported as
    inconsistent.
    """
    result = TimezoneCheck()
    result.utc_time = gps_datetime(metadata)
    result.local_time = local_datetime(metadata)
    result.recorded_offset = recorded_offset_hours(metadata)

    gps = metadata.get("gps") or {}
    latitude, longitude = gps.get("latitude"), gps.get("longitude")

    # The offset the file claims, either stated outright or implied by the two
    # clocks disagreeing.
    if result.recorded_offset is not None:
        result.implied_offset = result.recorded_offset
    elif result.utc_time and result.local_time:
        difference = (result.local_time - result.utc_time.replace(tzinfo=None)).total_seconds() / 3600.0
        # Cameras record whole- or half-hour offsets; round to the nearest quarter.
        result.implied_offset = round(difference * 4.0) / 4.0

    if result.implied_offset is None:
        result.message = (
            "No UTC offset could be established: the file lacks either a GPS "
            "timestamp or an OffsetTime tag."
        )
        return result

    # Feature 2: the offset alone narrows longitude, even with no coordinates.
    centre = result.implied_offset * 15.0
    result.constraints.append(
        LongitudeBand(
            source="exif",
            label=f"UTC offset {result.implied_offset:+g}h",
            detail=(
                f"A {result.implied_offset:+g} h offset centres on the "
                f"{abs(centre):.0f}°{'E' if centre >= 0 else 'W'} meridian. Political "
                "time zones stretch well past their meridian, so this is a wide band."
            ),
            min_lon=centre - 22.0,
            max_lon=centre + 22.0,
            softness=18.0,
            weight=0.6,
        )
    )

    if latitude is None or longitude is None:
        result.verdict = "unknown"
        result.message = (
            f"The file implies a UTC offset of {result.implied_offset:+g} h, but has no "
            "coordinates to check it against."
        )
        return result

    reference = result.local_time or (result.utc_time.replace(tzinfo=None) if result.utc_time else None)
    if reference is None:
        result.verdict = "unknown"
        result.message = "No capture time to check against."
        return result

    from .timezones import offset_at

    result.true_offset, zone = offset_at(latitude, longitude, reference)
    result.timezone = zone.name
    result.near_border = zone.near_border

    if result.true_offset is None:
        result.verdict = "unknown"
        result.message = (
            "No time zone applies at these coordinates (open sea), or the zone "
            "database could not be read, so the offset could not be verified."
        )
        return result

    difference = abs(result.implied_offset - result.true_offset)
    # Offsets wrap: +12 and -12 are the same meridian.
    difference = min(difference, 24.0 - difference)

    if difference <= tolerance_hours:
        result.verdict = "consistent"
        result.message = (
            f"The camera clock ({result.implied_offset:+g} h) matches "
            f"{result.timezone} ({result.true_offset:+g} h) at these coordinates."
        )
    elif difference <= QUESTIONABLE_HOURS:
        result.verdict = "questionable"
        result.message = (
            f"The file implies UTC{result.implied_offset:+g}, but {result.timezone} "
            f"was UTC{result.true_offset:+g} on that date - {difference:g} hours apart. "
            "A clock left on another zone after travelling, a daylight-saving slip, or "
            "a region that keeps time far from its sun would all look like this, so "
            "this is worth checking rather than treating as proof of anything."
        )
    elif result.near_border:
        # The shipped raster resolves to about 28 km, so a point this close to a
        # boundary may simply have been placed in the neighbouring zone. That is
        # a limit of the lookup, not evidence about the photograph.
        result.verdict = "questionable"
        result.message = (
            f"The file implies UTC{result.implied_offset:+g} while the lookup puts these "
            f"coordinates in {result.timezone} (UTC{result.true_offset:+g}). They sit close "
            "to a time-zone boundary, so the zone itself is uncertain here and this "
            "difference may mean nothing."
        )
    else:
        result.verdict = "inconsistent"
        result.message = (
            f"The file implies UTC{result.implied_offset:+g}, but {result.timezone} "
            f"was UTC{result.true_offset:+g} on that date - a {difference:g} hour "
            "discrepancy, too large to explain by a mis-set clock. Either the "
            "coordinates are wrong or the metadata was altered."
        )
    return result


# --------------------------------------------------------------------------
# Check 5: how much the GPS fix can be trusted
# --------------------------------------------------------------------------

@dataclass
class GpsQuality:
    has_gps: bool = False
    method: Optional[str] = None
    dop: Optional[float] = None
    satellites: Optional[int] = None
    measure_mode: Optional[str] = None
    accuracy_m: Optional[float] = None
    confidence: str = "unknown"
    message: str = ""
    constraints: List[Constraint] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_gps": self.has_gps,
            "method": self.method,
            "dop": self.dop,
            "satellites": self.satellites,
            "measure_mode": self.measure_mode,
            "accuracy_m": round(self.accuracy_m, 1) if self.accuracy_m else None,
            "confidence": self.confidence,
            "message": self.message,
        }


def check_gps_quality(metadata: Dict[str, Any]) -> GpsQuality:
    """Turn a bare coordinate into a coordinate plus an honest error radius."""
    result = GpsQuality()
    gps = metadata.get("gps") or {}
    latitude, longitude = gps.get("latitude"), gps.get("longitude")
    result.has_gps = latitude is not None and longitude is not None

    raw_method = _decode_byte_list(_tag(metadata, "GPS GPSProcessingMethod") or "")
    # Strip the encoding prefix ("ASCII\0\0\0") that precedes the value.
    cleaned = re.sub(r"[^A-Za-z]", "", raw_method).lower()
    cleaned = cleaned[5:] if cleaned.startswith("ascii") else cleaned
    for key in FIX_ACCURACY_M:
        if key in cleaned:
            result.method = key
            break

    dop_text = _tag(metadata, "GPS GPSDOP")
    if dop_text:
        values = _numbers(dop_text)
        if values:
            result.dop = round(values[0], 2)

    satellites_text = _tag(metadata, "GPS GPSSatellites")
    if satellites_text:
        digits = re.findall(r"\d+", satellites_text)
        if digits:
            # Some cameras list each satellite ID; the count is what matters.
            result.satellites = len(digits) if len(digits) > 1 else int(digits[0])

    mode = _tag(metadata, "GPS GPSMeasureMode")
    if mode:
        result.measure_mode = {"2": "2D fix", "3": "3D fix"}.get(mode.strip(), mode.strip())

    if not result.has_gps:
        result.message = "No GPS coordinates in this file."
        return result

    if result.dop is not None:
        result.accuracy_m = max(result.dop * UERE_M, 3.0)
    elif result.method and result.method in FIX_ACCURACY_M:
        result.accuracy_m = FIX_ACCURACY_M[result.method]
    else:
        result.accuracy_m = 25.0

    if result.method == "manual":
        result.confidence = "none"
        result.message = (
            "These coordinates were entered by hand, not measured. They carry no "
            "more weight than the word of whoever typed them."
        )
        result.accuracy_m = 0.0
    elif result.method in ("cellid", "cell"):
        result.confidence = "low"
        result.message = (
            "The position came from cell-tower triangulation, which is routinely "
            "off by a kilometre or more."
        )
    elif result.dop is not None and result.dop <= 2.0:
        result.confidence = "high"
        result.message = (
            f"Good fix: DOP {result.dop}"
            + (f" across {result.satellites} satellites" if result.satellites else "")
            + f", so roughly ±{result.accuracy_m:.0f} m."
        )
    elif result.dop is not None and result.dop > 5.0:
        result.confidence = "low"
        result.message = (
            f"Weak geometry: DOP {result.dop} implies an error of about "
            f"±{result.accuracy_m:.0f} m."
        )
    else:
        result.confidence = "medium"
        result.message = (
            f"Assuming about ±{result.accuracy_m:.0f} m; the file records no "
            "dilution-of-precision value."
        )

    if result.measure_mode == "2D fix":
        result.message += " Recorded as a 2D fix, so any altitude is unreliable."

    radius_km = max(result.accuracy_m, 25.0) / 1000.0
    result.constraints.append(
        CirclePrior(
            source="exif",
            label="GPS fix",
            detail=result.message,
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
            softness_km=max(radius_km, 0.05),
            weight=0.4 if result.confidence in ("none", "low") else 1.0,
        )
    )
    return result


# --------------------------------------------------------------------------
# Check 4: what the camera was pointing at
# --------------------------------------------------------------------------

@dataclass
class Direction:
    has_direction: bool = False
    bearing: Optional[float] = None
    reference: str = ""
    field_of_view: Optional[float] = None
    message: str = ""
    constraints: List[Constraint] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_direction": self.has_direction,
            "bearing": round(self.bearing, 2) if self.bearing is not None else None,
            "reference": self.reference,
            "field_of_view": round(self.field_of_view, 2) if self.field_of_view else None,
            "message": self.message,
        }


def check_direction(metadata: Dict[str, Any], range_km: float = 2.0) -> Direction:
    """Read ``GPSImgDirection`` and turn it into a cone of view."""
    result = Direction()
    gps = metadata.get("gps") or {}
    latitude, longitude = gps.get("latitude"), gps.get("longitude")

    text = _tag(metadata, "GPS GPSImgDirection")
    values = _numbers(text) if text else []
    if not values:
        result.message = (
            "No GPSImgDirection tag, so the direction the camera faced is unknown."
        )
        return result

    result.has_direction = True
    result.bearing = values[0] % 360.0
    reference = (_tag(metadata, "GPS GPSImgDirectionRef") or "T").strip().upper()[:1]
    result.reference = "magnetic" if reference == "M" else "true"

    from . import photogrammetry

    lens = photogrammetry.lens_from_metadata(metadata)
    result.field_of_view = lens.horizontal_fov if lens else None
    half_angle = (result.field_of_view / 2.0) if result.field_of_view else 30.0

    note = ""
    if result.reference == "magnetic":
        note = (
            " The bearing is magnetic, so it is off true north by the local magnetic "
            "declination - up to about 20° in places."
        )

    result.message = (
        f"The camera faced {result.bearing:.0f}° ({result.reference} north)"
        + (f", with a {result.field_of_view:.0f}° field of view." if result.field_of_view
           else ", field of view unknown.")
        + note
    )

    if latitude is not None and longitude is not None:
        result.constraints.append(
            ViewCone(
                source="exif",
                label=f"View cone {result.bearing:.0f}°",
                detail=result.message,
                latitude=latitude,
                longitude=longitude,
                bearing=result.bearing,
                half_angle=half_angle + (10.0 if result.reference == "magnetic" else 0.0),
                max_km=range_km,
                weight=0.5,
            )
        )
    return result


# --------------------------------------------------------------------------
# Everything at once
# --------------------------------------------------------------------------

def analyze(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Run every metadata-only check and collect the constraints they produce."""
    timezone_result = check_timezone(metadata)
    quality = check_gps_quality(metadata)
    direction = check_direction(metadata)

    from . import photogrammetry

    lens = photogrammetry.lens_from_metadata(metadata)

    constraints: List[Constraint] = []
    for part in (timezone_result, quality, direction):
        constraints.extend(part.constraints)

    warnings: List[str] = []
    if timezone_result.needs_attention:
        warnings.append(timezone_result.message)
    if quality.confidence in ("none", "low") and quality.has_gps:
        warnings.append(quality.message)

    return {
        "file": metadata.get("file", ""),
        "timezone": timezone_result.to_dict(),
        "gps_quality": quality.to_dict(),
        "direction": direction.to_dict(),
        "lens": lens.to_dict() if lens else None,
        "warnings": warnings,
        "constraints": constraints,
    }
