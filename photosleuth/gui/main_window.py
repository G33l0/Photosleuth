"""The PhotoSleuth main window.

Workflow
--------
1. Open images (drop, File menu, Explorer, or the command line).
2. They land in the Library on the left; analysis runs in the background with a
   progress bar and a Cancel button, so the window stays usable throughout.
3. Selecting an image fills the tabs on the right: Preview, Metadata,
   Forensics, Reverse Search.  Nothing re-reads the disk - the results are
   already in the model.
4. The Timeline tab arranges everything by capture date.
5. Tools act on the current selection; Reports export the whole library or just
   the selection.  Every action is written to the chain-of-custody log.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QByteArray, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QActionGroup, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .. import __version__, config as config_module, custody
from ..i18n import available_languages, set_language, tr
from ..utils import IMAGE_EXTENSIONS, find_images
from . import theme
from .dialogs.about_dialog import AboutDialog, UpdateDialog
from .dialogs.compare_dialog import CompareDialog
from .dialogs.custody_dialog import CustodyDialog
from .dialogs.geotag_dialog import GeotagDialog
from .dialogs.report_dialog import ReportDialog
from .dialogs.settings_dialog import SettingsDialog
from .models import ImageLibraryModel, LibraryFilterProxy, PathRole
from .resources import app_icon, icon
from .widgets.evidence_board import EvidenceBoardPanel
from .widgets.forensics_panel import ForensicsPanel
from .widgets.image_viewer import ImageViewer
from .widgets.measure_overlay import MeasureMode
from .widgets.metadata_tree import MetadataTree
from .widgets.network_status import NetworkStatusButton
from .widgets.search_panel import SearchPanel
from .widgets.thumbnail_grid import ThumbnailGrid, collect_dropped_paths
from .widgets.timeline_view import TimelineView
from .workers import AnalyzeWorker, ForensicsWorker, SearchWorker, TaskRunner, ThumbnailWorker


class MainWindow(QMainWindow):
    """Top-level window: library on the left, detail tabs on the right."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"PhotoSleuth {__version__}")
        self.setWindowIcon(app_icon())
        self.setAcceptDrops(True)
        self.resize(1340, 860)
        self.setMinimumSize(QSize(900, 600))

        self.config = config_module.load_config()
        self.ui_settings = self.config.get("ui", {})

        self.model = ImageLibraryModel(self)
        self.proxy = LibraryFilterProxy(self)
        self.proxy.setSourceModel(self.model)

        self.runner = TaskRunner(self)
        self.runner.busyChanged.connect(self._set_busy)
        self._analyze_worker: Optional[AnalyzeWorker] = None
        self._current_path: Optional[str] = None

        self._build_ui()
        self._build_actions()
        self._build_menus()
        self._build_toolbar()
        self._build_statusbar()

        self.model.countChanged.connect(self._update_counts)
        self._update_actions()
        self._restore_session()

        if self.config.get("updates", {}).get("check_on_startup", False):
            QTimer.singleShot(2500, lambda: self.check_updates(quiet=True))

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        colours = theme.palette()

        # --- left: the library -----------------------------------------
        self.filter_box = QLineEdit(self)
        self.filter_box.setPlaceholderText(tr("Search metadata…"))
        self.filter_box.setClearButtonEnabled(True)
        self.filter_box.textChanged.connect(self.proxy.set_text)
        self.filter_box.textChanged.connect(
            lambda _text: self._update_counts(self.model.rowCount())
        )

        self.gps_filter = QCheckBox("GPS", self)
        self.gps_filter.setToolTip("Show only geotagged images")
        self.gps_filter.toggled.connect(self.proxy.set_only_geotagged)
        self.gps_filter.toggled.connect(lambda _on: self._update_counts(self.model.rowCount()))

        self.flag_filter = QCheckBox("Flagged", self)
        self.flag_filter.setToolTip("Show only images with forensic findings")
        self.flag_filter.toggled.connect(self.proxy.set_only_flagged)
        self.flag_filter.toggled.connect(lambda _on: self._update_counts(self.model.rowCount()))

        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(8, 8, 8, 4)
        filter_row.addWidget(self.filter_box, 1)
        filter_row.addWidget(self.gps_filter)
        filter_row.addWidget(self.flag_filter)

        self.grid = ThumbnailGrid(self.proxy, self)
        self.grid.set_thumbnail_size(int(self.ui_settings.get("thumbnail_size", 160)))
        self.grid.pathsDropped.connect(self.add_paths)
        self.grid.selectionChanged.connect(self._selection_changed)

        self.empty_hint = QLabel(
            f"<div style='color:{colours['text_muted']};text-align:center'>"
            f"<p style='font-size:15px'>{tr('Drop images or a folder here')}</p>"
            f"<p>{tr('or use File → Open')}</p></div>",
            self,
        )
        self.empty_hint.setAlignment(Qt.AlignCenter)
        self.empty_hint.setWordWrap(True)

        self.library_count = QLabel("", self)
        self.library_count.setStyleSheet(f"color: {colours['text_muted']}; padding: 0 8px 6px;")

        left = QWidget(self)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        left_layout.addLayout(filter_row)
        left_layout.addWidget(self.empty_hint, 1)
        left_layout.addWidget(self.grid, 1)
        left_layout.addWidget(self.library_count)
        self.grid.hide()

        # --- right: detail tabs ----------------------------------------
        self.viewer = ImageViewer(self)
        self.metadata = MetadataTree(self)
        self.forensics = ForensicsPanel(self)
        self.forensics.runRequested.connect(self.run_forensics_for)
        self.search = SearchPanel(self)
        self.search.searchRequested.connect(self.run_search)
        self.search.statusMessage.connect(self.status_message)
        self.timeline = TimelineView(self)
        self.timeline.bucketClicked.connect(self._timeline_bucket_clicked)

        self.geolocate = EvidenceBoardPanel(self)
        self.geolocate.statusMessage.connect(self.status_message)
        self.geolocate.measureModeRequested.connect(self._start_measuring)
        self.viewer.measurementComplete.connect(self._measurement_taken)
        self.viewer.landmarkPlaced.connect(self.geolocate.begin_landmark)

        self.tabs = QTabWidget(self)
        self.tabs.addTab(self.viewer, icon("open-file", colours["icon"]), tr("Details"))
        self.tabs.addTab(self.metadata, icon("report", colours["icon"]), "Metadata")
        self.tabs.addTab(self.forensics, icon("shield", colours["icon"]), tr("Forensics"))
        self.tabs.addTab(self.search, icon("web", colours["icon"]), tr("Reverse Search"))
        self.tabs.addTab(self.timeline, icon("timeline", colours["icon"]), tr("Timeline"))
        self.tabs.addTab(self.geolocate, icon("pin", colours["icon"]), "Geolocate")

        self.splitter = QSplitter(Qt.Horizontal, self)
        self.splitter.addWidget(left)
        self.splitter.addWidget(self.tabs)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 3)
        self.splitter.setSizes([460, 880])
        self.splitter.setChildrenCollapsible(False)

        self.setCentralWidget(self.splitter)

    def _build_actions(self) -> None:
        colours = theme.palette()

        def make(text, slot, shortcut=None, icon_name=None, tip=None, checkable=False):
            action = QAction(text, self)
            if icon_name:
                action.setIcon(icon(icon_name, colours["icon"]))
            if shortcut:
                action.setShortcut(QKeySequence(shortcut))
            if tip:
                action.setToolTip(tip)
                action.setStatusTip(tip)
            action.setCheckable(checkable)
            action.triggered.connect(slot)
            return action

        self.act_open_files = make(tr("Open Images…"), self.open_files, "Ctrl+O", "open-file")
        self.act_open_folder = make(tr("Open Folder…"), self.open_folder, "Ctrl+Shift+O", "open-folder")
        self.act_clear = make("Close All", self.clear_library, "Ctrl+W")
        self.act_remove = make("Remove Selected", self.remove_selected, "Del")
        self.act_exit = make(tr("Exit"), self.close, "Ctrl+Q")

        self.act_analyze = make(
            tr("Analyze"), self.analyze_pending, "F5", "analyze",
            tip="Analyse every image that has not been read yet",
        )
        self.act_reanalyze = make("Re-analyze Selected", self.reanalyze_selected, "Shift+F5", "refresh")
        # Scope is explicit: the library auto-selects the first image, so a
        # single "run forensics" action would silently shrink to one file.
        self.act_forensics = make(
            "Check All Images", self.run_forensics, "F6", "shield",
            tip="Compare every image with its embedded thumbnail",
        )
        self.act_forensics_selected = make(
            "Check Selected", self.run_forensics_selected, "Shift+F6", "shield",
            tip="Run the forensic checks on the selected images only",
        )
        self.act_compare = make(tr("Compare Selected"), self.compare_selected, "Ctrl+D", "compare")
        self.act_strip = make(tr("Strip Metadata"), self.strip_selected, "Ctrl+Shift+S", "strip")
        self.act_geotag = make(tr("Set Location…"), self.geotag_selected, "Ctrl+G", "pin")
        self.act_open_maps = make("Open in Maps", self.open_in_maps, "Ctrl+M", "map")
        self.act_cancel = make(tr("Cancel"), self.cancel_tasks, "Esc", "cancel")
        self.act_cancel.setEnabled(False)

        self.act_geolocate = make(
            "Geolocate", self.open_geolocate, "F7", "pin",
            tip="Combine shadows, metadata and landmarks to work out where a photo was taken",
        )
        self.act_measure_shadow = make(
            "Measure Shadow", lambda: self._start_measuring(MeasureMode.SHADOW), "F8", "analyze",
            tip="Click the object, its base and the shadow tip",
        )
        self.act_stop_measuring = make(
            "Stop Measuring", lambda: self._start_measuring(MeasureMode.NONE), "Shift+Esc",
        )
        self.act_report = make(tr("Export Report…"), self.export_report, "Ctrl+E", "report")
        self.act_report_selected = make("Export Selection…", lambda: self.export_report(True))
        self.act_custody = make(tr("Chain of Custody"), self.show_custody, "Ctrl+L", "custody")

        self.act_settings = make(tr("Settings"), self.show_settings, "Ctrl+,", "settings")
        self.act_about = make(tr("About"), self.show_about)
        self.act_updates = make(tr("Check for Updates…"), lambda: self.check_updates(False))
        self.act_search_online = make(
            tr("Reverse Search"), self._focus_search, "F9", "web",
            tip="Search the web for this image (needs an internet connection)",
        )

        self.act_zoom_in = make(tr("Zoom In"), lambda: self.viewer.canvas.zoom(1.25), "Ctrl+=", "zoom-in")
        self.act_zoom_out = make(tr("Zoom Out"), lambda: self.viewer.canvas.zoom(0.8), "Ctrl+-", "zoom-out")
        self.act_fit = make(tr("Fit to Window"), self.viewer.canvas.fit, "Ctrl+0", "fit")
        self.act_actual = make(tr("Actual Size"), self.viewer.canvas.actual_size, "Ctrl+1")

    def _build_menus(self) -> None:
        bar = self.menuBar()

        file_menu = bar.addMenu(tr("File"))
        file_menu.addAction(self.act_open_files)
        file_menu.addAction(self.act_open_folder)
        self.recent_menu = file_menu.addMenu(tr("Recent"))
        self._rebuild_recent_menu()
        file_menu.addSeparator()
        file_menu.addAction(self.act_report)
        file_menu.addAction(self.act_report_selected)
        file_menu.addSeparator()
        file_menu.addAction(self.act_clear)
        file_menu.addAction(self.act_exit)

        edit_menu = bar.addMenu(tr("Edit"))
        edit_menu.addAction(self.act_remove)
        edit_menu.addSeparator()
        edit_menu.addAction(self.act_settings)

        view_menu = bar.addMenu(tr("View"))
        view_menu.addAction(self.act_zoom_in)
        view_menu.addAction(self.act_zoom_out)
        view_menu.addAction(self.act_fit)
        view_menu.addAction(self.act_actual)
        view_menu.addSeparator()

        theme_menu = view_menu.addMenu("Theme")
        self.theme_group = QActionGroup(self)
        self.theme_group.setExclusive(True)
        current_theme = self.ui_settings.get("theme", "system")
        for label, value in ((tr("System"), "system"), (tr("Light"), "light"), (tr("Dark"), "dark")):
            action = QAction(label, self, checkable=True)
            action.setChecked(value == current_theme)
            action.triggered.connect(lambda _checked=False, v=value: self.set_theme(v))
            self.theme_group.addAction(action)
            theme_menu.addAction(action)

        language_menu = view_menu.addMenu(tr("Language"))
        self.language_group = QActionGroup(self)
        self.language_group.setExclusive(True)
        current_language = self.ui_settings.get("language", "system")
        system_action = QAction("System default", self, checkable=True)
        system_action.setChecked(current_language == "system")
        system_action.triggered.connect(lambda: self.set_ui_language("system"))
        self.language_group.addAction(system_action)
        language_menu.addAction(system_action)
        for code, name in available_languages():
            action = QAction(f"{name} ({code})", self, checkable=True)
            action.setChecked(code == current_language)
            action.triggered.connect(lambda _checked=False, c=code: self.set_ui_language(c))
            self.language_group.addAction(action)
            language_menu.addAction(action)

        tools_menu = bar.addMenu(tr("Tools"))
        tools_menu.addAction(self.act_analyze)
        tools_menu.addAction(self.act_reanalyze)
        tools_menu.addAction(self.act_forensics)
        tools_menu.addAction(self.act_forensics_selected)
        tools_menu.addSeparator()
        tools_menu.addAction(self.act_compare)
        tools_menu.addAction(self.act_geotag)
        tools_menu.addAction(self.act_strip)
        tools_menu.addAction(self.act_open_maps)
        tools_menu.addSeparator()
        tools_menu.addAction(self.act_search_online)
        tools_menu.addAction(self.act_geolocate)
        tools_menu.addAction(self.act_measure_shadow)
        tools_menu.addAction(self.act_stop_measuring)
        tools_menu.addSeparator()
        tools_menu.addAction(self.act_cancel)

        reports_menu = bar.addMenu(tr("Reports"))
        reports_menu.addAction(self.act_report)
        reports_menu.addAction(self.act_report_selected)
        reports_menu.addSeparator()
        reports_menu.addAction(self.act_custody)

        help_menu = bar.addMenu(tr("Help"))
        help_menu.addAction(self.act_updates)
        help_menu.addAction(self.act_about)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main", self)
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(19, 19))
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        for action in (
            self.act_open_files, self.act_open_folder, None,
            self.act_analyze, self.act_forensics, None,
            self.act_compare, self.act_geotag, self.act_strip, None,
            self.act_geolocate, self.act_report,
        ):
            toolbar.addSeparator() if action is None else toolbar.addAction(action)
        spacer = QWidget(self)
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)
        toolbar.addAction(self.act_settings)
        self.addToolBar(toolbar)
        self.toolbar = toolbar

    def _build_statusbar(self) -> None:
        bar = QStatusBar(self)
        self.status_label = QLabel(tr("Ready"), self)
        self.progress = QProgressBar(self)
        self.progress.setMaximumWidth(220)
        self.progress.setVisible(False)
        self.cancel_button = QPushButton(tr("Cancel"), self)
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self.cancel_tasks)

        self.network_status = NetworkStatusButton(self)
        self.network_status.stateChanged.connect(self._network_state_changed)

        bar.addWidget(self.status_label, 1)
        bar.addPermanentWidget(self.progress)
        bar.addPermanentWidget(self.cancel_button)
        bar.addPermanentWidget(self.network_status)
        self.setStatusBar(bar)

    # ------------------------------------------------------------------
    # opening images
    # ------------------------------------------------------------------
    def open_files(self) -> None:
        patterns = " ".join(f"*{ext}" for ext in IMAGE_EXTENSIONS)
        paths, _ = QFileDialog.getOpenFileNames(
            self, tr("Open Images…"),
            self.config.get("session", {}).get("last_folder", ""),
            f"Images ({patterns});;All files (*)",
        )
        if paths:
            for path in paths:
                config_module.remember_recent("file", path)
            self.add_paths(paths)

    def open_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, tr("Open Folder…"), self.config.get("session", {}).get("last_folder", "")
        )
        if not folder:
            return
        recursive = (
            QMessageBox.question(
                self, tr("Open Folder…"), "Include images in subfolders?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
            )
            == QMessageBox.Yes
        )
        images = [str(path) for path in find_images(folder, recursive=recursive)]
        if not images:
            self.status_message("No image files found in that folder.")
            return
        config_module.remember_recent("folder", folder)
        config_module.update_config(session={"last_folder": folder})
        self.config = config_module.load_config()
        self._rebuild_recent_menu()
        self.add_paths(images)

    def add_paths(self, paths: List[str]) -> None:
        fresh = self.model.add_paths(paths)
        if not fresh:
            self.status_message("Those images are already open.")
            return

        self.empty_hint.hide()
        self.grid.show()
        self._update_counts(self.model.rowCount())

        self.runner.start(ThumbnailWorker(fresh, self.model.thumbnail_size)).signals.result.connect(
            lambda pair: self.model.set_thumbnail(pair[0], pair[1])
        )

        if self.ui_settings.get("auto_analyze_on_open", True):
            self._start_analysis(fresh)
        else:
            self.status_message(f"{len(fresh)} image(s) added. Press F5 to analyse.")
        self._update_actions()

    def _start_analysis(self, paths: List[str]) -> None:
        if not paths:
            return
        geocode = bool(self.config.get("geocoding", {}).get("enabled", True))
        worker = AnalyzeWorker(paths, geocode=geocode, forensics=False)
        worker.signals.result.connect(self._record_ready)
        worker.signals.progress.connect(self._progress)
        worker.signals.failed.connect(self._analysis_failed)
        worker.signals.finished.connect(self._analysis_finished)
        worker.signals.cancelled.connect(lambda: self.status_message("Analysis cancelled."))
        worker.signals.error.connect(self._worker_error)
        self._analyze_worker = worker
        self.runner.start(worker)

    # ------------------------------------------------------------------
    # analysis callbacks
    # ------------------------------------------------------------------
    def _record_ready(self, metadata: Dict[str, Any]) -> None:
        self.model.set_record(metadata)
        if not self._current_path:
            self.grid.select_first()

    def _analysis_failed(self, path: str, message: str) -> None:
        self.model.set_failed(path, message)
        self.status_message(f"{Path(path).name}: {message}")

    def _analysis_finished(self, records) -> None:
        self.timeline.set_records(self.model.records())
        self._update_counts(self.model.rowCount())
        count = len(records or [])
        geotagged = len(self.model.geotagged())
        self.status_message(
            f"{tr('Done')} · {count} analysed · {geotagged} geotagged"
        )
        self._update_actions()
        if self._current_path:
            self._show_details(self._current_path)

    def _worker_error(self, trace: str) -> None:
        self.status_message(tr("Error"))
        QMessageBox.critical(self, tr("Error"), f"A background task failed:\n\n{trace}")

    def _progress(self, done: int, total: int, name: str) -> None:
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(done)
        if name:
            self.status_label.setText(f"{tr('Analyzing…')} {name}  ({done}/{total})")

    def _set_busy(self, busy: bool) -> None:
        self.progress.setVisible(busy)
        self.cancel_button.setVisible(busy)
        self.act_cancel.setEnabled(busy)
        if not busy:
            self.progress.reset()

    # ------------------------------------------------------------------
    # selection
    # ------------------------------------------------------------------
    def _selection_changed(self, paths: List[str]) -> None:
        self._current_path = paths[0] if paths else None
        self._update_actions()
        if self._current_path:
            self._show_details(self._current_path)
        else:
            self.viewer.clear()
            self.metadata.clear()
            self.forensics.clear()
            self.search.set_image(None)

    def _show_details(self, path: str) -> None:
        record = self.model.record(path)
        self.viewer.show_image(path, Path(path).name)
        self.metadata.set_metadata(record)
        self.forensics.set_image(path, (record or {}).get("forensics"))
        self.search.set_image(path)
        self.geolocate.set_record(record)

    def _timeline_bucket_clicked(self, label: str, records: List[Dict[str, Any]]) -> None:
        if records:
            self.grid.select_path(records[0].get("file", ""))
            self.status_message(f"{label}: {len(records)} image(s)")

    def selected_records(self) -> List[Dict[str, Any]]:
        records = [self.model.record(path) for path in self.grid.selected_paths()]
        return [record for record in records if record]

    # ------------------------------------------------------------------
    # tools
    # ------------------------------------------------------------------
    def analyze_pending(self) -> None:
        pending = self.model.pending()
        if not pending:
            self.status_message("Everything is already analysed.")
            return
        self._start_analysis(pending)

    def reanalyze_selected(self) -> None:
        paths = self.grid.selected_paths() or self.model.paths()
        if paths:
            self._start_analysis(paths)

    def run_forensics_selected(self) -> None:
        records = self.selected_records()
        if not records:
            self.status_message("Select one or more images first.")
            return
        self._run_forensics(records)

    def run_forensics(self) -> None:
        """Check every analysed image in the library."""
        self._run_forensics(self.model.records())

    def _run_forensics(self, records) -> None:
        if not records:
            self.status_message("Nothing to analyse.")
            return
        worker = ForensicsWorker(records)
        worker.signals.progress.connect(self._progress)
        worker.signals.finished.connect(self._forensics_finished)
        worker.signals.failed.connect(lambda path, msg: self.status_message(f"{Path(path).name}: {msg}"))
        worker.signals.error.connect(self._worker_error)
        self.runner.start(worker)
        self.status_message(f"Running forensics on {len(records)} image(s)…")

    def run_forensics_for(self, path: str) -> None:
        record = self.model.record(path)
        if record:
            worker = ForensicsWorker([record])
            worker.signals.finished.connect(self._forensics_finished)
            worker.signals.error.connect(self._worker_error)
            self.runner.start(worker)

    def _forensics_finished(self, reports: Dict[str, Dict[str, Any]]) -> None:
        flagged = 0
        for path, report in (reports or {}).items():
            record = self.model.record(path)
            if record is not None:
                record["forensics"] = report
                self.model.set_record(record)
            if report.get("flags"):
                flagged += 1
        self.timeline.set_records(self.model.records())
        self._update_counts(self.model.rowCount())
        if self._current_path:
            self._show_details(self._current_path)
        self.status_message(
            f"{tr('Forensics')}: {len(reports or {})} checked · {flagged} flagged"
        )

    def compare_selected(self) -> None:
        records = self.selected_records()
        if len(records) != 2:
            QMessageBox.information(
                self, tr("Compare"),
                "Select exactly two analysed images to compare "
                "(hold Ctrl while clicking).",
            )
            return
        CompareDialog(records[0], records[1], self).exec()

    def strip_selected(self) -> None:
        records = self.selected_records()
        if not records:
            self.status_message("Select one or more images first.")
            return

        privacy = self.config.get("privacy", {})
        overwrite = bool(privacy.get("overwrite", False))
        suffix = privacy.get("output_suffix", "_clean")

        if self.ui_settings.get("confirm_destructive", True):
            detail = (
                f"This will <b>overwrite the original {len(records)} file(s)</b>."
                if overwrite
                else f"This writes {len(records)} cleaned copy/copies using the "
                     f"suffix <code>{suffix}</code>."
            )
            answer = QMessageBox.question(
                self, tr("Strip Metadata"),
                f"{detail}<br><br>Continue?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return

        from ..privacy import strip_exif

        written, failures = [], []
        for record in records:
            try:
                destination, removed = strip_exif(record["file"], overwrite=overwrite)
                written.append(destination)
                custody.record(
                    "strip", destination,
                    {"source": record["file"], "tags_removed": removed, "overwrite": overwrite},
                )
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{Path(record['file']).name}: {exc}")

        if failures:
            QMessageBox.warning(
                self, tr("Warning"),
                "Some files could not be cleaned:\n\n" + "\n".join(failures[:10]),
            )
        if written:
            self.status_message(f"Stripped {len(written)} image(s).")
            if overwrite:
                self._start_analysis([str(path) for path in written])
            else:
                self.add_paths([str(path) for path in written])

    def geotag_selected(self) -> None:
        records = self.selected_records()
        if not records:
            self.status_message("Select one or more images first.")
            return
        dialog = GeotagDialog(records, self)
        if dialog.exec() == GeotagDialog.Accepted:
            touched = dialog.written or dialog.removed
            if touched:
                self._start_analysis(touched)
                self.status_message(f"Updated the location of {len(touched)} image(s).")

    def _focus_search(self) -> None:
        if not self._current_path:
            self.status_message("Select an analysed image first.")
            return
        self.tabs.setCurrentWidget(self.search)

    def open_geolocate(self) -> None:
        """Show the Evidence Board for the current image."""
        if not self._current_path:
            self.status_message("Select an analysed image first.")
            return
        self.tabs.setCurrentWidget(self.geolocate)
        self.geolocate.set_record(self.model.record(self._current_path))

    def _start_measuring(self, mode) -> None:
        """Switch the preview into a measuring mode and show it."""
        if not self._current_path:
            self.status_message("Open an image before measuring.")
            return
        self.viewer.set_measure_mode(mode)
        if mode is not MeasureMode.NONE:
            self.tabs.setCurrentWidget(self.viewer)
            self.status_message("Measuring: follow the prompt above the image.")
        else:
            self.status_message(tr("Ready"))

    def _measurement_taken(self, measurement) -> None:
        """A completed on-image measurement feeds straight into the board."""
        if measurement.mode is MeasureMode.SHADOW:
            self.geolocate.apply_shadow_measurement(measurement)
            self.tabs.setCurrentWidget(self.geolocate)
            self.geolocate.tools.setCurrentIndex(1)
            self.viewer.set_measure_mode(MeasureMode.NONE)
            self.status_message("Shadow measured; the Geolocate tab has the numbers.")

    def open_in_maps(self) -> None:
        records = self.selected_records()
        opened = 0
        for record in records[:5]:
            url = record.get("map_url")
            if url:
                QDesktopServices.openUrl(QUrl(url))
                opened += 1
        if not opened:
            self.status_message("No GPS coordinates in the selection.")

    def run_search(self, path: str, engine: str) -> None:
        worker = SearchWorker(path, engine)
        worker.signals.result.connect(self.search.show_result)
        worker.signals.failed.connect(lambda _path, message: self.search.show_error(message))
        worker.signals.error.connect(self._worker_error)
        self.runner.start(worker)
        self.status_message(f"Reverse searching with {engine}…")

    def cancel_tasks(self) -> None:
        self.runner.cancel_all()
        self.status_message("Cancelling…")

    # ------------------------------------------------------------------
    # reports and dialogs
    # ------------------------------------------------------------------
    def export_report(self, selection_only: bool = False) -> None:
        records = self.selected_records() if selection_only else self.model.records()
        if not records:
            QMessageBox.information(
                self, tr("Export"),
                "Analyse some images first — there is nothing to export yet.",
            )
            return
        dialog = ReportDialog(records, self, selected_only=selection_only)
        dialog.exported.connect(
            lambda fmt, path: self.status_message(f"{fmt.upper()} saved to {path}")
        )
        dialog.exec()

    def geolocation_summary(self) -> Dict[str, Any]:
        """What the Evidence Board currently concludes, for reports and logging."""
        return self.geolocate.report_data()

    def show_custody(self) -> None:
        CustodyDialog(self).exec()

    def show_settings(self) -> None:
        dialog = SettingsDialog(self)
        dialog.settingsChanged.connect(self._settings_changed)
        dialog.exec()

    def _settings_changed(self, payload: Dict[str, Any]) -> None:
        self.config = config_module.load_config()
        self.ui_settings = self.config.get("ui", {})
        self.set_theme(self.ui_settings.get("theme", "system"), persist=False)
        self.set_ui_language(self.ui_settings.get("language", "system"), persist=False)
        size = int(self.ui_settings.get("thumbnail_size", 160))
        self.model.set_thumbnail_size(size)
        self.grid.set_thumbnail_size(size)
        self.network_status.refresh()
        self.status_message("Settings saved.")

    def show_about(self) -> None:
        AboutDialog(self).exec()

    def check_updates(self, quiet: bool = False) -> None:
        from ..updates import check_for_updates

        def done(info) -> None:
            if info.available or not quiet:
                UpdateDialog(info, self).exec()
            elif info.error:
                self.status_message(info.message)

        from .workers import CallableWorker

        worker = CallableWorker(check_for_updates)
        worker.signals.result.connect(done)
        self.runner.start(worker)

    # ------------------------------------------------------------------
    # appearance
    # ------------------------------------------------------------------
    def set_theme(self, name: str, persist: bool = True) -> None:
        application = QApplication.instance()
        if application is not None:
            theme.apply(application, name)
        if persist:
            config_module.update_config(ui={"theme": name})
            self.config = config_module.load_config()
            self.ui_settings = self.config.get("ui", {})
        self._refresh_theme_dependent_widgets()

    def _refresh_theme_dependent_widgets(self) -> None:
        colours = theme.palette()
        for index, name in enumerate(
            ("open-file", "report", "shield", "web", "timeline", "pin")
        ):
            self.tabs.setTabIcon(index, icon(name, colours["icon"]))
        for action, name in (
            (self.act_open_files, "open-file"), (self.act_open_folder, "open-folder"),
            (self.act_analyze, "analyze"), (self.act_forensics, "shield"),
            (self.act_compare, "compare"), (self.act_geotag, "pin"),
            (self.act_strip, "strip"), (self.act_report, "report"),
            (self.act_settings, "settings"), (self.act_custody, "custody"),
            (self.act_cancel, "cancel"), (self.act_reanalyze, "refresh"),
            (self.act_forensics_selected, "shield"), (self.act_geolocate, "pin"),
            (self.act_measure_shadow, "analyze"), (self.act_search_online, "web"),
            (self.act_open_maps, "map"),
        ):
            action.setIcon(icon(name, colours["icon"]))
        self.library_count.setStyleSheet(f"color: {colours['text_muted']}; padding: 0 8px 6px;")
        if self._current_path:
            self._show_details(self._current_path)
        self.grid.view.viewport().update()

    def set_ui_language(self, code: str, persist: bool = True) -> None:
        resolved = set_language(code)
        if persist:
            config_module.update_config(ui={"language": code})
            self.config = config_module.load_config()
            self.ui_settings = self.config.get("ui", {})
        application = QApplication.instance()
        if application is not None:
            from ..i18n import is_rtl

            application.setLayoutDirection(Qt.RightToLeft if is_rtl(resolved) else Qt.LeftToRight)
        if persist:
            QMessageBox.information(
                self, tr("Language"),
                "The language has been changed. Restart PhotoSleuth to translate "
                "every part of the interface.",
            )

    # ------------------------------------------------------------------
    # library housekeeping
    # ------------------------------------------------------------------
    def remove_selected(self) -> None:
        paths = self.grid.selected_paths()
        if not paths:
            return
        self.model.remove_paths(paths)
        self._current_path = None
        self._selection_changed([])
        self.timeline.set_records(self.model.records())
        self._update_counts(self.model.rowCount())

    def clear_library(self) -> None:
        self.model.clear()
        self._current_path = None
        self._selection_changed([])
        self.timeline.set_records([])
        self.grid.hide()
        self.empty_hint.show()
        self._update_counts(0)

    def _update_counts(self, count: int) -> None:
        shown = self.proxy.rowCount()
        geotagged = len(self.model.geotagged())
        text = f"{count} {tr('images')}"
        if shown != count:
            text += f" · {shown} shown"
        if geotagged:
            text += f" · {geotagged} geotagged"
        self.library_count.setText(text)
        if count:
            self.empty_hint.hide()
            self.grid.show()
        else:
            self.grid.hide()
            self.empty_hint.show()
        self._update_actions()

    def _update_actions(self) -> None:
        has_images = self.model.rowCount() > 0
        selected = len(self.grid.selected_paths()) if has_images else 0
        analysed = bool(self.model.records())

        self.act_analyze.setEnabled(bool(self.model.pending()))
        self.act_reanalyze.setEnabled(has_images)
        self.act_forensics.setEnabled(analysed)
        self.act_forensics_selected.setEnabled(selected > 0)
        self.act_compare.setEnabled(selected == 2)
        self.act_strip.setEnabled(selected > 0)
        self.act_geotag.setEnabled(selected > 0)
        self.act_open_maps.setEnabled(selected > 0)
        self.act_remove.setEnabled(selected > 0)
        self.act_clear.setEnabled(has_images)
        self.act_report.setEnabled(analysed)
        self.act_report_selected.setEnabled(selected > 0)
        self.act_geolocate.setEnabled(bool(self._current_path))
        self.act_measure_shadow.setEnabled(bool(self._current_path))
        from .. import connectivity as net

        self.act_search_online.setEnabled(bool(self._current_path) and net.state().usable)

    def _network_state_changed(self, state) -> None:
        """Enable or disable the features that genuinely need a connection."""
        usable = state.usable
        for action, name in (
            (self.act_search_online, "Reverse image search"),
            (self.act_updates, "Checking for updates"),
        ):
            action.setEnabled(usable)
            action.setToolTip(
                "" if usable else
                f"{name} needs the internet. "
                + ("Offline mode is on." if state.blocked_by_choice else "No connection.")
            )
        if hasattr(self, "search"):
            self.search.set_online(state)

    def status_message(self, text: str) -> None:
        self.status_label.setText(text)

    # ------------------------------------------------------------------
    # recent files
    # ------------------------------------------------------------------
    def _rebuild_recent_menu(self) -> None:
        self.recent_menu.clear()
        files = config_module.recent("file")
        folders = config_module.recent("folder")

        if not files and not folders:
            empty = QAction("(nothing yet)", self)
            empty.setEnabled(False)
            self.recent_menu.addAction(empty)
            return

        for folder in folders[:8]:
            action = QAction(f"📁 {folder}", self)
            action.triggered.connect(lambda _checked=False, f=folder: self._open_recent_folder(f))
            self.recent_menu.addAction(action)
        if folders and files:
            self.recent_menu.addSeparator()
        for path in files[:8]:
            action = QAction(Path(path).name, self)
            action.setToolTip(path)
            action.triggered.connect(lambda _checked=False, p=path: self._open_recent_file(p))
            self.recent_menu.addAction(action)

        self.recent_menu.addSeparator()
        clear = QAction(tr("Clear Recent"), self)
        clear.triggered.connect(lambda: (config_module.clear_recent(), self._rebuild_recent_menu()))
        self.recent_menu.addAction(clear)

    def _open_recent_folder(self, folder: str) -> None:
        if not Path(folder).is_dir():
            self.status_message(f"Folder no longer exists: {folder}")
            return
        images = [str(path) for path in find_images(folder, recursive=True)]
        self.add_paths(images) if images else self.status_message("No images in that folder.")

    def _open_recent_file(self, path: str) -> None:
        if Path(path).is_file():
            self.add_paths([path])
        else:
            self.status_message(f"File no longer exists: {path}")

    # ------------------------------------------------------------------
    # session, drag-and-drop, shutdown
    # ------------------------------------------------------------------
    def _restore_session(self) -> None:
        if not self.ui_settings.get("restore_session", True):
            return
        session = self.config.get("session", {})
        geometry = session.get("window_geometry")
        if geometry:
            try:
                self.restoreGeometry(QByteArray.fromBase64(geometry.encode("ascii")))
            except Exception:
                pass
        sizes = session.get("splitter_sizes")
        if sizes and len(sizes) == 2:
            try:
                self.splitter.setSizes([int(value) for value in sizes])
            except (TypeError, ValueError):
                pass
        try:
            self.tabs.setCurrentIndex(int(session.get("last_tab", 0)))
        except (TypeError, ValueError):
            pass

    def _save_session(self) -> None:
        try:
            config_module.update_config(
                session={
                    "window_geometry": bytes(self.saveGeometry().toBase64()).decode("ascii"),
                    "splitter_sizes": list(self.splitter.sizes()),
                    "last_tab": self.tabs.currentIndex(),
                }
            )
        except OSError:
            pass

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths = collect_dropped_paths(event.mimeData())
        if paths:
            self.add_paths(paths)
            event.acceptProposedAction()

    def closeEvent(self, event) -> None:
        if self.runner.busy:
            answer = QMessageBox.question(
                self, tr("Close"),
                "A background task is still running. Cancel it and quit?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            self.runner.cancel_all()
            self.runner.wait(4000)

        self._save_session()
        event.accept()
