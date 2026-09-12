"""Geolocation analysis: constraints, solar geometry and photogrammetry.

Every analyser in this package answers the same question in the same shape:
"given what I can measure, how plausible is each point on Earth?"  Each one
returns a :class:`~photosleuth.geolocation.constraints.Constraint`, and the
:class:`~photosleuth.geolocation.constraints.EvidenceBoard` multiplies them
together into a single probability surface.

No single technique locates a photograph. The intersection of several does.
"""

from . import exif_geo, photogrammetry, shadow, solar
from .constraints import (
    BearingConstraint,
    Candidate,
    CirclePrior,
    Constraint,
    EvidenceBoard,
    LatitudeBand,
    LongitudeBand,
    ProbabilityGrid,
    ResectionConstraint,
    ShadowLatitudeConstraint,
    SolarAzimuthConstraint,
    SolarElevationConstraint,
    ViewCone,
)

__all__ = [
    "BearingConstraint",
    "Candidate",
    "CirclePrior",
    "Constraint",
    "EvidenceBoard",
    "LatitudeBand",
    "LongitudeBand",
    "ProbabilityGrid",
    "ResectionConstraint",
    "ShadowLatitudeConstraint",
    "SolarAzimuthConstraint",
    "SolarElevationConstraint",
    "ViewCone",
    "exif_geo",
    "photogrammetry",
    "shadow",
    "solar",
]
