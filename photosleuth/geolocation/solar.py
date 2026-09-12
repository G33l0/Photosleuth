"""Solar position and shadow geometry.

Implements the NOAA solar position algorithm, which is accurate to well under
a degree for any date between 1901 and 2099 - far finer than anything that can
be measured off a photograph.

The shadow techniques built on it are the ones open-source investigators use:
a vertical object and its shadow give the sun's elevation angle, and the sun's
elevation at a known instant is only possible from a specific circle of points
on the Earth's surface.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date as _date
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional, Tuple

EARTH_RADIUS_KM = 6371.0088


@dataclass(frozen=True)
class SunPosition:
    """Where the sun is, seen from one point at one instant."""

    elevation: float          # degrees above the horizon (refraction-corrected)
    azimuth: float            # degrees clockwise from true north
    declination: float        # degrees
    equation_of_time: float   # minutes
    hour_angle: float         # degrees
    subsolar_latitude: float  # degrees - the point with the sun overhead
    subsolar_longitude: float

    @property
    def is_up(self) -> bool:
        return self.elevation > 0.0

    @property
    def shadow_azimuth(self) -> float:
        """Compass direction a shadow points: opposite the sun."""
        return (self.azimuth + 180.0) % 360.0


# --------------------------------------------------------------------------
# NOAA solar position
# --------------------------------------------------------------------------

def julian_day(moment: datetime) -> float:
    """Julian day number for a timezone-aware (or assumed-UTC) datetime."""
    moment = _as_utc(moment)
    year, month = moment.year, moment.month
    day = (
        moment.day
        + (moment.hour + (moment.minute + (moment.second + moment.microsecond / 1e6) / 60.0) / 60.0)
        / 24.0
    )
    if month <= 2:
        year -= 1
        month += 12
    a = math.floor(year / 100.0)
    b = 2 - a + math.floor(a / 4.0)
    return (
        math.floor(365.25 * (year + 4716))
        + math.floor(30.6001 * (month + 1))
        + day + b - 1524.5
    )


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _refraction(elevation: float) -> float:
    """Atmospheric refraction in degrees, per the NOAA spreadsheet."""
    if elevation > 85.0:
        return 0.0
    tan_e = math.tan(math.radians(elevation))
    if elevation > 5.0:
        correction = 58.1 / tan_e - 0.07 / tan_e**3 + 0.000086 / tan_e**5
    elif elevation > -0.575:
        correction = 1735.0 + elevation * (
            -518.2 + elevation * (103.4 + elevation * (-12.79 + elevation * 0.711))
        )
    else:
        correction = -20.772 / tan_e
    return correction / 3600.0


def sun_position(latitude: float, longitude: float, moment: datetime) -> SunPosition:
    """Sun elevation and azimuth for a location and instant."""
    moment = _as_utc(moment)
    century = (julian_day(moment) - 2451545.0) / 36525.0

    geom_mean_long = (280.46646 + century * (36000.76983 + century * 0.0003032)) % 360.0
    geom_mean_anom = 357.52911 + century * (35999.05029 - 0.0001537 * century)
    eccentricity = 0.016708634 - century * (0.000042037 + 0.0000001267 * century)

    anom_rad = math.radians(geom_mean_anom)
    centre = (
        math.sin(anom_rad) * (1.914602 - century * (0.004817 + 0.000014 * century))
        + math.sin(2 * anom_rad) * (0.019993 - 0.000101 * century)
        + math.sin(3 * anom_rad) * 0.000289
    )
    true_long = geom_mean_long + centre
    apparent_long = true_long - 0.00569 - 0.00478 * math.sin(
        math.radians(125.04 - 1934.136 * century)
    )

    mean_obliquity = (
        23.0
        + (26.0 + ((21.448 - century * (46.815 + century * (0.00059 - century * 0.001813)))) / 60.0)
        / 60.0
    )
    obliquity = mean_obliquity + 0.00256 * math.cos(math.radians(125.04 - 1934.136 * century))

    declination = math.degrees(
        math.asin(
            math.sin(math.radians(obliquity)) * math.sin(math.radians(apparent_long))
        )
    )

    var_y = math.tan(math.radians(obliquity / 2.0)) ** 2
    equation_of_time = 4.0 * math.degrees(
        var_y * math.sin(2 * math.radians(geom_mean_long))
        - 2 * eccentricity * math.sin(anom_rad)
        + 4 * eccentricity * var_y * math.sin(anom_rad) * math.cos(2 * math.radians(geom_mean_long))
        - 0.5 * var_y * var_y * math.sin(4 * math.radians(geom_mean_long))
        - 1.25 * eccentricity * eccentricity * math.sin(2 * anom_rad)
    )

    minutes_utc = (
        moment.hour * 60.0 + moment.minute + moment.second / 60.0 + moment.microsecond / 6e7
    )
    true_solar_time = (minutes_utc + equation_of_time + 4.0 * longitude) % 1440.0
    hour_angle = true_solar_time / 4.0 - 180.0
    if hour_angle < -180.0:
        hour_angle += 360.0

    lat_rad = math.radians(latitude)
    dec_rad = math.radians(declination)
    ha_rad = math.radians(hour_angle)

    cos_zenith = (
        math.sin(lat_rad) * math.sin(dec_rad)
        + math.cos(lat_rad) * math.cos(dec_rad) * math.cos(ha_rad)
    )
    cos_zenith = max(-1.0, min(1.0, cos_zenith))
    zenith = math.degrees(math.acos(cos_zenith))
    elevation = 90.0 - zenith
    elevation += _refraction(elevation)

    # Azimuth, measured clockwise from true north.
    sin_zenith = math.sin(math.radians(zenith))
    if abs(sin_zenith) < 1e-9:
        azimuth = 0.0
    else:
        cos_azimuth = (
            math.sin(lat_rad) * cos_zenith - math.sin(dec_rad)
        ) / (math.cos(lat_rad) * sin_zenith) if abs(math.cos(lat_rad)) > 1e-9 else 0.0
        cos_azimuth = max(-1.0, min(1.0, cos_azimuth))
        azimuth = math.degrees(math.acos(cos_azimuth))
        azimuth = (180.0 + azimuth) % 360.0 if hour_angle > 0 else (540.0 - azimuth) % 360.0

    # The subsolar point: sun exactly overhead there at this instant.
    subsolar_longitude = -(true_solar_time - 4.0 * longitude - 720.0) / 4.0
    subsolar_longitude = ((subsolar_longitude + 180.0) % 360.0) - 180.0

    return SunPosition(
        elevation=elevation,
        azimuth=azimuth,
        declination=declination,
        equation_of_time=equation_of_time,
        hour_angle=hour_angle,
        subsolar_latitude=declination,
        subsolar_longitude=subsolar_longitude,
    )


def subsolar_point(moment: datetime) -> Tuple[float, float]:
    """The (latitude, longitude) with the sun directly overhead."""
    position = sun_position(0.0, 0.0, moment)
    return position.subsolar_latitude, position.subsolar_longitude


def solar_noon(latitude: float, longitude: float, day: _date) -> datetime:
    """UTC instant of local solar noon (when shadows are shortest)."""
    probe = datetime(day.year, day.month, day.day, 12, 0, tzinfo=timezone.utc)
    equation_of_time = sun_position(latitude, longitude, probe).equation_of_time
    minutes = 720.0 - 4.0 * longitude - equation_of_time
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc) + timedelta(minutes=minutes)


def sun_times(latitude: float, longitude: float, day: _date,
              elevation: float = -0.833) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Sunrise and sunset (UTC). Returns ``(None, None)`` in polar day/night."""
    noon = solar_noon(latitude, longitude, day)
    declination = sun_position(latitude, longitude, noon).declination

    lat_rad = math.radians(latitude)
    dec_rad = math.radians(declination)
    try:
        cos_ha = (
            math.cos(math.radians(90.0 - elevation))
            - math.sin(lat_rad) * math.sin(dec_rad)
        ) / (math.cos(lat_rad) * math.cos(dec_rad))
    except ZeroDivisionError:
        return None, None
    if not -1.0 <= cos_ha <= 1.0:
        return None, None

    hour_angle = math.degrees(math.acos(cos_ha))
    offset = timedelta(minutes=4.0 * hour_angle)
    return noon - offset, noon + offset


