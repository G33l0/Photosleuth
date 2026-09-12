"""Camera geometry: field of view, on-image angles, and resection.

Two things turn a photograph into measurements:

* the lens field of view, which converts pixel separations into real angles;
* resection, which converts angles between identified landmarks into the one
  place the camera could have been standing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Sensor widths in millimetres for the common formats, used when EXIF gives a
# focal length but no sensor size.
SENSOR_WIDTHS = {
    "full-frame": 36.0,
    "aps-c": 23.6,
    "aps-c-canon": 22.3,
    "micro-four-thirds": 17.3,
    "1-inch": 13.2,
    "1/1.7": 7.6,
    "1/2.3": 6.17,
    "phone": 5.6,
}

EARTH_RADIUS_M = 6371008.8


# --------------------------------------------------------------------------
# Field of view
# --------------------------------------------------------------------------

@dataclass
class Lens:
    """Everything needed to turn pixels into angles."""

    focal_mm: float
    sensor_width_mm: float
    image_width: int
    image_height: int
    source: str = "manual"

    @property
    def horizontal_fov(self) -> float:
        return 2.0 * math.degrees(math.atan(self.sensor_width_mm / (2.0 * self.focal_mm)))

    @property
    def sensor_height_mm(self) -> float:
        if not self.image_width:
            return self.sensor_width_mm
        return self.sensor_width_mm * self.image_height / self.image_width

    @property
    def vertical_fov(self) -> float:
        return 2.0 * math.degrees(math.atan(self.sensor_height_mm / (2.0 * self.focal_mm)))

    @property
    def diagonal_fov(self) -> float:
        diagonal = math.hypot(self.sensor_width_mm, self.sensor_height_mm)
        return 2.0 * math.degrees(math.atan(diagonal / (2.0 * self.focal_mm)))

    @property
    def focal_pixels(self) -> float:
        """Focal length in pixels - the constant that maps pixels to angles."""
        return (self.image_width / 2.0) / math.tan(math.radians(self.horizontal_fov) / 2.0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "focal_mm": round(self.focal_mm, 2),
            "sensor_width_mm": round(self.sensor_width_mm, 2),
            "image_width": self.image_width,
            "image_height": self.image_height,
            "horizontal_fov": round(self.horizontal_fov, 3),
            "vertical_fov": round(self.vertical_fov, 3),
            "diagonal_fov": round(self.diagonal_fov, 3),
            "focal_pixels": round(self.focal_pixels, 1),
            "source": self.source,
        }


def field_of_view(focal_mm: float, sensor_width_mm: float = 36.0) -> float:
    """Horizontal field of view in degrees."""
    if focal_mm <= 0 or sensor_width_mm <= 0:
        raise ValueError("Focal length and sensor width must be positive.")
    return 2.0 * math.degrees(math.atan(sensor_width_mm / (2.0 * focal_mm)))


def lens_from_metadata(metadata: Dict[str, Any]) -> Optional[Lens]:
    """Build a :class:`Lens` from EXIF, preferring the 35 mm equivalent.

    ``FocalLengthIn35mmFilm`` already folds in the crop factor, so pairing it
    with a 36 mm sensor width is exact and avoids having to guess the sensor.
    """
    exif = metadata.get("exif") or {}
    width, height = _image_size(metadata)
    if not width or not height:
        return None

    equivalent = _ratio(exif.get("EXIF FocalLengthIn35mmFilm"))
    if equivalent and equivalent > 0:
        return Lens(equivalent, 36.0, width, height, source="35mm equivalent (EXIF)")

    focal = _ratio(exif.get("EXIF FocalLength"))
    if focal and focal > 0:
        return Lens(focal, SENSOR_WIDTHS["full-frame"], width, height,
                    source="focal length (EXIF), full-frame sensor assumed")
    return None


def _image_size(metadata: Dict[str, Any]) -> Tuple[int, int]:
    exif = metadata.get("exif") or {}
    width = _ratio(exif.get("EXIF ExifImageWidth")) or _ratio(exif.get("Image ImageWidth"))
    height = _ratio(exif.get("EXIF ExifImageLength")) or _ratio(exif.get("Image ImageLength"))
    if width and height:
        return int(width), int(height)
    try:
        from PIL import Image

        with Image.open(metadata["file"]) as image:
            return image.width, image.height
    except Exception:
        return 0, 0


def _ratio(value) -> Optional[float]:
    """Parse the string forms exifread hands back ('35', '7/2', '[3, 2]')."""
    if value is None:
        return None
    text = str(value).strip().strip("[]")
    if "," in text:
        text = text.split(",")[0].strip()
    try:
        if "/" in text:
            numerator, denominator = text.split("/", 1)
            return float(numerator) / float(denominator)
        return float(text)
    except (ValueError, ZeroDivisionError):
        return None


# --------------------------------------------------------------------------
# Angles measured on the image
# --------------------------------------------------------------------------

def angle_between_pixels(
    point_a: Tuple[float, float],
    point_b: Tuple[float, float],
    lens: Lens,
) -> float:
    """Angle subtended at the camera by two points in the frame.

    Uses the pinhole model: each pixel becomes a ray, and the angle between the
    rays is the real-world angle. Treating the image as a flat protractor would
    be wrong away from the centre, which is exactly where landmarks tend to sit.
    """
    focal = lens.focal_pixels
    centre_x = lens.image_width / 2.0
    centre_y = lens.image_height / 2.0

    first = (point_a[0] - centre_x, point_a[1] - centre_y, focal)
    second = (point_b[0] - centre_x, point_b[1] - centre_y, focal)

    dot = sum(u * v for u, v in zip(first, second))
    magnitude = math.sqrt(sum(u * u for u in first)) * math.sqrt(sum(v * v for v in second))
    if magnitude == 0:
        return 0.0
    return math.degrees(math.acos(max(-1.0, min(1.0, dot / magnitude))))


def distance_to_object(real_height_m: float, pixel_height: float, lens: Lens) -> float:
    """Rough distance to an object of known height, in metres."""
    if pixel_height <= 0:
        raise ValueError("Pixel height must be positive.")
    return real_height_m * lens.focal_pixels / pixel_height


# --------------------------------------------------------------------------
# Local tangent plane
# --------------------------------------------------------------------------

def to_local_metres(latitude: float, longitude: float,
                    origin_lat: float, origin_lon: float) -> Tuple[float, float]:
    """Flat-earth east/north offsets from an origin. Fine over a few kilometres."""
    east = math.radians(longitude - origin_lon) * EARTH_RADIUS_M * math.cos(math.radians(origin_lat))
    north = math.radians(latitude - origin_lat) * EARTH_RADIUS_M
    return east, north


def from_local_metres(east: float, north: float,
                      origin_lat: float, origin_lon: float) -> Tuple[float, float]:
    latitude = origin_lat + math.degrees(north / EARTH_RADIUS_M)
    cos_lat = math.cos(math.radians(origin_lat))
    longitude = origin_lon + math.degrees(east / (EARTH_RADIUS_M * max(cos_lat, 1e-9)))
    return latitude, longitude


# --------------------------------------------------------------------------
# Three-point resection
# --------------------------------------------------------------------------

@dataclass
class Resection:
    latitude: float
    longitude: float
    residual_deg: float
    method: str
    landmarks: Sequence[Tuple[float, float]] = ()
    angles: Sequence[float] = ()

    @property
    def is_reliable(self) -> bool:
        return self.residual_deg < 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "latitude": round(self.latitude, 6),
            "longitude": round(self.longitude, 6),
            "residual_deg": round(self.residual_deg, 4),
            "method": self.method,
            "reliable": self.is_reliable,
        }


def _circle_through_two_points(ax, ay, bx, by, inscribed_deg):
    """Centres and radius of the two arcs seeing A-B at the given angle.

    The inscribed-angle theorem: every point on such an arc sees the chord at
    the same angle, and the circumradius is ``chord / (2 sin angle)``.
    """
    angle = math.radians(abs(inscribed_deg))
    if angle < 1e-6 or angle > math.pi - 1e-6:
        return []
    chord = math.hypot(bx - ax, by - ay)
    if chord == 0:
        return []

    radius = chord / (2.0 * math.sin(angle))
    midpoint = ((ax + bx) / 2.0, (ay + by) / 2.0)
    offset_squared = radius * radius - (chord / 2.0) ** 2
    offset = math.sqrt(max(offset_squared, 0.0))

    # Unit normal to the chord.
    nx, ny = -(by - ay) / chord, (bx - ax) / chord
    return [
        ((midpoint[0] + nx * offset, midpoint[1] + ny * offset), radius),
        ((midpoint[0] - nx * offset, midpoint[1] - ny * offset), radius),
    ]


def _intersect_circles(c1, r1, c2, r2):
    distance = math.hypot(c2[0] - c1[0], c2[1] - c1[1])
    if distance == 0 or distance > r1 + r2 or distance < abs(r1 - r2):
        return []
    a = (r1 * r1 - r2 * r2 + distance * distance) / (2.0 * distance)
    height_squared = r1 * r1 - a * a
    if height_squared < 0:
        return []
    height = math.sqrt(height_squared)
    base = (c1[0] + a * (c2[0] - c1[0]) / distance, c1[1] + a * (c2[1] - c1[1]) / distance)
    dx = height * (c2[1] - c1[1]) / distance
    dy = height * (c2[0] - c1[0]) / distance
    return [(base[0] + dx, base[1] - dy), (base[0] - dx, base[1] + dy)]


def resect(
    landmarks: Sequence[Tuple[float, float]],
    angles: Sequence[float],
) -> Optional[Resection]:
    """Where was the camera, given angles between three known landmarks?

    Solved in closed form by intersecting two inscribed-angle circles, then the
    ambiguous roots are scored against the measurements and the best is kept.
    A grid search cannot do this job: the solution band can be metres across
    inside a search area kilometres wide.
    """
    if len(landmarks) < 3 or len(angles) < 2:
        return None

    origin_lat = sum(lat for lat, _ in landmarks) / len(landmarks)
    origin_lon = sum(lon for _, lon in landmarks) / len(landmarks)
    points = [to_local_metres(lat, lon, origin_lat, origin_lon) for lat, lon in landmarks]

    (ax, ay), (bx, by), (cx, cy) = points[0], points[1], points[2]

    first = _circle_through_two_points(ax, ay, bx, by, angles[0])
    second = _circle_through_two_points(bx, by, cx, cy, angles[1])
    if not first or not second:
        return None

    best: Optional[Tuple[float, Tuple[float, float]]] = None
    for centre1, radius1 in first:
        for centre2, radius2 in second:
            for candidate in _intersect_circles(centre1, radius1, centre2, radius2):
                # One root of every pair is landmark B itself; discard it.
                if math.hypot(candidate[0] - bx, candidate[1] - by) < 1.0:
                    continue
                residual = _angle_residual(candidate, points, angles)
                if best is None or residual < best[0]:
                    best = (residual, candidate)

    if best is None:
        return None

    residual, (east, north) = best
    latitude, longitude = from_local_metres(east, north, origin_lat, origin_lon)
    return Resection(
        latitude=latitude,
        longitude=longitude,
        residual_deg=residual,
        method="inscribed-angle circles",
        landmarks=list(landmarks),
        angles=list(angles),
    )


def _angle_residual(observer, points, angles) -> float:
    """RMS difference between the angles a point would see and those measured."""
    bearings = [
        math.degrees(math.atan2(px - observer[0], py - observer[1])) % 360.0
        for px, py in points
    ]
    total = 0.0
    for index, measured in enumerate(angles[: len(points) - 1]):
        separation = abs(((bearings[index + 1] - bearings[index] + 180.0) % 360.0) - 180.0)
        total += (separation - abs(measured)) ** 2
    return math.sqrt(total / max(1, len(angles)))


def angles_from_bearings(bearings: Sequence[float]) -> List[float]:
    """Consecutive angular separations, the form :func:`resect` expects."""
    return [
        abs(((bearings[index + 1] - bearings[index] + 180.0) % 360.0) - 180.0)
        for index in range(len(bearings) - 1)
    ]
