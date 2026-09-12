"""The Evidence Board: geographic constraints and how they combine.

No single technique locates a photograph. Each analyser instead answers
"how plausible is *this* point on Earth, given what I measured?", and the board
multiplies those answers together into one probability surface.

Every constraint scores in ``[0, 1]`` and never returns a hard zero: a single
mistaken measurement should pull a region down, not erase it, because in real
investigations one of the inputs is usually wrong.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import date as _date
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from . import solar

# Nothing is ever ruled out completely; this is the floor every constraint
# clamps to, so the fusion stays recoverable from one bad input.
SCORE_FLOOR = 0.02

WORLD_BOUNDS = (-90.0, 90.0, -180.0, 180.0)


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------

@dataclass
class Candidate:
    """A location the fused evidence considers plausible."""

    latitude: float
    longitude: float
    score: float
    rank: int = 0
    label: str = ""
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "latitude": round(self.latitude, 6),
            "longitude": round(self.longitude, 6),
            "score": round(self.score, 4),
            "rank": self.rank,
            "label": self.label,
            "notes": self.notes,
        }

    @property
    def map_url(self) -> str:
        return f"https://www.openstreetmap.org/?mlat={self.latitude:.6f}&mlon={self.longitude:.6f}#map=13"


@dataclass
class ProbabilityGrid:
    """A scored lat/lon raster, normalised so the best cell is 1.0."""

    values: np.ndarray
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float
    raw_peak: float = 1.0

    @property
    def has_signal(self) -> bool:
        """False when every cell sat on the floor - nothing was resolved.

        Normalising a floor-valued grid would otherwise turn pure noise into a
        confident-looking 1.0, which is the most dangerous failure mode here.
        """
        return self.raw_peak > SCORE_FLOOR * 1.5

    @property
    def rows(self) -> int:
        return int(self.values.shape[0])

    @property
    def cols(self) -> int:
        return int(self.values.shape[1])

    def latitude_of(self, row: float) -> float:
        if self.rows == 1:
            return self.lat_min
        return self.lat_min + (self.lat_max - self.lat_min) * row / (self.rows - 1)

    def longitude_of(self, col: float) -> float:
        if self.cols == 1:
            return self.lon_min
        return self.lon_min + (self.lon_max - self.lon_min) * col / (self.cols - 1)

    def peak(self) -> Candidate:
        row, col = np.unravel_index(int(np.argmax(self.values)), self.values.shape)
        return Candidate(
            latitude=self.latitude_of(row),
            longitude=self.longitude_of(col),
            score=float(self.values[row, col]),
            rank=1,
        )

    def top(self, count: int = 5, min_separation_deg: float = 4.0) -> List[Candidate]:
        """Best distinct local maxima, greedily separated on the ground."""
        flat = self.values.ravel()
        order = np.argsort(flat)[::-1]
        chosen: List[Candidate] = []

        for index in order[: max(4000, count * 400)]:
            if len(chosen) >= count:
                break
            row, col = divmod(int(index), self.cols)
            latitude = self.latitude_of(row)
            longitude = self.longitude_of(col)
            if any(
                solar.angular_distance(latitude, longitude, c.latitude, c.longitude)
                < min_separation_deg
                for c in chosen
            ):
                continue
            chosen.append(
                Candidate(latitude=latitude, longitude=longitude,
                          score=float(flat[index]), rank=len(chosen) + 1)
            )
        return chosen

    def normalised(self) -> "ProbabilityGrid":
        peak = float(np.max(self.values)) if self.values.size else 0.0
        values = self.values / peak if peak > 0 else self.values
        return ProbabilityGrid(
            values, self.lat_min, self.lat_max, self.lon_min, self.lon_max, raw_peak=peak
        )


# --------------------------------------------------------------------------
# Constraints
# --------------------------------------------------------------------------

@dataclass
class Constraint:
    """Base class. Subclasses implement :meth:`score`."""

    source: str = "constraint"
    label: str = ""
    detail: str = ""
    weight: float = 1.0
    enabled: bool = True
    identifier: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    def score(self, lat_grid: np.ndarray, lon_grid: np.ndarray) -> np.ndarray:
        raise NotImplementedError

    def score_clamped(self, lat_grid: np.ndarray, lon_grid: np.ndarray) -> np.ndarray:
        return np.clip(self.score(lat_grid, lon_grid), SCORE_FLOOR, 1.0)

    def score_at(self, latitude: float, longitude: float) -> float:
        values = self.score_clamped(
            np.array([[float(latitude)]]), np.array([[float(longitude)]])
        )
        return float(values[0, 0])

    def search_bounds(self) -> Optional[Tuple[float, float, float, float]]:
        """Region this constraint is informative in, if it is a local one.

        A global search grid cannot resolve a constraint whose answer is a few
        hundred metres across, so local constraints declare a window for the
        board to search inside instead.  ``None`` means "no opinion".
        """
        return None

    def describe(self) -> str:
        return self.detail or self.label or self.source

    # Fields scaled when a constraint is broadened for a coarse search pass.
    _tolerance_fields = ("tolerance", "softness", "softness_km", "half_angle")

    def broadened(self, factor: float) -> "Constraint":
        """A copy with its tolerances widened by *factor*.

        A constraint whose solution band is thinner than one grid cell is
        invisible to that grid - every sample misses it. The search therefore
        starts with deliberately blurred constraints and sharpens them as it
        zooms in, so the band is always at least a cell wide.
        """
        import copy as _copy

        if factor <= 1.0:
            return self
        clone = _copy.copy(self)
        for name in self._tolerance_fields:
            value = getattr(clone, name, None)
            if isinstance(value, (int, float)) and value > 0:
                setattr(clone, name, float(value) * factor)
        return clone

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.identifier,
            "type": type(self).__name__,
            "source": self.source,
            "label": self.label,
            "detail": self.detail,
            "weight": self.weight,
            "enabled": self.enabled,
        }


def _falloff(distance: np.ndarray, tolerance: float) -> np.ndarray:
    """Gaussian score: 1.0 on the money, decaying over *tolerance*."""
    tolerance = max(float(tolerance), 1e-6)
    return np.exp(-0.5 * (distance / tolerance) ** 2)


@dataclass
class LatitudeBand(Constraint):
    """The camera sat between two parallels."""

    min_lat: float = -90.0
    max_lat: float = 90.0
    softness: float = 2.0

    def score(self, lat_grid: np.ndarray, lon_grid: np.ndarray) -> np.ndarray:
        below = np.maximum(self.min_lat - lat_grid, 0.0)
        above = np.maximum(lat_grid - self.max_lat, 0.0)
        return _falloff(below + above, self.softness)


@dataclass
class LongitudeBand(Constraint):
    """The camera sat between two meridians (handles the antimeridian)."""

    min_lon: float = -180.0
    max_lon: float = 180.0
    softness: float = 2.0

    def score(self, lat_grid: np.ndarray, lon_grid: np.ndarray) -> np.ndarray:
        centre = (self.min_lon + self.max_lon) / 2.0
        half_width = abs(self.max_lon - self.min_lon) / 2.0
        delta = np.abs(((lon_grid - centre + 180.0) % 360.0) - 180.0)
        return _falloff(np.maximum(delta - half_width, 0.0), self.softness)


@dataclass
class CirclePrior(Constraint):
    """Within *radius_km* of a point - a GPS fix and its accuracy, say."""

    latitude: float = 0.0
    longitude: float = 0.0
    radius_km: float = 50.0
    softness_km: float = 25.0

    def score(self, lat_grid: np.ndarray, lon_grid: np.ndarray) -> np.ndarray:
        distance = _haversine_km(self.latitude, self.longitude, lat_grid, lon_grid)
        return _falloff(np.maximum(distance - self.radius_km, 0.0), self.softness_km)

    def search_bounds(self) -> Optional[Tuple[float, float, float, float]]:
        span = _km_to_degrees(self.radius_km + 3.0 * self.softness_km, self.latitude)
        return _window(self.latitude, self.longitude, span)


@dataclass
class ViewCone(Constraint):
    """What the camera was looking at, from EXIF coordinates and bearing."""

    _tolerance_fields = ("half_angle",)

    latitude: float = 0.0
    longitude: float = 0.0
    bearing: float = 0.0
    half_angle: float = 30.0
    max_km: float = 5.0

    def score(self, lat_grid: np.ndarray, lon_grid: np.ndarray) -> np.ndarray:
        distance = _haversine_km(self.latitude, self.longitude, lat_grid, lon_grid)
        heading = _bearing_grid(self.latitude, self.longitude, lat_grid, lon_grid)
        offset = np.abs(((heading - self.bearing + 180.0) % 360.0) - 180.0)

        angular = _falloff(np.maximum(offset - self.half_angle, 0.0), self.half_angle / 2.0)
        radial = _falloff(np.maximum(distance - self.max_km, 0.0), self.max_km / 2.0)
        return angular * radial

    def search_bounds(self) -> Optional[Tuple[float, float, float, float]]:
        span = _km_to_degrees(2.0 * self.max_km, self.latitude)
        return _window(self.latitude, self.longitude, span)


@dataclass
class SolarElevationConstraint(Constraint):
    """The sun stood at a measured elevation at a known UTC instant.

    Geometrically this is a circle of equal altitude: every point that sees the
    sun at that height lies the same angular distance from the subsolar point.
    """

    moment: Optional[datetime] = None
    elevation: float = 45.0
    tolerance: float = 2.0

    def score(self, lat_grid: np.ndarray, lon_grid: np.ndarray) -> np.ndarray:
        if self.moment is None:
            return np.ones_like(lat_grid, dtype=float)
        computed = solar.elevation_grid(lat_grid, lon_grid, self.moment)
        return _falloff(np.abs(computed - self.elevation), self.tolerance)


@dataclass
class SolarAzimuthConstraint(Constraint):
    """The sun bore in a measured compass direction at a known UTC instant."""

    moment: Optional[datetime] = None
    azimuth: float = 180.0
    tolerance: float = 5.0

    def score(self, lat_grid: np.ndarray, lon_grid: np.ndarray) -> np.ndarray:
        if self.moment is None:
            return np.ones_like(lat_grid, dtype=float)
        computed = solar.azimuth_grid(lat_grid, lon_grid, self.moment)
        offset = np.abs(((computed - self.azimuth + 180.0) % 360.0) - 180.0)
        return _falloff(offset, self.tolerance)


@dataclass
class ShadowLatitudeConstraint(Constraint):
    """Sun elevation at a local **solar** time, which constrains latitude only.

    Longitude cancels out of the hour-angle calculation when the time is solar,
    so this yields a latitude band and needs a second technique for longitude.

    ``local_solar_hour`` is *solar* time, not clock time. The two differ by up
    to three hours in real countries (France runs about 1.9 h ahead of its own
    sun, western China about 3 h), so passing a wall-clock reading here gives a
    confidently wrong latitude. Use :meth:`from_clock_time` when the UTC offset
    is known, or prefer :class:`SolarElevationConstraint` when the UTC instant
    is known - that one is exact.

    The reliable no-clock case is local solar noon, identifiable because the
    shadow is at its shortest; pass ``local_solar_hour=12``.
    """

    day: Optional[_date] = None
    local_solar_hour: float = 12.0
    elevation: float = 45.0
    tolerance: float = 2.0

    @classmethod
    def from_clock_time(
        cls,
        day: _date,
        clock_hour: float,
        utc_offset_hours: float,
        longitude: float,
        elevation: float,
        tolerance: float = 2.0,
        **kwargs,
    ) -> "ShadowLatitudeConstraint":
        """Build from wall-clock time when the UTC offset and longitude are known."""
        utc_hour = clock_hour - utc_offset_hours
        solar_hour = (utc_hour + longitude / 15.0) % 24.0
        return cls(day=day, local_solar_hour=solar_hour, elevation=elevation,
                   tolerance=tolerance, **kwargs)

    def score(self, lat_grid: np.ndarray, lon_grid: np.ndarray) -> np.ndarray:
        if self.day is None:
            return np.ones_like(lat_grid, dtype=float)
        noon = datetime(self.day.year, self.day.month, self.day.day, 12, 0, tzinfo=timezone.utc)
        declination, equation_of_time, _ = solar.solar_parameters(noon)
        true_solar_time = (self.local_solar_hour * 60.0 + equation_of_time) % 1440.0
        hour_angle = math.radians(true_solar_time / 4.0 - 180.0)

        lat_rad = np.radians(lat_grid)
        dec_rad = math.radians(declination)
        cos_zenith = np.clip(
            np.sin(lat_rad) * math.sin(dec_rad)
            + np.cos(lat_rad) * math.cos(dec_rad) * math.cos(hour_angle),
            -1.0,
            1.0,
        )
        computed = 90.0 - np.degrees(np.arccos(cos_zenith))
        return _falloff(np.abs(computed - self.elevation), self.tolerance)


@dataclass
class ResectionConstraint(Constraint):
    """Angles between identified landmarks fix where the camera stood.

    Classical three-point resection, evaluated over the grid rather than solved
    in closed form: this avoids the degenerate cases of the analytic solution
    and falls naturally out of the fusion step.
    """

    landmarks: Sequence[Tuple[float, float]] = ()
    angles: Sequence[float] = ()
    tolerance: float = 2.0

    def score(self, lat_grid: np.ndarray, lon_grid: np.ndarray) -> np.ndarray:
        if len(self.landmarks) < 2 or len(self.angles) < len(self.landmarks) - 1:
            return np.ones_like(lat_grid, dtype=float)

        bearings = [
            _bearing_grid(lat_grid, lon_grid, lat, lon) for lat, lon in self.landmarks
        ]
        residual = np.zeros_like(lat_grid, dtype=float)
        for index, measured in enumerate(self.angles[: len(self.landmarks) - 1]):
            separation = np.abs(
                ((bearings[index + 1] - bearings[index] + 180.0) % 360.0) - 180.0
            )
            residual += (separation - abs(measured)) ** 2
        return _falloff(np.sqrt(residual), self.tolerance)

    def solve(self):
        """Closed-form solution, or None when the geometry is degenerate."""
        from . import photogrammetry

        if len(self.landmarks) < 3 or len(self.angles) < 2:
            return None
        try:
            return photogrammetry.resect(self.landmarks, self.angles)
        except Exception:
            return None

    def search_bounds(self) -> Optional[Tuple[float, float, float, float]]:
        """Anchor the search on the closed-form solution.

        The band of positions matching a set of angles can be only metres wide
        while the plausible search area is kilometres across, so no practical
        grid will stumble onto it. Resection is therefore solved analytically
        and the grid is used only to blend it with the other evidence.
        """
        solution = self.solve()
        if solution is not None:
            # Wide enough that fusion can still pull the answer off this point
            # if the other constraints disagree with it.
            return _window(solution.latitude, solution.longitude, 0.05)

        if not self.landmarks:
            return None
        lats = [lat for lat, _ in self.landmarks]
        lons = [lon for _, lon in self.landmarks]
        extent = max(max(lats) - min(lats), max(lons) - min(lons))
        return _window(
            sum(lats) / len(lats), sum(lons) / len(lons), max(extent * 8.0, 0.6)
        )


@dataclass
class BearingConstraint(Constraint):
    """The camera lay along a known bearing from a known point."""

    latitude: float = 0.0
    longitude: float = 0.0
    bearing: float = 0.0
    tolerance: float = 2.0
    max_km: float = 200.0

    def score(self, lat_grid: np.ndarray, lon_grid: np.ndarray) -> np.ndarray:
        heading = _bearing_grid(self.latitude, self.longitude, lat_grid, lon_grid)
        offset = np.abs(((heading - self.bearing + 180.0) % 360.0) - 180.0)
        distance = _haversine_km(self.latitude, self.longitude, lat_grid, lon_grid)
        return _falloff(offset, self.tolerance) * _falloff(
            np.maximum(distance - self.max_km, 0.0), self.max_km / 2.0
        )

    def search_bounds(self) -> Optional[Tuple[float, float, float, float]]:
        span = _km_to_degrees(2.0 * self.max_km, self.latitude)
        return _window(self.latitude, self.longitude, span)


# --------------------------------------------------------------------------
# Geometry helpers (vectorised)
# --------------------------------------------------------------------------

def _haversine_km(lat: float, lon: float, lat_grid: np.ndarray, lon_grid: np.ndarray) -> np.ndarray:
    phi1 = math.radians(lat)
    phi2 = np.radians(lat_grid)
    delta_phi = phi2 - phi1
    delta_lambda = np.radians(((lon_grid - lon + 180.0) % 360.0) - 180.0)
    a = (
        np.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * np.cos(phi2) * np.sin(delta_lambda / 2.0) ** 2
    )
    return 2.0 * solar.EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def _km_to_degrees(km: float, latitude: float) -> float:
    """Rough span in degrees covering *km* at this latitude (longitude-safe)."""
    lat_span = km / 111.32
    cos_lat = max(math.cos(math.radians(latitude)), 0.05)
    return max(lat_span, km / (111.32 * cos_lat))


def _window(latitude: float, longitude: float, span: float) -> Tuple[float, float, float, float]:
    half = max(span, 0.02) / 2.0
    return (
        max(-90.0, latitude - half),
        min(90.0, latitude + half),
        longitude - half,
        longitude + half,
    )


def _intersect(windows: List[Tuple[float, float, float, float]]):
    """Overlap of several search windows, or None if they do not overlap."""
    lat_min = max(w[0] for w in windows)
    lat_max = min(w[1] for w in windows)
    lon_min = max(w[2] for w in windows)
    lon_max = min(w[3] for w in windows)
    if lat_min >= lat_max or lon_min >= lon_max:
        return None
    return (lat_min, lat_max, lon_min, lon_max)


def _bearing_grid(lat1, lon1, lat2, lon2) -> np.ndarray:
    """Bearing from point 1 to point 2; either argument may be an array."""
    phi1 = np.radians(lat1)
    phi2 = np.radians(lat2)
    delta = np.radians(np.asarray(lon2) - np.asarray(lon1))
    x = np.sin(delta) * np.cos(phi2)
    y = np.cos(phi1) * np.sin(phi2) - np.sin(phi1) * np.cos(phi2) * np.cos(delta)
    return np.degrees(np.arctan2(x, y)) % 360.0


# --------------------------------------------------------------------------
# The board
# --------------------------------------------------------------------------

class EvidenceBoard:
    """Holds the constraints and fuses them into one probability surface."""

    def __init__(self, constraints: Optional[Iterable[Constraint]] = None) -> None:
        self.constraints: List[Constraint] = list(constraints or [])

    # -- management ----------------------------------------------------
    def add(self, constraint: Constraint) -> Constraint:
        self.constraints.append(constraint)
        return constraint

    def remove(self, identifier: str) -> bool:
        before = len(self.constraints)
        self.constraints = [c for c in self.constraints if c.identifier != identifier]
        return len(self.constraints) != before

    def get(self, identifier: str) -> Optional[Constraint]:
        return next((c for c in self.constraints if c.identifier == identifier), None)

    def clear(self) -> None:
        self.constraints.clear()

    @property
    def active(self) -> List[Constraint]:
        return [c for c in self.constraints if c.enabled and c.weight > 0]

    def broadened(self, factor: float) -> "EvidenceBoard":
        return EvidenceBoard([c.broadened(factor) for c in self.active])

    def __len__(self) -> int:
        return len(self.constraints)

    # -- fusion --------------------------------------------------------
    def fuse(
        self,
        bounds: Tuple[float, float, float, float] = WORLD_BOUNDS,
        rows: int = 181,
        cols: int = 361,
    ) -> ProbabilityGrid:
        """Weighted geometric mean of every active constraint over a grid."""
        lat_min, lat_max, lon_min, lon_max = bounds
        latitudes = np.linspace(lat_min, lat_max, rows)
        longitudes = np.linspace(lon_min, lon_max, cols)
        lon_grid, lat_grid = np.meshgrid(longitudes, latitudes)

        active = self.active
        if not active:
            return ProbabilityGrid(np.ones((rows, cols)), lat_min, lat_max, lon_min, lon_max)

        # Log space keeps many multiplied constraints from underflowing.
        total_log = np.zeros((rows, cols), dtype=float)
        total_weight = 0.0
        for constraint in active:
            scores = constraint.score_clamped(lat_grid, lon_grid)
            total_log += constraint.weight * np.log(scores)
            total_weight += constraint.weight

        values = np.exp(total_log / max(total_weight, 1e-9))
        return ProbabilityGrid(
            values, lat_min, lat_max, lon_min, lon_max,
            raw_peak=float(np.max(values)) if values.size else 0.0,
        ).normalised()

    def refine(
        self,
        latitude: float,
        longitude: float,
        span_deg: float = 3.0,
        rows: int = 161,
        cols: int = 161,
    ) -> ProbabilityGrid:
        """Re-fuse at high resolution in a window around a candidate."""
        half = span_deg / 2.0
        bounds = (
            max(-90.0, latitude - half),
            min(90.0, latitude + half),
            longitude - half,
            longitude + half,
        )
        return self.fuse(bounds, rows=rows, cols=cols)

    def search_window(self) -> Optional[Tuple[float, float, float, float]]:
        """Where the coarse search should look, from the local constraints."""
        windows = [
            bounds
            for bounds in (c.search_bounds() for c in self.active)
            if bounds is not None
        ]
        if not windows:
            return None
        overlap = _intersect(windows)
        # Disagreeing local constraints are still worth searching: fall back to
        # the union so the fusion, not the hint, decides which one is wrong.
        if overlap is None:
            return (
                max(-90.0, min(w[0] for w in windows)),
                min(90.0, max(w[1] for w in windows)),
                min(w[2] for w in windows),
                max(w[3] for w in windows),
            )
        return overlap

    def _locate(
        self,
        window: Tuple[float, float, float, float],
        rows: int,
        cols: int,
        max_blur: float = 4096.0,
    ) -> ProbabilityGrid:
        """Fuse over *window*, blurring only as much as the grid demands.

        How wide a constraint's solution band is *in position* depends on the
        geometry - a bearing tolerance of 0.3 degrees is metres wide near a
        landmark and kilometres wide far from it - so the necessary blur cannot
        be computed from the window size. Instead it is measured: widen until
        the grid actually resolves something, then stop.
        """
        blur = 1.0
        grid = self.fuse(window, rows=rows, cols=cols)
        while not grid.has_signal and blur < max_blur:
            blur *= 4.0
            grid = self.broadened(blur).fuse(window, rows=rows, cols=cols)
        return grid

    def candidates(
        self,
        count: int = 5,
        coarse_rows: int = 181,
        coarse_cols: int = 361,
        refine: bool = True,
    ) -> List[Candidate]:
        """Search, then sharpen each hit with successively finer passes."""
        if not self.active:
            return []

        window = self.search_window()
        if window is None:
            window = WORLD_BOUNDS
            rows, cols, separation = coarse_rows, coarse_cols, 5.0
        else:
            rows = cols = 201
            separation = max((window[1] - window[0]) / 12.0, 0.01)

        coarse = self._locate(window, rows, cols)
        rough = coarse.top(count=count, min_separation_deg=separation)
        if not refine:
            return rough

        span = max(window[1] - window[0], (window[3] - window[2]) / 2.0)
        return self._refine_all(rough, span=span / 2.0)

    def _refine_all(self, rough: List[Candidate], span: float) -> List[Candidate]:
        """Zoom in on each hit, re-measuring the needed blur at every level."""
        refined: List[Candidate] = []
        for candidate in rough:
            latitude, longitude = candidate.latitude, candidate.longitude
            current = max(span, 1e-4)

            for _ in range(9):
                half = current / 2.0
                window = (
                    max(-90.0, latitude - half),
                    min(90.0, latitude + half),
                    longitude - half,
                    longitude + half,
                )
                grid = self._locate(window, rows=121, cols=121)
                if not grid.has_signal:
                    break
                peak = grid.peak()
                latitude, longitude = peak.latitude, peak.longitude
                current /= 4.0

            refined.append(
                Candidate(
                    latitude=latitude,
                    longitude=longitude,
                    score=self.score_at(latitude, longitude),
                    rank=candidate.rank,
                )
            )

        refined.sort(key=lambda c: c.score, reverse=True)
        for rank, candidate in enumerate(refined, start=1):
            candidate.rank = rank
        return refined

    def score_at(self, latitude: float, longitude: float) -> float:
        values = self.score_clamped(
            np.array([[float(latitude)]]), np.array([[float(longitude)]])
        )
        return float(values[0, 0])

    def search_bounds(self) -> Optional[Tuple[float, float, float, float]]:
        """Region this constraint is informative in, if it is a local one.

        A global search grid cannot resolve a constraint whose answer is a few
        hundred metres across, so local constraints declare a window for the
        board to search inside instead.  ``None`` means "no opinion".
        """
        return None

    def describe(self) -> str:
        return self.detail or self.label or self.source

    # Fields scaled when a constraint is broadened for a coarse search pass.
    _tolerance_fields = ("tolerance", "softness", "softness_km", "half_angle")

    def broadened(self, factor: float) -> "Constraint":
        """A copy with its tolerances widened by *factor*.

        A constraint whose solution band is thinner than one grid cell is
        invisible to that grid - every sample misses it. The search therefore
        starts with deliberately blurred constraints and sharpens them as it
        zooms in, so the band is always at least a cell wide.
        """
        import copy as _copy

        if factor <= 1.0:
            return self
        clone = _copy.copy(self)
        for name in self._tolerance_fields:
            value = getattr(clone, name, None)
            if isinstance(value, (int, float)) and value > 0:
                setattr(clone, name, float(value) * factor)
        return clone

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.identifier,
            "type": type(self).__name__,
            "source": self.source,
            "label": self.label,
            "detail": self.detail,
            "weight": self.weight,
            "enabled": self.enabled,
        }


def _falloff(distance: np.ndarray, tolerance: float) -> np.ndarray:
    """Gaussian score: 1.0 on the money, decaying over *tolerance*."""
    tolerance = max(float(tolerance), 1e-6)
    return np.exp(-0.5 * (distance / tolerance) ** 2)


@dataclass
class LatitudeBand(Constraint):
    """The camera sat between two parallels."""

    min_lat: float = -90.0
    max_lat: float = 90.0
    softness: float = 2.0

    def score(self, lat_grid: np.ndarray, lon_grid: np.ndarray) -> np.ndarray:
        below = np.maximum(self.min_lat - lat_grid, 0.0)
        above = np.maximum(lat_grid - self.max_lat, 0.0)
        return _falloff(below + above, self.softness)


@dataclass
class LongitudeBand(Constraint):
    """The camera sat between two meridians (handles the antimeridian)."""

    min_lon: float = -180.0
    max_lon: float = 180.0
    softness: float = 2.0

    def score(self, lat_grid: np.ndarray, lon_grid: np.ndarray) -> np.ndarray:
        centre = (self.min_lon + self.max_lon) / 2.0
        half_width = abs(self.max_lon - self.min_lon) / 2.0
        delta = np.abs(((lon_grid - centre + 180.0) % 360.0) - 180.0)
        return _falloff(np.maximum(delta - half_width, 0.0), self.softness)


@dataclass
class CirclePrior(Constraint):
    """Within *radius_km* of a point - a GPS fix and its accuracy, say."""

    latitude: float = 0.0
    longitude: float = 0.0
    radius_km: float = 50.0
    softness_km: float = 25.0

    def score(self, lat_grid: np.ndarray, lon_grid: np.ndarray) -> np.ndarray:
        distance = _haversine_km(self.latitude, self.longitude, lat_grid, lon_grid)
        return _falloff(np.maximum(distance - self.radius_km, 0.0), self.softness_km)

    def search_bounds(self) -> Optional[Tuple[float, float, float, float]]:
        span = _km_to_degrees(self.radius_km + 3.0 * self.softness_km, self.latitude)
        return _window(self.latitude, self.longitude, span)


@dataclass
class ViewCone(Constraint):
    """What the camera was looking at, from EXIF coordinates and bearing."""

    _tolerance_fields = ("half_angle",)

    latitude: float = 0.0
    longitude: float = 0.0
    bearing: float = 0.0
    half_angle: float = 30.0
    max_km: float = 5.0

    def score(self, lat_grid: np.ndarray, lon_grid: np.ndarray) -> np.ndarray:
        distance = _haversine_km(self.latitude, self.longitude, lat_grid, lon_grid)
        heading = _bearing_grid(self.latitude, self.longitude, lat_grid, lon_grid)
        offset = np.abs(((heading - self.bearing + 180.0) % 360.0) - 180.0)

        angular = _falloff(np.maximum(offset - self.half_angle, 0.0), self.half_angle / 2.0)
        radial = _falloff(np.maximum(distance - self.max_km, 0.0), self.max_km / 2.0)
        return angular * radial

    def search_bounds(self) -> Optional[Tuple[float, float, float, float]]:
        span = _km_to_degrees(2.0 * self.max_km, self.latitude)
        return _window(self.latitude, self.longitude, span)


@dataclass
class SolarElevationConstraint(Constraint):
    """The sun stood at a measured elevation at a known UTC instant.

    Geometrically this is a circle of equal altitude: every point that sees the
    sun at that height lies the same angular distance from the subsolar point.
    """

    moment: Optional[datetime] = None
    elevation: float = 45.0
    tolerance: float = 2.0

    def score(self, lat_grid: np.ndarray, lon_grid: np.ndarray) -> np.ndarray:
        if self.moment is None:
            return np.ones_like(lat_grid, dtype=float)
        computed = solar.elevation_grid(lat_grid, lon_grid, self.moment)
        return _falloff(np.abs(computed - self.elevation), self.tolerance)


@dataclass
class SolarAzimuthConstraint(Constraint):
    """The sun bore in a measured compass direction at a known UTC instant."""

    moment: Optional[datetime] = None
    azimuth: float = 180.0
    tolerance: float = 5.0

    def score(self, lat_grid: np.ndarray, lon_grid: np.ndarray) -> np.ndarray:
        if self.moment is None:
            return np.ones_like(lat_grid, dtype=float)
        computed = solar.azimuth_grid(lat_grid, lon_grid, self.moment)
        offset = np.abs(((computed - self.azimuth + 180.0) % 360.0) - 180.0)
        return _falloff(offset, self.tolerance)


@dataclass
class ShadowLatitudeConstraint(Constraint):
    """Sun elevation at a local **solar** time, which constrains latitude only.

    Longitude cancels out of the hour-angle calculation when the time is solar,
    so this yields a latitude band and needs a second technique for longitude.

    ``local_solar_hour`` is *solar* time, not clock time. The two differ by up
    to three hours in real countries (France runs about 1.9 h ahead of its own
    sun, western China about 3 h), so passing a wall-clock reading here gives a
    confidently wrong latitude. Use :meth:`from_clock_time` when the UTC offset
    is known, or prefer :class:`SolarElevationConstraint` when the UTC instant
    is known - that one is exact.

    The reliable no-clock case is local solar noon, identifiable because the
    shadow is at its shortest; pass ``local_solar_hour=12``.
    """

    day: Optional[_date] = None
    local_solar_hour: float = 12.0
    elevation: float = 45.0
    tolerance: float = 2.0

    @classmethod
    def from_clock_time(
        cls,
        day: _date,
        clock_hour: float,
        utc_offset_hours: float,
        longitude: float,
        elevation: float,
        tolerance: float = 2.0,
        **kwargs,
    ) -> "ShadowLatitudeConstraint":
        """Build from wall-clock time when the UTC offset and longitude are known."""
        utc_hour = clock_hour - utc_offset_hours
        solar_hour = (utc_hour + longitude / 15.0) % 24.0
        return cls(day=day, local_solar_hour=solar_hour, elevation=elevation,
                   tolerance=tolerance, **kwargs)

    def score(self, lat_grid: np.ndarray, lon_grid: np.ndarray) -> np.ndarray:
        if self.day is None:
            return np.ones_like(lat_grid, dtype=float)
        noon = datetime(self.day.year, self.day.month, self.day.day, 12, 0, tzinfo=timezone.utc)
        declination, equation_of_time, _ = solar.solar_parameters(noon)
        true_solar_time = (self.local_solar_hour * 60.0 + equation_of_time) % 1440.0
        hour_angle = math.radians(true_solar_time / 4.0 - 180.0)

        lat_rad = np.radians(lat_grid)
        dec_rad = math.radians(declination)
        cos_zenith = np.clip(
            np.sin(lat_rad) * math.sin(dec_rad)
            + np.cos(lat_rad) * math.cos(dec_rad) * math.cos(hour_angle),
            -1.0,
            1.0,
        )
        computed = 90.0 - np.degrees(np.arccos(cos_zenith))
        return _falloff(np.abs(computed - self.elevation), self.tolerance)


@dataclass
class ResectionConstraint(Constraint):
    """Angles between identified landmarks fix where the camera stood.

    Classical three-point resection, evaluated over the grid rather than solved
    in closed form: this avoids the degenerate cases of the analytic solution
    and falls naturally out of the fusion step.
    """

    landmarks: Sequence[Tuple[float, float]] = ()
    angles: Sequence[float] = ()
    tolerance: float = 2.0

    def score(self, lat_grid: np.ndarray, lon_grid: np.ndarray) -> np.ndarray:
        if len(self.landmarks) < 2 or len(self.angles) < len(self.landmarks) - 1:
            return np.ones_like(lat_grid, dtype=float)

        bearings = [
            _bearing_grid(lat_grid, lon_grid, lat, lon) for lat, lon in self.landmarks
        ]
        residual = np.zeros_like(lat_grid, dtype=float)
        for index, measured in enumerate(self.angles[: len(self.landmarks) - 1]):
            separation = np.abs(
                ((bearings[index + 1] - bearings[index] + 180.0) % 360.0) - 180.0
            )
            residual += (separation - abs(measured)) ** 2
        return _falloff(np.sqrt(residual), self.tolerance)

    def solve(self):
        """Closed-form solution, or None when the geometry is degenerate."""
        from . import photogrammetry

        if len(self.landmarks) < 3 or len(self.angles) < 2:
            return None
        try:
            return photogrammetry.resect(self.landmarks, self.angles)
        except Exception:
            return None

    def search_bounds(self) -> Optional[Tuple[float, float, float, float]]:
        """Anchor the search on the closed-form solution.

        The band of positions matching a set of angles can be only metres wide
        while the plausible search area is kilometres across, so no practical
        grid will stumble onto it. Resection is therefore solved analytically
        and the grid is used only to blend it with the other evidence.
        """
        solution = self.solve()
        if solution is not None:
            # Wide enough that fusion can still pull the answer off this point
            # if the other constraints disagree with it.
            return _window(solution.latitude, solution.longitude, 0.05)

        if not self.landmarks:
            return None
        lats = [lat for lat, _ in self.landmarks]
        lons = [lon for _, lon in self.landmarks]
        extent = max(max(lats) - min(lats), max(lons) - min(lons))
        return _window(
            sum(lats) / len(lats), sum(lons) / len(lons), max(extent * 8.0, 0.6)
        )


@dataclass
class BearingConstraint(Constraint):
    """The camera lay along a known bearing from a known point."""

    latitude: float = 0.0
    longitude: float = 0.0
    bearing: float = 0.0
    tolerance: float = 2.0
    max_km: float = 200.0

    def score(self, lat_grid: np.ndarray, lon_grid: np.ndarray) -> np.ndarray:
        heading = _bearing_grid(self.latitude, self.longitude, lat_grid, lon_grid)
        offset = np.abs(((heading - self.bearing + 180.0) % 360.0) - 180.0)
        distance = _haversine_km(self.latitude, self.longitude, lat_grid, lon_grid)
        return _falloff(offset, self.tolerance) * _falloff(
            np.maximum(distance - self.max_km, 0.0), self.max_km / 2.0
        )

    def search_bounds(self) -> Optional[Tuple[float, float, float, float]]:
        span = _km_to_degrees(2.0 * self.max_km, self.latitude)
        return _window(self.latitude, self.longitude, span)


# --------------------------------------------------------------------------
# Geometry helpers (vectorised)
# --------------------------------------------------------------------------

def _haversine_km(lat: float, lon: float, lat_grid: np.ndarray, lon_grid: np.ndarray) -> np.ndarray:
    phi1 = math.radians(lat)
    phi2 = np.radians(lat_grid)
    delta_phi = phi2 - phi1
    delta_lambda = np.radians(((lon_grid - lon + 180.0) % 360.0) - 180.0)
    a = (
        np.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * np.cos(phi2) * np.sin(delta_lambda / 2.0) ** 2
    )
    return 2.0 * solar.EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def _km_to_degrees(km: float, latitude: float) -> float:
    """Rough span in degrees covering *km* at this latitude (longitude-safe)."""
    lat_span = km / 111.32
    cos_lat = max(math.cos(math.radians(latitude)), 0.05)
    return max(lat_span, km / (111.32 * cos_lat))


def _window(latitude: float, longitude: float, span: float) -> Tuple[float, float, float, float]:
    half = max(span, 0.02) / 2.0
    return (
        max(-90.0, latitude - half),
        min(90.0, latitude + half),
        longitude - half,
        longitude + half,
    )


def _intersect(windows: List[Tuple[float, float, float, float]]):
    """Overlap of several search windows, or None if they do not overlap."""
    lat_min = max(w[0] for w in windows)
    lat_max = min(w[1] for w in windows)
    lon_min = max(w[2] for w in windows)
    lon_max = min(w[3] for w in windows)
    if lat_min >= lat_max or lon_min >= lon_max:
        return None
    return (lat_min, lat_max, lon_min, lon_max)


def _bearing_grid(lat1, lon1, lat2, lon2) -> np.ndarray:
    """Bearing from point 1 to point 2; either argument may be an array."""
    phi1 = np.radians(lat1)
    phi2 = np.radians(lat2)
    delta = np.radians(np.asarray(lon2) - np.asarray(lon1))
    x = np.sin(delta) * np.cos(phi2)
    y = np.cos(phi1) * np.sin(phi2) - np.sin(phi1) * np.cos(phi2) * np.cos(delta)
    return np.degrees(np.arctan2(x, y)) % 360.0


# --------------------------------------------------------------------------
# The board
# --------------------------------------------------------------------------

class EvidenceBoard:
    """Holds the constraints and fuses them into one probability surface."""

    def __init__(self, constraints: Optional[Iterable[Constraint]] = None) -> None:
        self.constraints: List[Constraint] = list(constraints or [])

    # -- management ----------------------------------------------------
    def add(self, constraint: Constraint) -> Constraint:
        self.constraints.append(constraint)
        return constraint

    def remove(self, identifier: str) -> bool:
        before = len(self.constraints)
        self.constraints = [c for c in self.constraints if c.identifier != identifier]
        return len(self.constraints) != before

    def get(self, identifier: str) -> Optional[Constraint]:
        return next((c for c in self.constraints if c.identifier == identifier), None)

    def clear(self) -> None:
        self.constraints.clear()

    @property
    def active(self) -> List[Constraint]:
        return [c for c in self.constraints if c.enabled and c.weight > 0]

    def broadened(self, factor: float) -> "EvidenceBoard":
        return EvidenceBoard([c.broadened(factor) for c in self.active])

    def __len__(self) -> int:
        return len(self.constraints)

    # -- fusion --------------------------------------------------------
    def fuse(
        self,
        bounds: Tuple[float, float, float, float] = WORLD_BOUNDS,
        rows: int = 181,
        cols: int = 361,
    ) -> ProbabilityGrid:
        """Weighted geometric mean of every active constraint over a grid."""
        lat_min, lat_max, lon_min, lon_max = bounds
        latitudes = np.linspace(lat_min, lat_max, rows)
        longitudes = np.linspace(lon_min, lon_max, cols)
        lon_grid, lat_grid = np.meshgrid(longitudes, latitudes)

        active = self.active
        if not active:
            return ProbabilityGrid(np.ones((rows, cols)), lat_min, lat_max, lon_min, lon_max)

        # Log space keeps many multiplied constraints from underflowing.
        total_log = np.zeros((rows, cols), dtype=float)
        total_weight = 0.0
        for constraint in active:
            scores = constraint.score_clamped(lat_grid, lon_grid)
            total_log += constraint.weight * np.log(scores)
            total_weight += constraint.weight

        values = np.exp(total_log / max(total_weight, 1e-9))
        return ProbabilityGrid(
            values, lat_min, lat_max, lon_min, lon_max,
            raw_peak=float(np.max(values)) if values.size else 0.0,
        ).normalised()

    def refine(
        self,
        latitude: float,
        longitude: float,
        span_deg: float = 3.0,
        rows: int = 161,
        cols: int = 161,
    ) -> ProbabilityGrid:
        """Re-fuse at high resolution in a window around a candidate."""
        half = span_deg / 2.0
        bounds = (
            max(-90.0, latitude - half),
            min(90.0, latitude + half),
            longitude - half,
            longitude + half,
        )
        return self.fuse(bounds, rows=rows, cols=cols)

    def search_window(self) -> Optional[Tuple[float, float, float, float]]:
        """Where the coarse search should look, from the local constraints."""
        windows = [
            bounds
            for bounds in (c.search_bounds() for c in self.active)
            if bounds is not None
        ]
        if not windows:
            return None
        overlap = _intersect(windows)
        # Disagreeing local constraints are still worth searching: fall back to
        # the union so the fusion, not the hint, decides which one is wrong.
        if overlap is None:
            return (
                max(-90.0, min(w[0] for w in windows)),
                min(90.0, max(w[1] for w in windows)),
                min(w[2] for w in windows),
                max(w[3] for w in windows),
            )
        return overlap

    def candidates(
        self,
        count: int = 5,
        coarse_rows: int = 181,
        coarse_cols: int = 361,
        refine: bool = True,
    ) -> List[Candidate]:
        """Search, then sharpen each hit with successively finer passes."""
        if not self.active:
            return []

        window = self.search_window()
        if window is None:
            window = WORLD_BOUNDS
            separation = 5.0
        else:
            separation = max((window[1] - window[0]) / 12.0, 0.01)

        span = max(window[1] - window[0], (window[3] - window[2]) / 2.0)
        rows = coarse_rows if window is WORLD_BOUNDS else 201
        cols = coarse_cols if window is WORLD_BOUNDS else 201

        # First pass: blur the constraints so no solution band can fall
        # between grid samples, then locate the promising neighbourhoods.
        blur = max(1.0, span / (max(rows, cols) * 0.02))
        coarse = self.broadened(blur).fuse(window, rows=rows, cols=cols)
        rough = coarse.top(count=count, min_separation_deg=separation)
        if not refine:
            return rough
        return self._refine_all(rough, span=span / 3.0)

    def _refine_all(self, rough: List[Candidate], span: float) -> List[Candidate]:
        """Zoom in on each hit, sharpening the constraints as the window shrinks."""
        refined: List[Candidate] = []
        for candidate in rough:
            latitude, longitude = candidate.latitude, candidate.longitude
            current = max(span, 0.002)
            for _ in range(7):
                # Keep the solution band about a cell wide at every zoom level.
                blur = max(1.0, current / (121 * 0.02))
                board = self.broadened(blur)
                grid = board.refine(latitude, longitude, span_deg=current, rows=121, cols=121)
                if not grid.has_signal:
                    # Nothing resolved here; widen rather than chase noise.
                    current *= 2.0
                    continue
                peak = grid.peak()
                latitude, longitude = peak.latitude, peak.longitude
                current /= 4.0
            refined.append(
                Candidate(
                    latitude=latitude,
                    longitude=longitude,
                    score=self.score_at(latitude, longitude),
                    rank=candidate.rank,
                )
            )

        refined.sort(key=lambda c: c.score, reverse=True)
        for rank, candidate in enumerate(refined, start=1):
            candidate.rank = rank
        return refined

    def score_at(self, latitude: float, longitude: float) -> float:
        """Fused score for a single point, on the same scale as the grid."""
        active = self.active
        if not active:
            return 1.0
        total_log = 0.0
        total_weight = 0.0
        for constraint in active:
            total_log += constraint.weight * math.log(constraint.score_at(latitude, longitude))
            total_weight += constraint.weight
        return math.exp(total_log / max(total_weight, 1e-9))

    def explain(self, latitude: float, longitude: float) -> List[Dict[str, Any]]:
        """Per-constraint scores at a point - the audit trail for a candidate."""
        rows = []
        for constraint in self.constraints:
            rows.append({
                "id": constraint.identifier,
                "source": constraint.source,
                "label": constraint.label or type(constraint).__name__,
                "detail": constraint.describe(),
                "weight": constraint.weight,
                "enabled": constraint.enabled,
                "score": round(constraint.score_at(latitude, longitude), 4)
                if constraint.enabled else None,
            })
        return rows

    def summary(self) -> Dict[str, Any]:
        return {
            "constraints": len(self.constraints),
            "active": len(self.active),
            "sources": sorted({c.source for c in self.active}),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {"constraints": [c.to_dict() for c in self.constraints]}
