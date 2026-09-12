"""The Evidence Board tab, the map widget and the measurement overlay."""

from datetime import date, datetime, timezone

import pytest

from photosleuth.geolocation import photogrammetry as pg, solar
from photosleuth.geolocation.constraints import CirclePrior, LatitudeBand, ResectionConstraint

TRUTH = (48.858370, 2.294481)
WHEN = datetime(2024, 7, 4, 9, 30, tzinfo=timezone.utc)
LANDMARKS = [(48.8738, 2.2950), (48.8606, 2.3376), (48.8462, 2.3372)]


@pytest.fixture(autouse=True)
def offline_tiles(monkeypatch):
    """Never touch the network from tests."""
    from photosleuth.gui.widgets import map_widget

    cache = map_widget.shared_tile_cache()
    cache.enabled = False
    yield
    cache.enabled = False


@pytest.fixture
def panel(themed, pump):
    from photosleuth.gui.widgets.evidence_board import EvidenceBoardPanel

    widget = EvidenceBoardPanel()
    widget.resize(1100, 700)
    widget.show()
    pump()
    yield widget
    widget.close()


# --- map widget -------------------------------------------------------------

@pytest.mark.parametrize(
    "latitude,longitude,zoom",
    [(48.8584, 2.2945, 14), (-33.87, 151.21, 10), (0, 0, 1), (85, -179, 5)],
)
def test_projection_round_trips(themed, latitude, longitude, zoom):
    from photosleuth.gui.widgets.map_widget import deg_to_pixel, pixel_to_deg

    x, y = deg_to_pixel(latitude, longitude, zoom)
    back_lat, back_lon = pixel_to_deg(x, y, zoom)
    assert back_lat == pytest.approx(latitude, abs=1e-6)
    assert back_lon == pytest.approx(longitude, abs=1e-6)


def test_centre_maps_to_the_middle_of_the_widget(themed, pump):
    from photosleuth.gui.widgets.map_widget import MapWidget

    widget = MapWidget()
    widget.resize(800, 600)
    widget.show()
    pump()
    widget.set_centre(48.8584, 2.2945, 13)
    point = widget.screen_of(48.8584, 2.2945)
    assert point.x() == pytest.approx(400, abs=1)
    assert point.y() == pytest.approx(300, abs=1)


def test_click_reports_coordinates(themed, pump):
    from PySide6.QtCore import QPoint

    from photosleuth.gui.widgets.map_widget import MapWidget

    widget = MapWidget()
    widget.resize(800, 600)
    widget.show()
    pump()
    widget.set_centre(48.8584, 2.2945, 13)
    latitude, longitude = widget.coords_of(QPoint(400, 300))
    assert latitude == pytest.approx(48.8584, abs=1e-4)
    assert longitude == pytest.approx(2.2945, abs=1e-4)


def test_fit_bounds_contains_the_region(themed, pump):
    from photosleuth.gui.widgets.map_widget import MapWidget

    widget = MapWidget()
    widget.resize(900, 600)
    widget.show()
    pump()
    widget.fit_bounds(48.80, 48.92, 2.20, 2.42)
    assert 48.80 < widget.centre_lat < 48.92
    assert 2.20 < widget.centre_lon < 2.42


def test_heatmap_accepts_a_grid(themed, pump):
    from photosleuth.geolocation.constraints import EvidenceBoard
    from photosleuth.gui.widgets.map_widget import MapWidget

    board = EvidenceBoard([CirclePrior(latitude=48.86, longitude=2.29,
                                       radius_km=3.0, softness_km=2.0)])
    grid = board.fuse((48.7, 49.0, 2.1, 2.5), rows=60, cols=60)

    widget = MapWidget()
    widget.resize(600, 400)
    widget.show()
    widget.set_heatmap(grid)
    pump()
    assert widget.heatmap is not None
    assert widget.heatmap.width() == 60
    widget.set_heatmap(None)
    assert widget.heatmap is None


def test_map_paints_without_tiles(themed, pump):
    from photosleuth.gui.widgets.map_widget import MapWidget

    widget = MapWidget()
    widget.resize(500, 400)
    widget.show()
    pump()
    assert not widget.grab().isNull()


# --- measurement overlay ----------------------------------------------------

def test_shadow_measurement_from_three_points(themed):
    from photosleuth.gui.widgets.measure_overlay import Measurement, MeasureMode

    measurement = Measurement(mode=MeasureMode.SHADOW,
                              points=[(100, 50), (100, 200), (260, 200)])
    observation = measurement.shadow_observation()
    assert observation.object_length == pytest.approx(150.0)
    assert observation.elevation == pytest.approx(43.15, abs=0.05)


def test_angle_measurement(themed):
    from photosleuth.gui.widgets.measure_overlay import Measurement, MeasureMode

    measurement = Measurement(mode=MeasureMode.ANGLE,
                              points=[(100, 100), (200, 100), (100, 200)])
    assert measurement.angle_degrees() == pytest.approx(90.0)


