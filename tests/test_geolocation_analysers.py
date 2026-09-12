"""EXIF geo-checks, photogrammetry and shadow analysis."""

from datetime import date, datetime, timezone

import pytest
from PIL import Image

piexif = pytest.importorskip("piexif")

from photosleuth.core import extract_metadata
from photosleuth.geolocation import exif_geo, photogrammetry as pg, shadow as sh, solar

TRUTH = (48.858370, 2.294481)
WHEN = datetime(2024, 7, 4, 9, 30, tzinfo=timezone.utc)


def _dms(value):
    value = abs(value)
    degrees = int(value)
    minutes = int((value - degrees) * 60)
    seconds = round(((value - degrees) * 60 - minutes) * 60 * 100)
    return ((degrees, 1), (minutes, 1), (seconds, 100))


def make_image(path, *, latitude=48.8584, longitude=2.2945, lat_ref="N", lon_ref="E",
               local="2024:07:04 11:30:00", gps_date="2024:07:04",
               gps_time=((9, 1), (30, 1), (0, 1)), offset=None, dop=None,
               satellites=None, method=None, direction=None, focal35=None):
    gps = {
        piexif.GPSIFD.GPSLatitudeRef: lat_ref.encode(),
        piexif.GPSIFD.GPSLatitude: _dms(latitude),
        piexif.GPSIFD.GPSLongitudeRef: lon_ref.encode(),
        piexif.GPSIFD.GPSLongitude: _dms(longitude),
    }
    if gps_date:
        gps[piexif.GPSIFD.GPSDateStamp] = gps_date.encode()
    if gps_time:
        gps[piexif.GPSIFD.GPSTimeStamp] = gps_time
    if dop is not None:
        gps[piexif.GPSIFD.GPSDOP] = (int(dop * 100), 100)
    if satellites:
        gps[piexif.GPSIFD.GPSSatellites] = satellites.encode()
    if method:
        gps[piexif.GPSIFD.GPSProcessingMethod] = b"ASCII\x00\x00\x00" + method.encode()
    if direction is not None:
        gps[piexif.GPSIFD.GPSImgDirection] = (int(direction * 100), 100)
        gps[piexif.GPSIFD.GPSImgDirectionRef] = b"T"

    exif = {piexif.ExifIFD.DateTimeOriginal: local.encode(),
            piexif.ExifIFD.PixelXDimension: 640, piexif.ExifIFD.PixelYDimension: 480}
    if offset:
        exif[piexif.ExifIFD.OffsetTimeOriginal] = offset.encode()
    if focal35:
        exif[piexif.ExifIFD.FocalLengthIn35mmFilm] = focal35

    Image.new("RGB", (640, 480), (70, 110, 160)).save(
        path,
        exif=piexif.dump({"0th": {piexif.ImageIFD.Make: b"TestCam"}, "Exif": exif,
                          "GPS": gps, "1st": {}, "thumbnail": None}),
    )
    return extract_metadata(path, geocode=False)


# --- timezone consistency (features 1 and 2) --------------------------------

def test_matching_clock_and_coordinates_are_consistent(tmp_path):
    metadata = make_image(tmp_path / "ok.jpg", offset="+02:00")
    result = exif_geo.check_timezone(metadata)
    assert result.verdict == "consistent"
    assert result.timezone == "Europe/Paris"


def test_spoofed_coordinates_are_caught(tmp_path):
    """Sydney coordinates with a European clock is an eight-hour lie."""
    metadata = make_image(tmp_path / "spoof.jpg", latitude=33.8688, longitude=151.2093,
                          lat_ref="S", lon_ref="E")
    result = exif_geo.check_timezone(metadata)
    assert result.verdict == "inconsistent"
    assert result.is_inconsistent
    assert "discrepancy" in result.message


def test_offset_alone_constrains_longitude(tmp_path):
    metadata = make_image(tmp_path / "nogps.jpg", offset="+09:00")
    result = exif_geo.check_timezone(metadata)
    band = result.constraints[0]
    assert band.score_at(35.0, 135.0) > 0.8      # Japan, near the +9 meridian
    assert band.score_at(35.0, -100.0) < 0.1


def test_missing_times_report_unknown(tmp_path):
    metadata = make_image(tmp_path / "bare.jpg", gps_date=None, gps_time=None)
    assert exif_geo.check_timezone(metadata).verdict == "unknown"


