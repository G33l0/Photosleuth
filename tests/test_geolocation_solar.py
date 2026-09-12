"""Solar position, validated against known astronomy."""

import math
from datetime import date, datetime, timedelta, timezone

import pytest

from photosleuth.geolocation import solar


@pytest.mark.parametrize(
    "day,expected",
    [(date(2024, 6, 20), 23.44), (date(2024, 12, 21), -23.44),
     (date(2024, 3, 20), 0.0), (date(2024, 9, 22), 0.0)],
)
def test_declination_at_solstices_and_equinoxes(day, expected):
    moment = datetime(day.year, day.month, day.day, 12, tzinfo=timezone.utc)
    assert solar.sun_position(0, 0, moment).declination == pytest.approx(expected, abs=0.25)


@pytest.mark.parametrize(
    "latitude,longitude,day",
    [(51.4779, 0.0, date(2024, 6, 21)), (0.0, 0.0, date(2024, 6, 21)),
     (-33.87, 151.21, date(2024, 12, 21)), (40.7, -74.0, date(2024, 3, 20))],
)
def test_noon_elevation_matches_the_identity(latitude, longitude, day):
    """At solar noon the sun's height is exactly 90 - |latitude - declination|."""
    noon = solar.solar_noon(latitude, longitude, day)
    position = solar.sun_position(latitude, longitude, noon)
    identity = 90.0 - abs(latitude - position.declination)
    assert position.elevation == pytest.approx(identity, abs=0.1)


def test_sun_is_due_south_at_northern_noon():
    noon = solar.solar_noon(51.5, 0.0, date(2024, 6, 21))
    assert solar.sun_position(51.5, 0.0, noon).azimuth == pytest.approx(180.0, abs=0.5)


def test_sun_is_due_north_at_southern_noon():
    noon = solar.solar_noon(-33.87, 151.21, date(2024, 6, 21))
    azimuth = solar.sun_position(-33.87, 151.21, noon).azimuth
    assert min(azimuth, 360.0 - azimuth) == pytest.approx(0.0, abs=0.5)


@pytest.mark.parametrize(
    "day,sunrise,sunset",
    [(date(2024, 6, 21), "03:43", "20:21"), (date(2024, 12, 21), "08:03", "15:53")],
)
def test_london_sunrise_and_sunset(day, sunrise, sunset):
    """Published times for Greenwich, matched to within two minutes."""
    rise, set_ = solar.sun_times(51.4779, -0.0015, day)
    assert abs((rise - _at(day, sunrise)).total_seconds()) < 120
    assert abs((set_ - _at(day, sunset)).total_seconds()) < 120


def _at(day, hhmm):
    hour, minute = (int(part) for part in hhmm.split(":"))
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc)


def test_polar_day_and_night_have_no_sunrise():
    assert solar.sun_times(78.2, 15.6, date(2024, 6, 21)) == (None, None)
    assert solar.sun_times(78.2, 15.6, date(2024, 12, 21)) == (None, None)


def test_subsolar_point_at_the_solstice():
    latitude, longitude = solar.subsolar_point(datetime(2024, 6, 21, 12, tzinfo=timezone.utc))
    assert latitude == pytest.approx(23.44, abs=0.1)
    assert abs(longitude) < 2.0


@pytest.mark.parametrize(
    "height,shadow,expected",
    [(1, 1, 45.0), (1, math.sqrt(3), 30.0), (math.sqrt(3), 1, 60.0), (1, 0, 90.0)],
)
def test_elevation_from_shadow(height, shadow, expected):
    assert solar.elevation_from_shadow(height, shadow) == pytest.approx(expected, abs=1e-6)


def test_shadow_ratio_round_trips():
    for elevation in (5.0, 20.0, 37.5, 60.0, 85.0):
        ratio = solar.shadow_ratio_from_elevation(elevation)
        assert solar.elevation_from_shadow(1.0, ratio) == pytest.approx(elevation, abs=1e-9)