def test_incomplete_measurement_yields_nothing(themed):
    from photosleuth.gui.widgets.measure_overlay import Measurement, MeasureMode

    measurement = Measurement(mode=MeasureMode.SHADOW, points=[(0, 0)])
    assert measurement.is_complete is False
    assert measurement.shadow_observation() is None


def test_viewer_measure_mode_disables_panning(themed, pump, image_ne):
    from PySide6.QtWidgets import QGraphicsView

    from photosleuth.gui.widgets.image_viewer import ImageViewer
    from photosleuth.gui.widgets.measure_overlay import MeasureMode

    viewer = ImageViewer()
    viewer.resize(600, 400)
    viewer.show()
    viewer.show_image(image_ne)
    pump()

    viewer.set_measure_mode(MeasureMode.SHADOW)
    assert viewer.canvas.dragMode() == QGraphicsView.NoDrag
    viewer.set_measure_mode(MeasureMode.NONE)
    assert viewer.canvas.dragMode() == QGraphicsView.ScrollHandDrag


# --- the panel --------------------------------------------------------------

def test_panel_starts_empty(panel):
    assert len(panel.board) == 0
    assert panel.layers.topLevelItemCount() == 0
    assert panel.fuse_button.isEnabled() is False


def test_adding_constraints_populates_the_layer_list(panel, pump):
    panel.add_constraint(LatitudeBand(source="test", label="Band", min_lat=0, max_lat=10))
    pump()
    assert panel.layers.topLevelItemCount() == 1
    assert panel.fuse_button.isEnabled() is True


def test_unchecking_a_layer_disables_it(panel, pump):
    from PySide6.QtCore import Qt

    panel.add_constraint(LatitudeBand(source="test", label="Band", min_lat=0, max_lat=10))
    pump()
    item = panel.layers.topLevelItem(0)
    item.setCheckState(0, Qt.Unchecked)
    pump()
    assert panel.board.active == []


def test_fusing_produces_candidates(panel, pump):
    angles = pg.angles_from_bearings(
        [solar.bearing(*TRUTH, la, lo) for la, lo in LANDMARKS]
    )
    panel.add_constraint(ResectionConstraint(source="resection", label="3 landmarks",
                                             landmarks=LANDMARKS, angles=angles,
                                             tolerance=0.3))
    panel.fuse()
    pump()
    assert panel.candidate_list.topLevelItemCount() >= 1
    best = panel.candidates[0]
    error = solar.angular_distance(*TRUTH, best.latitude, best.longitude) * 111_320
    assert error < 200


def test_metadata_checks_add_constraints(panel, pump, tmp_path):
    from tests.test_geolocation_analysers import make_image

    panel.set_record(make_image(tmp_path / "m.jpg", offset="+02:00", dop=1.0,
                                method="GPS", direction=119.0, focal35=28))
    panel.run_metadata_checks()
    pump()
    sources = {c.source for c in panel.board.constraints}
    assert "exif" in sources
    assert panel.layers.topLevelItemCount() >= 2


def test_shadow_constraint_flows_from_the_form(panel, pump):
    from PySide6.QtCore import QDate, QDateTime, QTime

    elevation = solar.sun_position(*TRUTH, WHEN).elevation
    panel.shadow_when.setDateTime(QDateTime(QDate(2024, 7, 4), QTime(9, 30)))
    panel.shadow_object.setValue(100.0)
    panel.shadow_shadow.setValue(100.0 * solar.shadow_ratio_from_elevation(elevation))
    pump()
    assert f"{elevation:.2f}" in panel.shadow_elevation.text()

    panel.add_shadow_constraint()
    pump()
    assert any(c.source == "shadow" for c in panel.board.constraints)


def test_verify_shadow_reports_a_verdict(panel, pump):
    panel.set_record({"file": "x.jpg", "gps": {"latitude": TRUTH[0], "longitude": TRUTH[1]}})
    panel.shadow_object.setValue(100.0)
    panel.shadow_shadow.setValue(100.0)
    panel.verify_shadow()
    pump()
    text = panel.explanation.toPlainText()
    assert "Consistent" in text or "Inconsistent" in text


def test_landmark_pairing(panel, pump):
    panel.begin_landmark(320.0, 240.0)
    panel._map_clicked(48.8738, 2.2950)
    pump()
    assert len(panel.landmarks) == 1
    assert panel.landmark_list.topLevelItemCount() == 1


def test_clearing_the_board_resets_everything(panel, pump):
    panel.add_constraint(LatitudeBand(source="t", label="B", min_lat=0, max_lat=1))
    panel.begin_landmark(10.0, 10.0)
    panel._map_clicked(1.0, 1.0)
    panel.clear_board()
    pump()
    assert len(panel.board) == 0
    assert panel.landmarks == []
    assert panel.candidate_list.topLevelItemCount() == 0


def test_report_data_is_serialisable(panel, pump):
    import json

    panel.add_constraint(LatitudeBand(source="t", label="B", min_lat=0, max_lat=1))
    panel.fuse()
    pump()
    json.dumps(panel.report_data())        # must not raise


def test_fusing_with_nothing_is_safe(panel, pump):
    panel.fuse()
    pump()
    assert panel.candidates == []