# --------------------------------------------------------------------------
# Shadow geometry
# --------------------------------------------------------------------------

def elevation_from_shadow(object_height: float, shadow_length: float) -> float:
    """Sun elevation from a vertical object and the shadow it casts.

    Units cancel, so pixels work as well as metres provided both are measured
    in the same plane.
    """
    if object_height <= 0:
        raise ValueError("Object height must be positive.")
    if shadow_length < 0:
        raise ValueError("Shadow length cannot be negative.")
    if shadow_length == 0:
        return 90.0
    return math.degrees(math.atan2(object_height, shadow_length))


def shadow_ratio_from_elevation(elevation: float) -> float:
    """Shadow length as a multiple of object height, for a sun elevation."""
    if not 0.0 < elevation < 90.0:
        raise ValueError("Elevation must be between 0 and 90 degrees.")
    return 1.0 / math.tan(math.radians(elevation))


def shadow_length_from_elevation(object_height: float, elevation: float) -> float:
    return object_height * shadow_ratio_from_elevation(elevation)


def angular_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle separation in degrees."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta = math.radians(lon2 - lon1)
    cos_d = (
        math.sin(phi1) * math.sin(phi2)
        + math.cos(phi1) * math.cos(phi2) * math.cos(delta)
    )
    return math.degrees(math.acos(max(-1.0, min(1.0, cos_d))))


def bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial great-circle bearing from point 1 to point 2, degrees from north."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta = math.radians(lon2 - lon1)
    x = math.sin(delta) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(delta)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def destination(lat: float, lon: float, bearing_deg: float, distance_km: float) -> Tuple[float, float]:
    """Point reached by travelling *distance_km* along *bearing_deg*."""
    angular = distance_km / EARTH_RADIUS_KM
    phi1, lambda1 = math.radians(lat), math.radians(lon)
    theta = math.radians(bearing_deg)
    phi2 = math.asin(
        math.sin(phi1) * math.cos(angular) + math.cos(phi1) * math.sin(angular) * math.cos(theta)
    )
    lambda2 = lambda1 + math.atan2(
        math.sin(theta) * math.sin(angular) * math.cos(phi1),
        math.cos(angular) - math.sin(phi1) * math.sin(phi2),
    )
    return math.degrees(phi2), ((math.degrees(lambda2) + 540.0) % 360.0) - 180.0


# --------------------------------------------------------------------------
# Discovery helpers
# --------------------------------------------------------------------------

def times_for_elevation(
    latitude: float,
    longitude: float,
    day: _date,
    target_elevation: float,
    step_minutes: int = 2,
) -> List[datetime]:
    """UTC instants on *day* when the sun sits at *target_elevation*.

    Typically returns two answers - one before solar noon and one after -
    which the direction of the shadow then distinguishes.
    """
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    samples = []
    steps = int(24 * 60 / step_minutes) + 1
    for index in range(steps):
        moment = start + timedelta(minutes=index * step_minutes)
        samples.append((moment, sun_position(latitude, longitude, moment).elevation))

    hits: List[datetime] = []
    for (t0, e0), (t1, e1) in zip(samples, samples[1:]):
        if (e0 - target_elevation) == 0.0:
            hits.append(t0)
        elif (e0 - target_elevation) * (e1 - target_elevation) < 0:
            # Linear interpolation is plenty: elevation is smooth at this scale.
            fraction = (target_elevation - e0) / (e1 - e0)
            hits.append(t0 + (t1 - t0) * fraction)
    return hits