def test_shadow_rejects_impossible_input():
    with pytest.raises(ValueError):
        solar.elevation_from_shadow(0, 1)
    with pytest.raises(ValueError):
        solar.elevation_from_shadow(1, -1)


def test_times_for_elevation_recovers_the_original_moment():
    latitude, longitude, day = 48.8584, 2.2945, date(2024, 7, 4)
    moment = datetime(2024, 7, 4, 9, 30, tzinfo=timezone.utc)
    elevation = solar.sun_position(latitude, longitude, moment).elevation

    hits = solar.times_for_elevation(latitude, longitude, day, elevation)
    assert len(hits) == 2               # one before noon, one after
    assert min(abs((hit - moment).total_seconds()) for hit in hits) < 90


def test_vectorised_elevation_matches_scalar():
    import numpy as np

    moment = datetime(2024, 7, 4, 9, 30, tzinfo=timezone.utc)
    lats = np.array([[48.86, 0.0], [-33.87, 40.7]])
    lons = np.array([[2.29, 0.0], [151.21, -74.0]])
    grid = solar.elevation_grid(lats, lons, moment)
    for row in range(2):
        for col in range(2):
            scalar = solar.sun_position(lats[row, col], lons[row, col], moment).elevation
            assert grid[row, col] == pytest.approx(scalar, abs=0.05)


def test_vectorised_azimuth_matches_scalar():
    import numpy as np

    moment = datetime(2024, 7, 4, 9, 30, tzinfo=timezone.utc)
    lats = np.array([[48.86, -33.87]])
    lons = np.array([[2.29, 151.21]])
    grid = solar.azimuth_grid(lats, lons, moment)
    for col in range(2):
        scalar = solar.sun_position(lats[0, col], lons[0, col], moment).azimuth
        assert grid[0, col] == pytest.approx(scalar, abs=0.1)


def test_latitudes_for_elevation_gives_two_hemispheres():
    hits = solar.latitudes_for_elevation(date(2024, 7, 4), 12.0, 60.0)
    assert len(hits) == 2
    assert any(h > 40 for h in hits) and any(h < 0 for h in hits)


def test_bearing_and_distance():
    assert solar.bearing(0, 0, 10, 0) == pytest.approx(0.0, abs=0.01)
    assert solar.bearing(0, 0, 0, 10) == pytest.approx(90.0, abs=0.01)
    assert solar.angular_distance(0, 0, 0, 10) == pytest.approx(10.0, abs=0.01)


def test_destination_round_trips():
    latitude, longitude = solar.destination(48.8584, 2.2945, 45.0, 10.0)
    assert solar.angular_distance(48.8584, 2.2945, latitude, longitude) * 111.32 == pytest.approx(
        10.0, rel=0.01
    )


def test_verify_claim_accepts_the_truth_and_rejects_a_lie():
    truth = (48.8584, 2.2945)
    moment = datetime(2024, 7, 4, 9, 30, tzinfo=timezone.utc)
    elevation = solar.sun_position(*truth, moment).elevation

    assert solar.verify_claim(*truth, moment, elevation)["consistent"] is True
    assert solar.verify_claim(-33.87, 151.21, moment, elevation)["consistent"] is False


def test_north_arrow_is_consistent_with_the_sun():
    truth = (48.8584, 2.2945)
    moment = datetime(2024, 7, 4, 9, 30, tzinfo=timezone.utc)
    position = solar.sun_position(*truth, moment)

    # A shadow drawn pointing straight up the image means image-up is the
    # shadow's true bearing, so north sits at minus that bearing.
    result = solar.north_arrow(*truth, moment, 0.0)
    assert result["true_shadow_azimuth"] == pytest.approx(position.shadow_azimuth, abs=0.01)
    assert result["image_north_direction"] == pytest.approx(
        (-position.shadow_azimuth) % 360.0, abs=0.01
    )


def test_north_arrow_refuses_when_the_sun_is_down():
    with pytest.raises(ValueError):
        solar.north_arrow(48.8584, 2.2945, datetime(2024, 1, 1, 1, tzinfo=timezone.utc), 0.0)