def test_beijing_time_in_xinjiang_is_questionable_not_tampering(tmp_path):
    """Urumqi's IANA zone is UTC+6 but people there keep Beijing time (UTC+8).

    An honest photo therefore looks two hours out, and must not be reported as
    altered metadata.
    """
    metadata = make_image(tmp_path / "cn.jpg", latitude=43.8, longitude=87.6,
                          local="2024:07:04 17:30:00")
    result = exif_geo.check_timezone(metadata)
    assert result.true_offset == pytest.approx(6.0)
    assert result.verdict == "questionable"
    assert result.is_inconsistent is False
    assert result.needs_attention is True


def test_a_large_mismatch_is_still_called_inconsistent(tmp_path):
    metadata = make_image(tmp_path / "far.jpg", latitude=33.8688, longitude=151.2093,
                          lat_ref="S", lon_ref="E")
    assert exif_geo.check_timezone(metadata).verdict == "inconsistent"


# --- GPS quality (feature 5) ------------------------------------------------

def test_good_fix_is_trusted(tmp_path):
    metadata = make_image(tmp_path / "good.jpg", dop=1.2, satellites="09", method="GPS")
    quality = exif_geo.check_gps_quality(metadata)
    assert quality.confidence == "high"
    assert quality.accuracy_m < 15


def test_cell_tower_fix_is_distrusted(tmp_path):
    metadata = make_image(tmp_path / "cell.jpg", method="CELLID")
    quality = exif_geo.check_gps_quality(metadata)
    assert quality.confidence == "low"
    assert quality.accuracy_m > 1000
    assert quality.constraints[0].weight < 1.0


def test_manual_coordinates_carry_no_evidence(tmp_path):
    metadata = make_image(tmp_path / "manual.jpg", method="MANUAL")
    assert exif_geo.check_gps_quality(metadata).confidence == "none"


def test_weak_geometry_widens_the_circle(tmp_path):
    metadata = make_image(tmp_path / "weak.jpg", dop=9.0, method="GPS")
    quality = exif_geo.check_gps_quality(metadata)
    assert quality.confidence == "low"
    assert quality.accuracy_m > 40


# --- direction and lens (features 4 and 15) ---------------------------------

def test_view_cone_from_direction(tmp_path):
    metadata = make_image(tmp_path / "dir.jpg", direction=90.0, focal35=28)
    direction = exif_geo.check_direction(metadata)
    assert direction.has_direction
    assert direction.bearing == pytest.approx(90.0)
    assert direction.reference == "true"
    cone = direction.constraints[0]
    east = solar.destination(48.8584, 2.2945, 90.0, 1.0)
    assert cone.score_at(*east) > 0.9


def test_missing_direction_is_reported(tmp_path):
    metadata = make_image(tmp_path / "nodir.jpg")
    assert exif_geo.check_direction(metadata).has_direction is False


def test_lens_from_35mm_equivalent(tmp_path):
    metadata = make_image(tmp_path / "lens.jpg", focal35=50)
    lens = pg.lens_from_metadata(metadata)
    assert lens.horizontal_fov == pytest.approx(39.6, abs=0.5)


def test_analyze_collects_everything(tmp_path):
    metadata = make_image(tmp_path / "all.jpg", offset="+02:00", dop=1.0,
                          satellites="10", method="GPS", direction=119.0, focal35=28)
    report = exif_geo.analyze(metadata)
    assert report["timezone"]["verdict"] == "consistent"
    assert report["lens"] is not None
    assert len(report["constraints"]) == 3
    assert report["warnings"] == []


# --- photogrammetry (features 14 and 15) ------------------------------------

@pytest.mark.parametrize(
    "focal,expected", [(24, 73.7), (35, 54.4), (50, 39.6), (85, 23.9)]
)
def test_field_of_view_matches_published_values(focal, expected):
    assert pg.field_of_view(focal, 36.0) == pytest.approx(expected, abs=0.3)


def test_angle_between_frame_edges_equals_the_field_of_view():
    lens = pg.Lens(focal_mm=24, sensor_width_mm=36, image_width=6000, image_height=4000)
    measured = pg.angle_between_pixels((0, 2000), (6000, 2000), lens)
    assert measured == pytest.approx(lens.horizontal_fov, abs=0.05)


def test_resection_recovers_the_camera_position():
    landmarks = [(48.8738, 2.2950), (48.8606, 2.3376), (48.8462, 2.3372)]
    angles = pg.angles_from_bearings(
        [solar.bearing(*TRUTH, la, lo) for la, lo in landmarks]
    )
    solution = pg.resect(landmarks, angles)
    error = solar.angular_distance(*TRUTH, solution.latitude, solution.longitude) * 111_320
    assert error < 5
    assert solution.is_reliable


