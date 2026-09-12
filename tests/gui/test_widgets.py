"""Every widget and dialog is constructed and driven at least once."""

import pytest

from photosleuth import forensics
from photosleuth.core import extract_metadata


@pytest.fixture
def record_ne(image_ne):
    return extract_metadata(image_ne, geocode=False)


@pytest.fixture
def record_sw(image_sw):
    return extract_metadata(image_sw, geocode=False)


# --- image viewer -----------------------------------------------------------

def test_viewer_loads_and_zooms(themed, pump, image_with_matching_thumbnail):
    """Uses a 320x240 image so a 2x zoom stays well inside the clamp."""
    from photosleuth.gui.widgets.image_viewer import ImageViewer

    viewer = ImageViewer()
    viewer.resize(600, 400)
    viewer.show()
    pump()
    assert viewer.show_image(image_with_matching_thumbnail) is True

    before = viewer.canvas.current_scale()
    viewer.canvas.zoom(2.0)
    assert viewer.canvas.current_scale() == pytest.approx(before * 2, rel=0.01)
    viewer.canvas.fit()
    viewer.canvas.actual_size()
    assert viewer.canvas.current_scale() == pytest.approx(1.0, rel=0.01)


def test_viewer_zoom_is_clamped(themed, image_ne):
    from photosleuth.gui.widgets.image_viewer import MAX_SCALE, MIN_SCALE, ImageViewer

    viewer = ImageViewer()
    viewer.show_image(image_ne)
    for _ in range(60):
        viewer.canvas.zoom(2.0)
    assert viewer.canvas.current_scale() <= MAX_SCALE * 1.01
    for _ in range(120):
        viewer.canvas.zoom(0.5)
    assert viewer.canvas.current_scale() >= MIN_SCALE * 0.99


def test_viewer_rejects_a_non_image(themed, not_an_image):
    from photosleuth.gui.widgets.image_viewer import ImageViewer

    viewer = ImageViewer()
    assert viewer.show_image(not_an_image) is False
    assert "Error" in viewer.caption.text()


def test_viewer_rotate_and_clear(themed, image_ne):
    from photosleuth.gui.widgets.image_viewer import ImageViewer

    viewer = ImageViewer()
    viewer.show_image(image_ne)
    viewer.canvas.rotate_by(90)
    viewer.clear()
    assert viewer.canvas.has_image is False


# --- metadata tree ----------------------------------------------------------

def test_metadata_tree_groups(themed, pump, record_ne):
    from photosleuth.gui.widgets.metadata_tree import MetadataTree

    tree = MetadataTree()
    tree.set_metadata(record_ne)
    pump()
    titles = [tree.tree.topLevelItem(i).text(0) for i in range(tree.tree.topLevelItemCount())]
    assert any("File Info" in t for t in titles)
    assert any("Camera" in t for t in titles)
    assert any("Location" in t for t in titles)


def test_metadata_filter_hides_groups(themed, pump, record_ne):
    from photosleuth.gui.widgets.metadata_tree import MetadataTree

    tree = MetadataTree()
    tree.set_metadata(record_ne)
    tree.filter_box.setText("latitude")
    pump()
    visible = [
        tree.tree.topLevelItem(i).text(0)
        for i in range(tree.tree.topLevelItemCount())
        if not tree.tree.topLevelItem(i).isHidden()
    ]
    assert len(visible) == 1 and "Location" in visible[0]


def test_metadata_filter_with_no_match(themed, pump, record_ne):
    from photosleuth.gui.widgets.metadata_tree import MetadataTree

    tree = MetadataTree()
    tree.set_metadata(record_ne)
    tree.filter_box.setText("zzzz-no-such-tag")
    pump()
    assert all(
        tree.tree.topLevelItem(i).isHidden() for i in range(tree.tree.topLevelItemCount())
    )


def test_metadata_tree_handles_none(themed, record_ne):
    from photosleuth.gui.widgets.metadata_tree import MetadataTree

    tree = MetadataTree()
    tree.set_metadata(record_ne)
    tree.set_metadata(None)
    assert tree.tree.topLevelItemCount() == 0


def test_metadata_tree_shows_forensics(themed, pump, image_with_stale_thumbnail):
    from photosleuth.gui.widgets.metadata_tree import MetadataTree

    record = extract_metadata(image_with_stale_thumbnail, geocode=False)
    record["forensics"] = forensics.analyze(image_with_stale_thumbnail, record)
    tree = MetadataTree()
    tree.set_metadata(record)
    pump()
    titles = [tree.tree.topLevelItem(i).text(0) for i in range(tree.tree.topLevelItemCount())]
    assert any("Forensics" in t for t in titles)


# --- thumbnail grid ---------------------------------------------------------

def test_grid_selection(themed, pump, image_ne, image_sw):
    from photosleuth.gui.models import ImageLibraryModel, LibraryFilterProxy
    from photosleuth.gui.widgets.thumbnail_grid import ThumbnailGrid

    model = ImageLibraryModel()
    proxy = LibraryFilterProxy()
    proxy.setSourceModel(model)
    model.add_paths([image_ne, image_sw])

    grid = ThumbnailGrid(proxy)
    grid.resize(600, 400)
    grid.show()
    pump()

    grid.select_first()
    assert grid.selected_paths() == [str(image_ne)]
    grid.select_path(str(image_sw))
    assert grid.selected_paths() == [str(image_sw)]