def verify_claim(
    latitude: float,
    longitude: float,
    moment: datetime,
    measured_elevation: float,
    measured_shadow_azimuth: Optional[float] = None,
    tolerance: float = 3.0,
) -> dict:
    """Compare a measured shadow against a claimed place and time."""
    position = sun_position(latitude, longitude, moment)
    elevation_error = measured_elevation - position.elevation

    result = {
        "expected_elevation": round(position.elevation, 3),
        "measured_elevation": round(measured_elevation, 3),
        "elevation_error": round(elevation_error, 3),
        "expected_sun_azimuth": round(position.azimuth, 2),
        "expected_shadow_azimuth": round(position.shadow_azimuth, 2),
        "sun_is_up": position.is_up,
        "tolerance": tolerance,
        "consistent": abs(elevation_error) <= tolerance and position.is_up,
    }

    if measured_shadow_azimuth is not None:
        difference = ((measured_shadow_azimuth - position.shadow_azimuth + 180.0) % 360.0) - 180.0
        result["azimuth_error"] = round(difference, 2)
        result["consistent"] = result["consistent"] and abs(difference) <= tolerance * 2

    if not position.is_up:
        result["reason"] = "The sun was below the horizon, so there could be no shadow."
    elif not result["consistent"]:
        result["reason"] = (
            f"Shadow indicates a sun elevation of {measured_elevation:.1f}°, but at this "
            f"place and time the sun was {position.elevation:.1f}° above the horizon."
        )
    else:
        result["reason"] = "The shadow is consistent with this place and time."
    return result


def north_arrow(latitude: float, longitude: float, moment: datetime,
                shadow_azimuth_in_image: float) -> dict:
    """Work out which way is north in a photograph.

    Knowing where the sun was means the shadow's true compass bearing is known;
    comparing it with the shadow's direction as drawn on the image gives the
    rotation between image and map - which is what lets an analyst line the
    photograph up against satellite imagery.
    """
    position = sun_position(latitude, longitude, moment)
    if not position.is_up:
        raise ValueError("The sun was below the horizon at that place and time.")
    rotation = (position.shadow_azimuth - shadow_azimuth_in_image) % 360.0
    return {
        "true_shadow_azimuth": round(position.shadow_azimuth, 2),
        "image_shadow_azimuth": round(shadow_azimuth_in_image % 360.0, 2),
        "image_north_direction": round((0.0 - rotation) % 360.0, 2),
        "rotation_to_map": round(rotation, 2),
        "sun_elevation": round(position.elevation, 2),
    }


# --------------------------------------------------------------------------
# Vectorised helpers (used by the constraint grid)
# --------------------------------------------------------------------------

def solar_parameters(moment: datetime) -> Tuple[float, float, float]:
    """Return ``(declination, equation_of_time, minutes_utc)`` for an instant.

    Declination and the equation of time depend only on *when*, not *where*,
    so they are computed once and reused across an entire grid of locations.
    """
    position = sun_position(0.0, 0.0, moment)
    moment = _as_utc(moment)
    minutes_utc = (
        moment.hour * 60.0 + moment.minute + moment.second / 60.0 + moment.microsecond / 6e7
    )
    return position.declination, position.equation_of_time, minutes_utc


def elevation_grid(lat_grid, lon_grid, moment: datetime, refraction: bool = True):
    """Sun elevation (degrees) over arrays of latitudes and longitudes."""
    import numpy as np

    declination, equation_of_time, minutes_utc = solar_parameters(moment)

    true_solar_time = np.mod(minutes_utc + equation_of_time + 4.0 * lon_grid, 1440.0)
    hour_angle = np.radians(true_solar_time / 4.0 - 180.0)

    lat_rad = np.radians(lat_grid)
    dec_rad = math.radians(declination)

    cos_zenith = np.clip(
        np.sin(lat_rad) * math.sin(dec_rad)
        + np.cos(lat_rad) * math.cos(dec_rad) * np.cos(hour_angle),
        -1.0,
        1.0,
    )
    elevation = 90.0 - np.degrees(np.arccos(cos_zenith))

    if refraction:
        elevation = elevation + _refraction_grid(elevation)
    return elevation


