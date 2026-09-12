"""Constraint scoring and the fusion engine."""

from datetime import date, datetime, timezone

import numpy as np
import pytest

from photosleuth.geolocation import photogrammetry as pg
from photosleuth.geolocation import solar
from photosleuth.geolocation.constraints import (
    SCORE_FLOOR,
    CirclePrior,
    EvidenceBoard,
    LatitudeBand,
    LongitudeBand,
    ResectionConstraint,
    ShadowLatitudeConstraint,
    SolarAzimuthConstraint,
    SolarElevationConstraint,
    ViewCone,
)

TRUTH = (48.858370, 2.294481)
WHEN = datetime(2024, 7, 4, 9, 30, tzinfo=timezone.utc)
LANDMARKS = [(48.8738, 2.2950), (48.8606, 2.3376), (48.8462, 2.3372)]


def error_metres(candidate):
    return solar.angular_distance(*TRUTH, candidate.latitude, candidate.longitude) * 111_320


@pytest.fixture
def angles():
    return pg.angles_from_bearings([solar.bearing(*TRUTH, la, lo) for la, lo in LANDMARKS])


# --- individual constraints -------------------------------------------------

def test_latitude_band_scores_inside_and_outside():
    band = LatitudeBand(min_lat=40.0, max_lat=50.0, softness=1.0)
    assert band.score_at(45.0, 0.0) == pytest.approx(1.0)
    assert band.score_at(60.0, 0.0) < 0.05


def test_longitude_band_wraps_the_antimeridian():
    band = LongitudeBand(min_lon=170.0, max_lon=190.0, softness=1.0)
    assert band.score_at(0.0, 180.0) == pytest.approx(1.0)
    assert band.score_at(0.0, -175.0) == pytest.approx(1.0)   # same as +185
    assert band.score_at(0.0, 0.0) < 0.05


def test_circle_prior():
    circle = CirclePrior(latitude=48.86, longitude=2.29, radius_km=5.0, softness_km=2.0)
    assert circle.score_at(48.86, 2.29) == pytest.approx(1.0)
    assert circle.score_at(48.90, 2.29) > 0.5      # ~4 km away, inside
    assert circle.score_at(49.60, 2.29) < 0.05     # ~80 km away


def test_view_cone_only_looks_one_way():
    cone = ViewCone(latitude=48.86, longitude=2.29, bearing=90.0, half_angle=20.0, max_km=5.0)
    east = solar.destination(48.86, 2.29, 90.0, 2.0)
    west = solar.destination(48.86, 2.29, 270.0, 2.0)
    assert cone.score_at(*east) > 0.9
    assert cone.score_at(*west) < 0.05


def test_solar_elevation_is_a_circle_of_equal_altitude():
    elevation = solar.sun_position(*TRUTH, WHEN).elevation
    constraint = SolarElevationConstraint(moment=WHEN, elevation=elevation, tolerance=1.0)
    assert constraint.score_at(*TRUTH) == pytest.approx(1.0, abs=0.01)

    # Other points on the same circle score just as well - which is the point.
    subsolar = solar.subsolar_point(WHEN)
    radius = solar.angular_distance(*TRUTH, *subsolar)
    for azimuth in (0.0, 90.0, 180.0):
        elsewhere = solar.destination(*subsolar, azimuth, radius * 111.32)
        assert constraint.score_at(*elsewhere) > 0.8


def test_solar_azimuth_narrows_the_circle():
    position = solar.sun_position(*TRUTH, WHEN)
    constraint = SolarAzimuthConstraint(moment=WHEN, azimuth=position.azimuth, tolerance=1.0)
    assert constraint.score_at(*TRUTH) == pytest.approx(1.0, abs=0.01)
    assert constraint.score_at(-33.87, 151.21) < 0.1


def test_shadow_latitude_constraint_ignores_longitude():
    constraint = ShadowLatitudeConstraint(
        day=date(2024, 7, 4), local_solar_hour=12.0, elevation=60.0, tolerance=1.0
    )
    for longitude in (-120.0, 0.0, 90.0):
        assert constraint.score_at(52.79, longitude) == pytest.approx(
            constraint.score_at(52.79, 0.0), abs=1e-9
        )


def test_shadow_latitude_from_clock_time_converts_correctly():
    """France runs ~2 h ahead of its own sun; the conversion must absorb that."""
    elevation = solar.sun_position(*TRUTH, WHEN).elevation
    constraint = ShadowLatitudeConstraint.from_clock_time(
        day=date(2024, 7, 4), clock_hour=11.5, utc_offset_hours=2.0,
        longitude=TRUTH[1], elevation=elevation, tolerance=1.0,
    )
    assert constraint.score_at(TRUTH[0], 0.0) > 0.8
    # Feeding wall-clock time straight in would have pointed at the wrong band.
    naive = ShadowLatitudeConstraint(
        day=date(2024, 7, 4), local_solar_hour=11.5, elevation=elevation, tolerance=1.0
    )
    assert naive.score_at(TRUTH[0], 0.0) < 0.5


