"""Shadow analysis: from a line drawn on a photograph to a constraint on the map.

A vertical object and the shadow it casts give the sun's elevation angle, and
the sun is only that high from a specific set of places at a given instant.
This module turns that measurement into the three things an investigator wants:
a verdict on a claimed location, the time of day, and a constraint for the board.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date as _date
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from . import solar
from .constraints import (
    Constraint,
    ShadowLatitudeConstraint,
    SolarAzimuthConstraint,
    SolarElevationConstraint,
)


@dataclass
class ShadowObservation:
    """One object-and-shadow measurement taken off an image.

    Lengths may be in pixels or metres - only their ratio matters - but both
    must be measured in the same plane, which is why the ground should be flat
    and the object vertical for the result to mean anything.
    """

    object_length: float
    shadow_length: float
    shadow_azimuth_image: Optional[float] = None
    note: str = ""

    @property
    def elevation(self) -> float:
        return solar.elevation_from_shadow(self.object_length, self.shadow_length)

    @property
    def ratio(self) -> float:
        return self.shadow_length / self.object_length if self.object_length else float("inf")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "object_length": round(self.object_length, 3),
            "shadow_length": round(self.shadow_length, 3),
            "ratio": round(self.ratio, 4),
            "elevation": round(self.elevation, 3),
            "shadow_azimuth_image": self.shadow_azimuth_image,
            "note": self.note,
        }


def elevation_uncertainty(observation: ShadowObservation, pixel_error: float = 3.0) -> float:
    """How far the elevation could be out, given imprecise clicking.

    Shadow measurement error is not symmetric: a low sun casts a long shadow
    that is easy to measure, while a high sun casts a short one where a few
    pixels matter enormously. This propagates that through.
    """
    height = max(observation.object_length, 1e-6)
    shadow = max(observation.shadow_length, 1e-6)

    best = observation.elevation
    worst = 0.0
    for delta_h in (-pixel_error, pixel_error):
        for delta_s in (-pixel_error, pixel_error):
            trial_h = max(height + delta_h, 1e-6)
            trial_s = max(shadow + delta_s, 1e-6)
            worst = max(worst, abs(math.degrees(math.atan2(trial_h, trial_s)) - best))
    return round(worst, 3)


# --------------------------------------------------------------------------
# The three questions
# --------------------------------------------------------------------------

def verify(
    observation: ShadowObservation,
    latitude: float,
    longitude: float,
    moment: datetime,
    tolerance: Optional[float] = None,
) -> Dict[str, Any]:
    """Feature 7 - does the shadow match a claimed place and time?"""
    if tolerance is None:
        tolerance = max(2.0, elevation_uncertainty(observation) * 2.0)
    result = solar.verify_claim(
        latitude, longitude, moment,
        measured_elevation=observation.elevation,
        measured_shadow_azimuth=None,
        tolerance=tolerance,
    )
    result["measured_ratio"] = round(observation.ratio, 4)
    result["expected_ratio"] = (
        round(solar.shadow_ratio_from_elevation(result["expected_elevation"]), 4)
        if 0 < result["expected_elevation"] < 90 else None
    )
    return result


def time_of_day(
    observation: ShadowObservation,
    latitude: float,
    longitude: float,
    day: _date,
) -> Dict[str, Any]:
    """Feature 8 - when was this taken, given where and what date?"""
    elevation = observation.elevation
    hits = solar.times_for_elevation(latitude, longitude, day, elevation)
    noon = solar.solar_noon(latitude, longitude, day)

    entries = []
    for moment in hits:
        position = solar.sun_position(latitude, longitude, moment)
        entries.append({
            "utc": moment,
            "is_morning": moment < noon,
            "sun_azimuth": round(position.azimuth, 2),
            "shadow_azimuth": round(position.shadow_azimuth, 2),
        })

    return {
        "elevation": round(elevation, 3),
        "solar_noon_utc": noon,
        "matches": entries,
        "message": (
            "The sun never reaches that height at this place on this date."
            if not entries else
            f"The sun was {elevation:.1f}° up at "
            + " and ".join(f"{e['utc']:%H:%M} UTC" for e in entries)
            + (". Which one it was is settled by the direction the shadow falls."
               if len(entries) > 1 else ".")
        ),
    }


def north_from_shadow(
    observation: ShadowObservation,
    latitude: float,
    longitude: float,
    moment: datetime,
) -> Dict[str, Any]:
    """Feature 10 - which way is north in the photograph?"""
    if observation.shadow_azimuth_image is None:
        raise ValueError(
            "Measure the shadow's direction in the image before asking where north is."
        )
    return solar.north_arrow(latitude, longitude, moment, observation.shadow_azimuth_image)


# --------------------------------------------------------------------------
# Constraints for the board
# --------------------------------------------------------------------------

def constraints(
    observation: ShadowObservation,
    moment: Optional[datetime] = None,
    day: Optional[_date] = None,
    local_solar_hour: Optional[float] = None,
    sun_azimuth: Optional[float] = None,
    tolerance: Optional[float] = None,
) -> List[Constraint]:
    """Turn a shadow measurement into constraints the Evidence Board can fuse.

    Pass *moment* when the UTC instant is known: the result is a circle of equal
    altitude, which is exact. Fall back to *day* plus *local_solar_hour* when it
    is not - that yields a latitude band only, because longitude cancels out.
    """
    elevation = observation.elevation
    if tolerance is None:
        tolerance = max(1.5, elevation_uncertainty(observation) * 2.0)

    built: List[Constraint] = []

    if moment is not None:
        built.append(
            SolarElevationConstraint(
                source="shadow",
                label=f"Sun {elevation:.1f}° up",
                detail=(
                    f"A shadow {observation.ratio:.2f}× the object's height puts the sun "
                    f"{elevation:.1f}° above the horizon at {moment:%Y-%m-%d %H:%M} UTC. "
                    "Every point that saw it that high lies on one circle."
                ),
                moment=moment,
                elevation=elevation,
                tolerance=tolerance,
            )
        )
        if sun_azimuth is not None:
            built.append(
                SolarAzimuthConstraint(
                    source="shadow",
                    label=f"Sun bearing {sun_azimuth:.0f}°",
                    detail=(
                        "The compass direction of the sun, which cuts the circle of "
                        "equal altitude down to a point."
                    ),
                    moment=moment,
                    azimuth=sun_azimuth,
                    tolerance=max(tolerance * 2.0, 3.0),
                )
            )
        return built

    if day is not None and local_solar_hour is not None:
        built.append(
            ShadowLatitudeConstraint(
                source="shadow",
                label=f"Sun {elevation:.1f}° at {local_solar_hour:.2f} solar",
                detail=(
                    f"With only a local solar time, the measurement fixes latitude and "
                    f"says nothing about longitude. Expect two bands, one per hemisphere."
                ),
                day=day,
                local_solar_hour=local_solar_hour,
                elevation=elevation,
                tolerance=tolerance,
            )
        )
    return built


def image_azimuth(start: Tuple[float, float], end: Tuple[float, float]) -> float:
    """Direction of a drawn line in image space, degrees clockwise from up.

    Image y grows downwards, so 'up' in the picture is negative y; this returns
    a bearing in the same convention as a compass so the two can be compared.
    """
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    return (math.degrees(math.atan2(dx, -dy)) + 360.0) % 360.0


def observation_from_points(
    object_top: Tuple[float, float],
    object_base: Tuple[float, float],
    shadow_tip: Tuple[float, float],
) -> ShadowObservation:
    """Build an observation from three clicks: object top, object base, shadow tip."""
    height = math.dist(object_top, object_base)
    length = math.dist(object_base, shadow_tip)
    return ShadowObservation(
        object_length=height,
        shadow_length=length,
        shadow_azimuth_image=image_azimuth(object_base, shadow_tip),
    )