def _refraction_grid(elevation):
    """Vectorised twin of :func:`_refraction`, branch for branch.

    The scalar and grid paths must agree exactly, or a constraint would score a
    point differently depending on which one evaluated it.
    """
    import numpy as np

    # tan() explodes at the horizon, so evaluate it on a clamped copy and let
    # np.select discard the branches that are not chosen.
    safe = np.where(np.abs(elevation) < 0.02, 0.02, elevation)
    with np.errstate(divide="ignore", invalid="ignore"):
        tan_e = np.tan(np.radians(safe))
        high = 58.1 / tan_e - 0.07 / tan_e**3 + 0.000086 / tan_e**5
        low = -20.772 / tan_e
    middle = 1735.0 + elevation * (
        -518.2 + elevation * (103.4 + elevation * (-12.79 + elevation * 0.711))
    )

    arcseconds = np.select(
        [elevation > 85.0, elevation > 5.0, elevation > -0.575],
        [np.zeros_like(elevation), high, middle],
        default=low,
    )
    return np.nan_to_num(arcseconds, nan=0.0, posinf=0.0, neginf=0.0) / 3600.0


def azimuth_grid(lat_grid, lon_grid, moment: datetime):
    """Sun azimuth (degrees clockwise from north) over arrays of positions."""
    import numpy as np

    declination, equation_of_time, minutes_utc = solar_parameters(moment)

    true_solar_time = np.mod(minutes_utc + equation_of_time + 4.0 * lon_grid, 1440.0)
    hour_angle_deg = true_solar_time / 4.0 - 180.0
    hour_angle = np.radians(hour_angle_deg)

    lat_rad = np.radians(lat_grid)
    dec_rad = math.radians(declination)

    cos_zenith = np.clip(
        np.sin(lat_rad) * math.sin(dec_rad)
        + np.cos(lat_rad) * math.cos(dec_rad) * np.cos(hour_angle),
        -1.0,
        1.0,
    )
    zenith = np.arccos(cos_zenith)
    sin_zenith = np.sin(zenith)

    with np.errstate(divide="ignore", invalid="ignore"):
        cos_azimuth = np.clip(
            (np.sin(lat_rad) * cos_zenith - math.sin(dec_rad))
            / (np.cos(lat_rad) * sin_zenith),
            -1.0,
            1.0,
        )
    azimuth = np.degrees(np.arccos(cos_azimuth))
    azimuth = np.where(hour_angle_deg > 0, (180.0 + azimuth) % 360.0, (540.0 - azimuth) % 360.0)
    return np.nan_to_num(azimuth, nan=0.0)


def latitudes_for_elevation(
    day: _date,
    local_clock_hour: float,
    target_elevation: float,
    step: float = 0.25,
) -> List[float]:
    """Latitudes where the sun reaches *target_elevation* at a local clock time.

    Assumes the camera's clock ran roughly on local solar time. Under that
    assumption longitude cancels out of the hour-angle calculation, so the
    measurement constrains latitude alone - which is exactly why a shadow
    gives you a band of latitudes rather than a point.
    """
    import numpy as np

    noon = datetime(day.year, day.month, day.day, 12, 0, tzinfo=timezone.utc)
    declination, equation_of_time, _ = solar_parameters(noon)

    true_solar_time = (local_clock_hour * 60.0 + equation_of_time) % 1440.0
    hour_angle = math.radians(true_solar_time / 4.0 - 180.0)

    latitudes = np.arange(-90.0, 90.0 + step, step)
    lat_rad = np.radians(latitudes)
    dec_rad = math.radians(declination)
    cos_zenith = np.clip(
        np.sin(lat_rad) * math.sin(dec_rad)
        + np.cos(lat_rad) * math.cos(dec_rad) * math.cos(hour_angle),
        -1.0,
        1.0,
    )
    elevations = 90.0 - np.degrees(np.arccos(cos_zenith))

    hits: List[float] = []
    for index in range(len(latitudes) - 1):
        low, high = elevations[index] - target_elevation, elevations[index + 1] - target_elevation
        if low == 0.0:
            hits.append(float(latitudes[index]))
        elif low * high < 0:
            fraction = low / (low - high)
            hits.append(float(latitudes[index] + fraction * step))
    return hits