def test_constraints_never_score_below_the_floor():
    band = LatitudeBand(min_lat=0.0, max_lat=1.0, softness=0.1)
    assert band.score_at(-80.0, 0.0) == pytest.approx(SCORE_FLOOR)


def test_broadening_widens_tolerance():
    constraint = SolarElevationConstraint(moment=WHEN, elevation=50.0, tolerance=1.0)
    assert constraint.broadened(10.0).tolerance == pytest.approx(10.0)
    assert constraint.tolerance == pytest.approx(1.0)   # original untouched


# --- fusion -----------------------------------------------------------------

def test_fusion_recovers_a_known_location(angles):
    position = solar.sun_position(*TRUTH, WHEN)
    board = EvidenceBoard([
        SolarElevationConstraint(source="shadow", moment=WHEN,
                                 elevation=position.elevation, tolerance=1.5),
        SolarAzimuthConstraint(source="shadow", moment=WHEN,
                               azimuth=position.azimuth, tolerance=3.0),
        ResectionConstraint(source="resection", landmarks=LANDMARKS,
                            angles=angles, tolerance=0.3),
    ])
    best = board.candidates(count=1)[0]
    assert error_metres(best) < 50
    assert best.score > 0.9


def test_resection_alone_is_precise(angles):
    board = EvidenceBoard([
        ResectionConstraint(source="resection", landmarks=LANDMARKS,
                            angles=angles, tolerance=0.2)
    ])
    assert error_metres(board.candidates(count=1)[0]) < 100


def test_conflicting_evidence_lowers_confidence(angles):
    board = EvidenceBoard([
        ResectionConstraint(source="resection", landmarks=LANDMARKS,
                            angles=angles, tolerance=0.2),
        SolarElevationConstraint(source="shadow", moment=WHEN,
                                 elevation=15.0, tolerance=1.0),   # wrong
    ])
    best = board.candidates(count=1)[0]
    assert best.score < 0.5

    scores = {row["label"] or row["source"]: row["score"]
              for row in board.explain(best.latitude, best.longitude)}
    assert min(scores.values()) < 0.1     # the breakdown names the culprit


def test_disabled_constraints_are_ignored():
    board = EvidenceBoard()
    band = board.add(LatitudeBand(min_lat=0.0, max_lat=10.0))
    assert len(board.active) == 1
    band.enabled = False
    assert board.active == []
    assert board.fuse(rows=9, cols=9).values.max() == pytest.approx(1.0)


def test_weights_shift_the_balance():
    strong = LatitudeBand(min_lat=0.0, max_lat=1.0, softness=0.5, weight=5.0)
    weak = LatitudeBand(min_lat=50.0, max_lat=51.0, softness=0.5, weight=0.2)
    board = EvidenceBoard([strong, weak])
    assert board.score_at(0.5, 0.0) > board.score_at(50.5, 0.0)


def test_no_signal_is_reported_rather_than_faked():
    """A grid that resolves nothing must not be normalised into false certainty."""
    board = EvidenceBoard([
        ResectionConstraint(landmarks=[(0, 0), (0, 1), (1, 0)],
                            angles=[179.9, 179.9], tolerance=0.001)
    ])
    grid = board.fuse((-1, 2, -1, 2), rows=31, cols=31)
    assert grid.has_signal is False
    assert grid.raw_peak == pytest.approx(SCORE_FLOOR)


def test_empty_board_returns_no_candidates():
    assert EvidenceBoard().candidates() == []


def test_search_window_follows_local_constraints():
    board = EvidenceBoard([
        CirclePrior(latitude=48.86, longitude=2.29, radius_km=1.0, softness_km=0.5)
    ])
    window = board.search_window()
    assert window is not None
    assert window[0] < 48.86 < window[1]
    assert window[2] < 2.29 < window[3]


def test_global_constraints_give_no_window():
    assert EvidenceBoard([LatitudeBand(min_lat=0.0, max_lat=10.0)]).search_window() is None


def test_grid_geometry_and_peak():
    board = EvidenceBoard([CirclePrior(latitude=10.0, longitude=20.0,
                                       radius_km=1.0, softness_km=1.0)])
    grid = board.fuse((5.0, 15.0, 15.0, 25.0), rows=101, cols=101)
    assert grid.latitude_of(0) == pytest.approx(5.0)
    assert grid.longitude_of(100) == pytest.approx(25.0)
    peak = grid.peak()
    assert peak.latitude == pytest.approx(10.0, abs=0.2)
    assert peak.longitude == pytest.approx(20.0, abs=0.2)


def test_explain_lists_every_constraint():
    board = EvidenceBoard([
        LatitudeBand(source="a", label="A", min_lat=0.0, max_lat=10.0),
        LongitudeBand(source="b", label="B", min_lon=0.0, max_lon=10.0),
    ])
    rows = board.explain(5.0, 5.0)
    assert len(rows) == 2
    assert all(row["score"] == pytest.approx(1.0) for row in rows)


def test_board_serialises():
    board = EvidenceBoard([LatitudeBand(source="x", label="L", min_lat=0.0, max_lat=1.0)])
    payload = board.to_dict()
    assert payload["constraints"][0]["source"] == "x"
    assert payload["constraints"][0]["type"] == "LatitudeBand"
