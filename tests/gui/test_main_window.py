"""End-to-end tests driving the real main window."""

import pytest


@pytest.fixture
def window(themed, pump):
    from photosleuth.gui.main_window import MainWindow

    win = MainWindow()
    win.resize(1200, 800)
    win.show()
    pump()
    yield win
    win.runner.cancel_all()
    win.runner.wait(5000)
    win.close()


@pytest.fixture
def loaded(window, wait_for_idle, gallery, pump):
    """A window with the whole fixture gallery analysed."""
    from photosleuth.utils import find_images

    window.add_paths([str(path) for path in find_images(gallery)])
    assert wait_for_idle(window.runner)
    pump()
    return window


def test_window_starts_empty(window):
    assert window.model.rowCount() == 0
    assert window.empty_hint.isVisible() is True
    assert window.act_report.isEnabled() is False
    assert window.act_compare.isEnabled() is False


def test_loading_analyses_in_the_background(loaded):
    assert loaded.model.rowCount() >= 5
    assert len(loaded.model.records()) == loaded.model.rowCount()
    assert len(loaded.model.geotagged()) == 2
    assert loaded.empty_hint.isVisible() is False


def test_duplicate_paths_are_ignored(loaded, gallery, pump):
    from photosleuth.utils import find_images

    before = loaded.model.rowCount()
    loaded.add_paths([str(path) for path in find_images(gallery)])
    pump()
    assert loaded.model.rowCount() == before


def test_selecting_populates_every_tab(loaded, pump, image_ne):
    loaded.grid.select_path(str(image_ne))
    pump()
    assert loaded._current_path == str(image_ne)
    assert loaded.metadata.tree.topLevelItemCount() > 0
    assert loaded.viewer.canvas.has_image is True
    assert loaded.search.search_button.isEnabled() is True


def test_every_tab_renders(loaded, pump):
    """Visit every tab; none may raise, whatever the tab set has grown to."""
    titles = [loaded.tabs.tabText(i) for i in range(loaded.tabs.count())]
    for index in range(loaded.tabs.count()):
        loaded.tabs.setCurrentIndex(index)
        pump()
    for expected in ("Details", "Metadata", "Forensics", "Timeline", "Geolocate"):
        assert expected in titles


def test_filtering_updates_the_counter(loaded, pump):
    total = loaded.model.rowCount()
    loaded.gps_filter.setChecked(True)
    pump()
    assert loaded.proxy.rowCount() == 2
    assert "shown" in loaded.library_count.text()

    loaded.gps_filter.setChecked(False)
    loaded.filter_box.setText("zzz-no-match")
    pump()
    assert loaded.proxy.rowCount() == 0

    loaded.filter_box.clear()
    pump()
    assert loaded.proxy.rowCount() == total


def test_forensics_run_flags_the_edited_image(loaded, wait_for_idle, pump,
                                              image_with_stale_thumbnail):
    loaded.run_forensics()
    assert wait_for_idle(loaded.runner)
    pump()

    record = loaded.model.record(image_with_stale_thumbnail)
    assert record["forensics"]["verdict"] == "mismatch"
    assert record["forensics"]["flags"]

    loaded.flag_filter.setChecked(True)
    pump()
    assert loaded.proxy.rowCount() >= 1


def test_forensics_on_all_ignores_the_auto_selection(loaded, wait_for_idle, pump):
    """The first image is auto-selected; 'Check All' must still cover everything."""
    assert loaded.grid.selected_paths()
    loaded.run_forensics()
    assert wait_for_idle(loaded.runner)
    pump()
    checked = [r for r in loaded.model.records() if r.get("forensics")]
    assert len(checked) == loaded.model.rowCount()


def test_forensics_on_selection_is_scoped(loaded, wait_for_idle, pump, image_ne):
    loaded.grid.select_path(str(image_ne))
    pump()
    loaded.run_forensics_selected()
    assert wait_for_idle(loaded.runner)
    pump()
    checked = [r for r in loaded.model.records() if r.get("forensics")]
    assert len(checked) == 1


def test_strip_metadata_adds_the_clean_copy(loaded, wait_for_idle, pump, image_ne, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    loaded.grid.select_path(str(image_ne))
    pump()
    before = loaded.model.rowCount()
    loaded.strip_selected()
    assert wait_for_idle(loaded.runner)
    pump()

    assert loaded.model.rowCount() == before + 1
    cleaned = [p for p in loaded.model.paths() if p.endswith("_clean.jpg")]
    assert cleaned
    assert loaded.model.record(cleaned[0]).get("gps") is None


def test_remove_and_clear(loaded, pump, image_ne):
    loaded.grid.select_path(str(image_ne))
    pump()
    before = loaded.model.rowCount()
    loaded.remove_selected()
    pump()
    assert loaded.model.rowCount() == before - 1

    loaded.clear_library()
    pump()
    assert loaded.model.rowCount() == 0
    assert loaded.empty_hint.isVisible() is True


def test_actions_enable_with_selection(loaded, pump, image_ne, image_sw):
    from PySide6.QtCore import QItemSelectionModel

    loaded.grid.select_path(str(image_ne))
    pump()
    assert loaded.act_strip.isEnabled() is True
    assert loaded.act_compare.isEnabled() is False

    index = loaded.proxy.mapFromSource(loaded.model.index_of(image_sw))
    loaded.grid.view.selectionModel().select(index, QItemSelectionModel.Select)
    pump()
    assert loaded.act_compare.isEnabled() is True


def test_theme_switch_does_not_break_the_view(loaded, pump):
    for name in ("light", "dark", "system"):
        loaded.set_theme(name, persist=False)
        pump()
    assert loaded.model.rowCount() > 0


def test_session_round_trip(loaded, pump):
    from photosleuth import config

    loaded.tabs.setCurrentIndex(2)
    loaded.splitter.setSizes([500, 700])
    loaded._save_session()

    session = config.load_config()["session"]
    assert session["last_tab"] == 2
    assert session["window_geometry"]
    assert len(session["splitter_sizes"]) == 2


def test_recent_menu_is_rebuilt(window, pump, image_ne):
    from photosleuth import config

    config.remember_recent("file", str(image_ne))
    window._rebuild_recent_menu()
    pump()
    labels = [action.text() for action in window.recent_menu.actions()]
    assert any(image_ne.name in label for label in labels)


def test_timeline_follows_the_library(loaded, pump):
    loaded.timeline.set_records(loaded.model.records())
    pump()
    assert f"{loaded.model.rowCount()} images" in loaded.timeline.summary.text()


def test_cancel_is_safe_when_idle(loaded, pump):
    loaded.cancel_tasks()
    pump()
    assert loaded.runner.busy is False


def test_unreadable_file_does_not_stop_the_batch(window, wait_for_idle, pump,
                                                 gallery, not_an_image):
    from photosleuth.utils import find_images

    paths = [str(p) for p in find_images(gallery)] + [str(not_an_image)]
    window.add_paths(paths)
    assert wait_for_idle(window.runner)
    pump()
    assert len(window.model.records()) >= 5


def test_export_report_without_analysis_warns(window, pump, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown.append(a))
    window.export_report()
    assert shown


def test_close_saves_the_session(loaded, pump):
    from PySide6.QtGui import QCloseEvent

    event = QCloseEvent()
    loaded.closeEvent(event)
    assert event.isAccepted() is True