def test_grid_thumbnail_size(themed, image_ne):
    from photosleuth.gui.models import ImageLibraryModel
    from photosleuth.gui.widgets.thumbnail_grid import ThumbnailGrid

    model = ImageLibraryModel()
    model.add_paths([image_ne])
    grid = ThumbnailGrid(model)
    grid.set_thumbnail_size(220)
    assert grid.delegate.thumb_size == 220


def test_dropped_folder_is_expanded(themed, gallery, image_ne):
    from PySide6.QtCore import QMimeData, QUrl

    from photosleuth.gui.widgets.thumbnail_grid import collect_dropped_paths

    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(gallery))])
    found = collect_dropped_paths(mime)
    assert str(image_ne) in found
    assert len(found) >= 3


def test_dropped_non_image_is_ignored(themed, tmp_path):
    from PySide6.QtCore import QMimeData, QUrl

    from photosleuth.gui.widgets.thumbnail_grid import collect_dropped_paths

    document = tmp_path / "notes.txt"
    document.write_text("hello")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(document))])
    assert collect_dropped_paths(mime) == []


# --- timeline ---------------------------------------------------------------

def test_timeline_buckets(themed, pump, record_ne, record_sw):
    from photosleuth.gui.widgets.timeline_view import TimelineView

    view = TimelineView()
    view.resize(800, 300)
    view.show()
    view.set_records([record_ne, record_sw])
    pump()
    assert "2 images" in view.summary.text()

    view.grouping.setCurrentIndex(2)  # group by year
    pump()
    assert "bucket" in view.summary.text()


def test_timeline_handles_undated(themed, pump):
    from photosleuth.gui.widgets.timeline_view import build_buckets, parse_timestamp

    assert parse_timestamp({}) is None
    buckets = build_buckets([{"name": "x"}], "%Y-%m-%d")
    assert buckets[0][0] == "No date"


def test_timeline_empty(themed, pump):
    from photosleuth.gui.widgets.timeline_view import TimelineView

    view = TimelineView()
    view.set_records([])
    pump()
    assert "0 images" in view.summary.text()


# --- forensics panel --------------------------------------------------------

def test_forensics_panel_states(themed, pump, image_with_stale_thumbnail):
    from photosleuth.gui.widgets.forensics_panel import ForensicsPanel

    panel = ForensicsPanel()
    panel.resize(700, 500)
    panel.show()

    panel.set_image(None)
    assert "No images" in panel.verdict.text()

    panel.set_image(str(image_with_stale_thumbnail))
    pump()
    assert "Not analysed" in panel.verdict.text()

    record = extract_metadata(image_with_stale_thumbnail, geocode=False)
    panel.set_image(str(image_with_stale_thumbnail),
                    forensics.analyze(image_with_stale_thumbnail, record))
    pump()
    assert "does NOT match" in panel.verdict.text()
    assert "SHA-256" in panel.details.toPlainText()


def test_forensics_panel_match(themed, pump, image_with_matching_thumbnail):
    from photosleuth.gui.widgets.forensics_panel import ForensicsPanel

    panel = ForensicsPanel()
    record = extract_metadata(image_with_matching_thumbnail, geocode=False)
    panel.set_image(str(image_with_matching_thumbnail),
                    forensics.analyze(image_with_matching_thumbnail, record))
    pump()
    assert "matches" in panel.verdict.text()


# --- search panel -----------------------------------------------------------

def test_search_panel_engines(themed, image_ne):
    from photosleuth.gui.widgets.search_panel import SearchPanel

    panel = SearchPanel()
    engines = [panel.engine_box.itemData(i) for i in range(panel.engine_box.count())]
    assert "google_vision" in engines and "yandex" in engines

    assert panel.search_button.isEnabled() is False
    panel.set_image(str(image_ne))
    assert panel.search_button.isEnabled() is True


def test_search_panel_renders_api_results(themed, pump, image_ne):
    from photosleuth.gui.widgets.search_panel import SearchPanel

    panel = SearchPanel()
    panel.set_image(str(image_ne))
    panel.show_result({
        "engine": "google_vision", "mode": "api",
        "best_guess": ["Eiffel Tower"],
        "entities": [{"description": "Eiffel Tower", "score": 0.92}],
        "pages_with_matching_images": [{"url": "https://example.com/a", "title": "A"}],
        "full_matching_images": ["https://www.example.com/1.jpg"],
        "partial_matching_images": [], "visually_similar_images": [], "landmarks": [],
    })
    pump()
    assert "Eiffel Tower" in panel.summary.toPlainText()
    assert panel.results.count() == 1
    assert panel.results.item(0).text() == "example.com"


def test_search_panel_browser_mode(themed, pump, image_ne):
    from photosleuth.gui.widgets.search_panel import SearchPanel

    panel = SearchPanel()
    panel.set_image(str(image_ne))
    panel.show_result({
        "engine": "yandex", "mode": "browser",
        "url": "https://yandex.com/images/", "instructions": "Drop the file here.",
    })
    pump()
    assert "Drop the file here." in panel.summary.toPlainText()


def test_search_panel_error(themed, pump, image_ne):
    from photosleuth.gui.widgets.search_panel import SearchPanel

    panel = SearchPanel()
    panel.set_image(str(image_ne))
    panel.show_error("No API key configured.")
    pump()
    assert "No API key" in panel.summary.toPlainText()
    assert panel.search_button.isEnabled() is True