def test_resection_degrades_gracefully_with_noise():
    landmarks = [(48.8738, 2.2950), (48.8606, 2.3376), (48.8462, 2.3372)]
    angles = pg.angles_from_bearings(
        [solar.bearing(*TRUTH, la, lo) for la, lo in landmarks]
    )
    noisy = [angles[0] + 0.5, angles[1] - 0.5]
    solution = pg.resect(landmarks, noisy)
    error = solar.angular_distance(*TRUTH, solution.latitude, solution.longitude) * 111_320
    assert error < 500          # half a degree of error costs a few hundred metres


def test_resection_needs_three_landmarks():
    assert pg.resect([(0, 0), (0, 1)], [45.0]) is None


def test_local_metre_conversion_round_trips():
    east, north = pg.to_local_metres(48.8600, 2.3000, 48.8584, 2.2945)
    latitude, longitude = pg.from_local_metres(east, north, 48.8584, 2.2945)
    assert latitude == pytest.approx(48.8600, abs=1e-6)
    assert longitude == pytest.approx(2.3000, abs=1e-6)


def test_distance_to_object():
    lens = pg.Lens(focal_mm=50, sensor_width_mm=36, image_width=6000, image_height=4000)
    # A 1.7 m person filling 500 px.
    assert pg.distance_to_object(1.7, 500, lens) == pytest.approx(28.3, rel=0.05)


# --- shadow analysis (features 6-10) ----------------------------------------

def test_observation_elevation_and_ratio():
    observation = sh.ShadowObservation(object_length=100.0, shadow_length=100.0)
    assert observation.elevation == pytest.approx(45.0)
    assert observation.ratio == pytest.approx(1.0)


def test_uncertainty_grows_when_the_sun_is_high():
    high = sh.ShadowObservation(object_length=200.0, shadow_length=20.0)   # ~84°
    low = sh.ShadowObservation(object_length=200.0, shadow_length=600.0)   # ~18°
    assert sh.elevation_uncertainty(high) > sh.elevation_uncertainty(low)


def test_verify_accepts_truth_and_rejects_a_lie():
    elevation = solar.sun_position(*TRUTH, WHEN).elevation
    observation = sh.ShadowObservation(
        object_length=100.0, shadow_length=100.0 * solar.shadow_ratio_from_elevation(elevation)
    )
    assert sh.verify(observation, *TRUTH, WHEN)["consistent"] is True
    assert sh.verify(observation, -33.87, 151.21, WHEN)["consistent"] is False


def test_time_of_day_finds_the_capture_moment():
    elevation = solar.sun_position(*TRUTH, WHEN).elevation
    observation = sh.ShadowObservation(
        object_length=100.0, shadow_length=100.0 * solar.shadow_ratio_from_elevation(elevation)
    )
    result = sh.time_of_day(observation, *TRUTH, date(2024, 7, 4))
    assert len(result["matches"]) == 2
    assert any(abs((m["utc"] - WHEN).total_seconds()) < 120 for m in result["matches"])


def test_time_of_day_reports_impossible_elevations():
    observation = sh.ShadowObservation(object_length=100.0, shadow_length=1.0)   # ~89.4°
    result = sh.time_of_day(observation, 78.2, 15.6, date(2024, 12, 21))
    assert result["matches"] == []
    assert "never" in result["message"]


def test_constraints_need_a_time():
    observation = sh.ShadowObservation(object_length=100.0, shadow_length=100.0)
    assert sh.constraints(observation) == []
    assert len(sh.constraints(observation, moment=WHEN)) == 1
    assert len(sh.constraints(observation, moment=WHEN, sun_azimuth=120.0)) == 2


def test_three_click_helper():
    observation = sh.observation_from_points((100, 50), (100, 200), (260, 200))
    assert observation.object_length == pytest.approx(150.0)
    assert observation.shadow_length == pytest.approx(160.0)
    assert observation.shadow_azimuth_image == pytest.approx(90.0)


@pytest.mark.parametrize(
    "start,end,expected",
    [((0, 0), (0, -10), 0.0), ((0, 0), (10, 0), 90.0),
     ((0, 0), (0, 10), 180.0), ((0, 0), (-10, 0), 270.0)],
)
def test_image_azimuth_uses_compass_convention(start, end, expected):
    assert sh.image_azimuth(start, end) == pytest.approx(expected)


def test_north_from_shadow_needs_a_drawn_direction():
    observation = sh.ShadowObservation(object_length=100.0, shadow_length=100.0)
    with pytest.raises(ValueError):
        sh.north_from_shadow(observation, *TRUTH, WHEN)
