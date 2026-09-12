"""The Evidence Board tab: constraints on the left, map and candidates on the right.

This is the piece that makes several weak techniques worth more than the sum of
their parts. Each analyser contributes a constraint layer; the board fuses them
and shows both the answer and why it believes it.
"""

from __future__ import annotations

import math
from datetime import date as _date
from datetime import datetime, time as _time, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QDate, QDateTime, Qt, QTime, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...geolocation import exif_geo, photogrammetry, shadow as shadow_module, solar
from ...geolocation.constraints import (
    Candidate,
    Constraint,
    EvidenceBoard,
    ResectionConstraint,
    ViewCone,
)
from ...i18n import tr
from .. import theme
from ..resources import icon
from .map_widget import MapWidget
from .measure_overlay import MeasureMode


class EvidenceBoardPanel(QWidget):
    """Layer list, map, candidates and the analyser panels that feed them."""

    statusMessage = Signal(str)
    measureModeRequested = Signal(object)
    constraintsChanged = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.board = EvidenceBoard()
        self.record: Optional[Dict[str, Any]] = None
        self.candidates: List[Candidate] = []
        self.landmarks: List[Dict[str, Any]] = []
        self._pending_landmark_pixel: Optional[tuple] = None

        colours = theme.palette()

        # ---------------- left: layers and candidates ----------------
        self.layers = QTreeWidget(self)
        self.layers.setColumnCount(3)
        self.layers.setHeaderLabels(["Constraint", "Source", "Weight"])
        self.layers.setRootIsDecorated(False)
        self.layers.setAlternatingRowColors(True)
        self.layers.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.layers.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.layers.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.layers.itemChanged.connect(self._layer_toggled)
        self.layers.currentItemChanged.connect(self._layer_selected)

        remove_button = QPushButton("Remove", self)
        remove_button.clicked.connect(self.remove_selected_layer)
        clear_button = QPushButton("Clear all", self)
        clear_button.clicked.connect(self.clear_board)
        self.fuse_button = QPushButton("Fuse evidence", self)
        self.fuse_button.setProperty("accent", True)
        self.fuse_button.setIcon(icon("analyze", colours["accent_text"]))
        self.fuse_button.clicked.connect(self.fuse)

        layer_buttons = QHBoxLayout()
        layer_buttons.addWidget(remove_button)
        layer_buttons.addWidget(clear_button)
        layer_buttons.addStretch(1)
        layer_buttons.addWidget(self.fuse_button)

        self.candidate_list = QTreeWidget(self)
        self.candidate_list.setColumnCount(4)
        self.candidate_list.setHeaderLabels(["#", "Latitude", "Longitude", "Score"])
        self.candidate_list.setRootIsDecorated(False)
        self.candidate_list.setAlternatingRowColors(True)
        self.candidate_list.setSelectionMode(QAbstractItemView.SingleSelection)
        header = self.candidate_list.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.candidate_list.currentItemChanged.connect(self._candidate_selected)
        self.candidate_list.itemDoubleClicked.connect(self._open_candidate)

        self.explanation = QTextBrowser(self)
        self.explanation.setMinimumHeight(110)
        self._show_intro()

        left = QWidget(self)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.addWidget(QLabel("Constraint layers", self))
        left_layout.addWidget(self.layers, 3)
        left_layout.addLayout(layer_buttons)
        left_layout.addWidget(QLabel("Candidates", self))
        left_layout.addWidget(self.candidate_list, 2)
        left_layout.addWidget(self.explanation, 2)

        # ---------------- right: map plus analyser tabs ----------------
        self.map = MapWidget(self)
        self.map.clicked.connect(self._map_clicked)

        self.tools = QTabWidget(self)
        self.tools.addTab(self._metadata_tab(), "Metadata")
        self.tools.addTab(self._shadow_tab(), "Shadow")
        self.tools.addTab(self._resection_tab(), "Landmarks")
        self.tools.setMaximumHeight(290)

        right = QSplitter(Qt.Vertical, self)
        right.addWidget(self.map)
        right.addWidget(self.tools)
        right.setStretchFactor(0, 3)
        right.setStretchFactor(1, 1)

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 5)
        splitter.setChildrenCollapsible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        # Establish the empty state: nothing to fuse until evidence is added.
        self._refresh_layers()

    # ------------------------------------------------------------------
    # analyser tabs
    # ------------------------------------------------------------------
    def _metadata_tab(self) -> QWidget:
        page = QWidget(self)
        self.metadata_report = QTextBrowser(page)
        self.metadata_report.setOpenExternalLinks(False)

        run = QPushButton("Read metadata evidence", page)
        run.setToolTip(
            "Time-zone consistency, GPS quality and the camera's bearing - "
            "all offline, all instant."
        )
        run.clicked.connect(self.run_metadata_checks)

        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(run)
        layout.addWidget(self.metadata_report, 1)
        return page

    def _shadow_tab(self) -> QWidget:
        page = QWidget(self)
        colours = theme.palette()

        self.shadow_status = QLabel(
            "Choose “Measure shadow” and click three points on the photo: "
            "the top of the object, its base, then the tip of its shadow.", page
        )
        self.shadow_status.setWordWrap(True)
        self.shadow_status.setStyleSheet(f"color: {colours['text_muted']};")

        measure = QPushButton("Measure shadow on photo", page)
        measure.setIcon(icon("analyze", colours["icon"]))
        measure.clicked.connect(lambda: self.measureModeRequested.emit(MeasureMode.SHADOW))

        self.shadow_object = QDoubleSpinBox(page)
        self.shadow_object.setRange(0.001, 100000.0)
        self.shadow_object.setDecimals(2)
        self.shadow_object.setValue(100.0)
        self.shadow_shadow = QDoubleSpinBox(page)
        self.shadow_shadow.setRange(0.0, 100000.0)
        self.shadow_shadow.setDecimals(2)
        self.shadow_shadow.setValue(100.0)
        for box in (self.shadow_object, self.shadow_shadow):
            box.valueChanged.connect(self._update_shadow_readout)

        self.shadow_when = QDateTimeEdit(QDateTime.currentDateTimeUtc(), page)
        self.shadow_when.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.shadow_when.setCalendarPopup(True)
        self.shadow_when.setToolTip("The capture time in UTC.")

        self.shadow_elevation = QLabel("—", page)
        font = self.shadow_elevation.font()
        font.setBold(True)
        self.shadow_elevation.setFont(font)

        verify = QPushButton("Verify against best candidate", page)
        verify.clicked.connect(self.verify_shadow)
        add = QPushButton("Add to board", page)
        add.setProperty("accent", True)
        add.clicked.connect(self.add_shadow_constraint)
        times = QPushButton("What time was it?", page)
        times.clicked.connect(self.shadow_time_of_day)

        buttons = QHBoxLayout()
        buttons.addWidget(add)
        buttons.addWidget(verify)
        buttons.addWidget(times)
        buttons.addStretch(1)

        form = QFormLayout()
        form.addRow("Object length (px)", self.shadow_object)
        form.addRow("Shadow length (px)", self.shadow_shadow)
        form.addRow("Captured (UTC)", self.shadow_when)
        form.addRow("Sun elevation", self.shadow_elevation)

        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(measure)
        layout.addWidget(self.shadow_status)
        layout.addLayout(form)
        layout.addLayout(buttons)
        self._update_shadow_readout()
        return page

    def _resection_tab(self) -> QWidget:
        page = QWidget(self)
        colours = theme.palette()

        self.resection_status = QLabel(
            "Click “Mark landmark on photo”, click the landmark in the picture, "
            "then click the same spot on the map. Three landmarks fix the camera.",
            page,
        )
        self.resection_status.setWordWrap(True)
        self.resection_status.setStyleSheet(f"color: {colours['text_muted']};")

        mark = QPushButton("Mark landmark on photo", page)
        mark.setIcon(icon("pin", colours["icon"]))
        mark.clicked.connect(lambda: self.measureModeRequested.emit(MeasureMode.LANDMARK))

        self.landmark_list = QTreeWidget(page)
        self.landmark_list.setColumnCount(3)
        self.landmark_list.setHeaderLabels(["Landmark", "Image x,y", "Map lat,lon"])
        self.landmark_list.setRootIsDecorated(False)
        self.landmark_list.setMaximumHeight(110)

        solve = QPushButton("Solve position", page)
        solve.setProperty("accent", True)
        solve.clicked.connect(self.solve_resection)
        clear = QPushButton("Clear landmarks", page)
        clear.clicked.connect(self.clear_landmarks)

        buttons = QHBoxLayout()
        buttons.addWidget(solve)
        buttons.addWidget(clear)
        buttons.addStretch(1)

        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(mark)
        layout.addWidget(self.resection_status)
        layout.addWidget(self.landmark_list, 1)
        layout.addLayout(buttons)
        return page

    # ------------------------------------------------------------------
    # image binding
    # ------------------------------------------------------------------
    def set_record(self, record: Optional[Dict[str, Any]]) -> None:
        self.record = record
        if not record:
            return

        gps = record.get("gps") or {}
        if gps:
            self.map.set_centre(gps["latitude"], gps["longitude"], 13)

        moment = exif_geo.gps_datetime(record) or exif_geo.local_datetime(record)
        if moment:
            self.shadow_when.setDateTime(
                QDateTime(QDate(moment.year, moment.month, moment.day),
                          QTime(moment.hour, moment.minute))
            )
        self._show_intro()

    # ------------------------------------------------------------------
    # metadata analysers (features 1, 2, 4, 5, 15)
    # ------------------------------------------------------------------
    def run_metadata_checks(self) -> None:
        if not self.record:
            self.statusMessage.emit("Select an analysed image first.")
            return

        report = exif_geo.analyze(self.record)
        colours = theme.palette()

        def row(title: str, verdict: str, message: str, tone: str) -> str:
            return (
                f"<p style='margin:4px 0'><b>{title}:</b> "
                f"<span style='color:{colours[tone]}'>{verdict}</span><br>"
                f"<span style='color:{colours['text_muted']}'>{message}</span></p>"
            )

        timezone_info = report["timezone"]
        tone = {"consistent": "success", "questionable": "warning",
                "inconsistent": "danger"}.get(timezone_info["verdict"], "text_muted")
        html = [row("Time zone", timezone_info["verdict"].title(), timezone_info["message"], tone)]

        quality = report["gps_quality"]
        html.append(row(
            "GPS quality", quality["confidence"].title(), quality["message"],
            {"high": "success", "medium": "text_muted"}.get(quality["confidence"], "warning"),
        ))
        html.append(row("Direction", "", report["direction"]["message"], "text_muted"))
        if report["lens"]:
            lens = report["lens"]
            html.append(row(
                "Lens", f"{lens['horizontal_fov']:.0f}° horizontal",
                f"{lens['focal_mm']} mm, {lens['source']}. "
                f"Focal length in pixels: {lens['focal_pixels']:.0f}.",
                "text_muted",
            ))

        self.metadata_report.setHtml(f"<div style='color:{colours['text']}'>{''.join(html)}</div>")

        added = 0
        for constraint in report["constraints"]:
            self.board.add(constraint)
            added += 1
        self._refresh_layers()

        cones = [
            {"latitude": c.latitude, "longitude": c.longitude, "bearing": c.bearing,
             "half_angle": c.half_angle, "max_km": c.max_km}
            for c in self.board.constraints if isinstance(c, ViewCone)
        ]
        self.map.set_cones(cones)

        self.statusMessage.emit(
            f"Metadata evidence: {added} constraint(s) added"
            + (f" · {len(report['warnings'])} warning(s)" if report["warnings"] else "")
        )
        if report["warnings"]:
            QMessageBox.warning(self, tr("Warning"), "\n\n".join(report["warnings"]))

    # ------------------------------------------------------------------
    # shadow analysers (features 6-10)
    # ------------------------------------------------------------------
    def apply_shadow_measurement(self, measurement) -> None:
        """Fill the shadow form from three clicks on the photograph."""
        observation = measurement.shadow_observation()
        if observation is None:
            return
        self.shadow_object.setValue(observation.object_length)
        self.shadow_shadow.setValue(observation.shadow_length)
        self._image_shadow_azimuth = observation.shadow_azimuth_image
        self.shadow_status.setText(
            f"Measured from the photo: object {observation.object_length:.0f} px, "
            f"shadow {observation.shadow_length:.0f} px, "
            f"pointing {observation.shadow_azimuth_image:.0f}° in image space."
        )
        self._update_shadow_readout()

    def current_observation(self):
        return shadow_module.ShadowObservation(
            object_length=max(self.shadow_object.value(), 1e-6),
            shadow_length=self.shadow_shadow.value(),
            shadow_azimuth_image=getattr(self, "_image_shadow_azimuth", None),
        )

    def _update_shadow_readout(self) -> None:
        observation = self.current_observation()
        uncertainty = shadow_module.elevation_uncertainty(observation)
        self.shadow_elevation.setText(
            f"{observation.elevation:.2f}° ± {uncertainty:.2f}°   "
            f"(shadow is {observation.ratio:.2f}× the height)"
        )

    def shadow_moment(self) -> datetime:
        value = self.shadow_when.dateTime().toPython()
        return value.replace(tzinfo=timezone.utc)

    def add_shadow_constraint(self) -> None:
        observation = self.current_observation()
        built = shadow_module.constraints(observation, moment=self.shadow_moment())
        for constraint in built:
            self.board.add(constraint)
        self._refresh_layers()
        self.statusMessage.emit(
            f"Added a sun-elevation constraint at {observation.elevation:.1f}°."
        )

    def verify_shadow(self) -> None:
        target = self._reference_point()
        if target is None:
            self.statusMessage.emit("No candidate or GPS position to verify against.")
            return
        latitude, longitude = target
        result = shadow_module.verify(
            self.current_observation(), latitude, longitude, self.shadow_moment()
        )
        colours = theme.palette()
        tone = colours["success"] if result["consistent"] else colours["danger"]
        self.explanation.setHtml(
            f"<div style='color:{colours['text']}'>"
            f"<p style='color:{tone}'><b>"
            f"{'Consistent' if result['consistent'] else 'Inconsistent'}</b></p>"
            f"<p>{result['reason']}</p>"
            f"<table><tr><td style='padding-right:14px'>Measured elevation</td>"
            f"<td>{result['measured_elevation']}°</td></tr>"
            f"<tr><td>Expected at this place</td><td>{result['expected_elevation']}°</td></tr>"
            f"<tr><td>Expected shadow bearing</td>"
            f"<td>{result['expected_shadow_azimuth']}°</td></tr></table></div>"
        )
        self.statusMessage.emit(result["reason"][:120])

    def shadow_time_of_day(self) -> None:
        target = self._reference_point()
        if target is None:
            self.statusMessage.emit("Pick a candidate location first.")
            return
        latitude, longitude = target
        moment = self.shadow_moment()
        result = shadow_module.time_of_day(
            self.current_observation(), latitude, longitude, moment.date()
        )
        colours = theme.palette()
        rows = "".join(
            f"<tr><td style='padding-right:14px'>{entry['utc']:%H:%M} UTC</td>"
            f"<td>{'morning' if entry['is_morning'] else 'afternoon'}</td>"
            f"<td>shadow points {entry['shadow_azimuth']:.0f}°</td></tr>"
            for entry in result["matches"]
        )
        self.explanation.setHtml(
            f"<div style='color:{colours['text']}'><p>{result['message']}</p>"
            f"<table>{rows}</table></div>"
        )

    def north_arrow(self) -> Optional[Dict[str, Any]]:
        target = self._reference_point()
        observation = self.current_observation()
        if target is None or observation.shadow_azimuth_image is None:
            return None
        try:
            return shadow_module.north_from_shadow(
                observation, target[0], target[1], self.shadow_moment()
            )
        except ValueError:
            return None

    # ------------------------------------------------------------------
    # resection (feature 14)
    # ------------------------------------------------------------------
    def begin_landmark(self, x: float, y: float) -> None:
        """A landmark was clicked on the photo; next map click pairs with it."""
        self._pending_landmark_pixel = (x, y)
        self.tools.setCurrentIndex(2)
        self.resection_status.setText(
            f"Landmark at image ({x:.0f}, {y:.0f}). Now click the same place on the map."
        )

    def _map_clicked(self, latitude: float, longitude: float) -> None:
        if self._pending_landmark_pixel is None:
            self.statusMessage.emit(f"Map: {latitude:.5f}, {longitude:.5f}")
            return

        x, y = self._pending_landmark_pixel
        self._pending_landmark_pixel = None
        self.landmarks.append({
            "pixel": (x, y),
            "latitude": latitude,
            "longitude": longitude,
            "name": f"L{len(self.landmarks) + 1}",
        })
        self._refresh_landmarks()
        self.resection_status.setText(
            f"{len(self.landmarks)} landmark(s) paired. Three are needed to solve a position."
        )

    def _refresh_landmarks(self) -> None:
        self.landmark_list.clear()
        for entry in self.landmarks:
            QTreeWidgetItem(self.landmark_list, [
                entry["name"],
                f"{entry['pixel'][0]:.0f}, {entry['pixel'][1]:.0f}",
                f"{entry['latitude']:.5f}, {entry['longitude']:.5f}",
            ])
        self.map.set_markers([
            {"latitude": e["latitude"], "longitude": e["longitude"],
             "label": e["name"], "colour": theme.palette()["warning"]}
            for e in self.landmarks
        ])

    def clear_landmarks(self) -> None:
        self.landmarks.clear()
        self._pending_landmark_pixel = None
        self._refresh_landmarks()
        self.resection_status.setText("Landmarks cleared.")

    def solve_resection(self) -> None:
        if len(self.landmarks) < 3:
            self.statusMessage.emit("Three paired landmarks are needed to solve a position.")
            return
        if not self.record:
            self.statusMessage.emit("Select an analysed image first.")
            return

        lens = photogrammetry.lens_from_metadata(self.record)
        if lens is None:
            QMessageBox.information(
                self, "Lens unknown",
                "The angles between landmarks are computed from the lens field of view, "
                "which this file does not record. Without a focal length the image "
                "cannot be turned into angles.",
            )
            return

        pixels = [entry["pixel"] for entry in self.landmarks]
        angles = [
            photogrammetry.angle_between_pixels(pixels[index], pixels[index + 1], lens)
            for index in range(len(pixels) - 1)
        ]
        points = [(e["latitude"], e["longitude"]) for e in self.landmarks]

        solution = photogrammetry.resect(points, angles)
        if solution is None:
            QMessageBox.warning(
                self, tr("Warning"),
                "Those angles have no solution. Landmarks lying almost in a straight "
                "line, or nearly on a circle through the camera, make the geometry "
                "degenerate - try a wider spread.",
            )
            return

        constraint = ResectionConstraint(
            source="resection",
            label=f"{len(points)} landmarks",
            detail=(
                f"Angles of {', '.join(f'{a:.1f}°' for a in angles)} between the marked "
                f"landmarks put the camera at {solution.latitude:.5f}, "
                f"{solution.longitude:.5f} (residual {solution.residual_deg:.3f}°)."
            ),
            landmarks=points,
            angles=angles,
            tolerance=max(0.3, solution.residual_deg * 3.0),
        )
        self.board.add(constraint)
        self._refresh_layers()
        self.map.set_centre(solution.latitude, solution.longitude, 15)
        self.statusMessage.emit(
            f"Resection: {solution.latitude:.5f}, {solution.longitude:.5f} "
            f"(residual {solution.residual_deg:.3f}°)"
        )
        self.fuse()

    # ------------------------------------------------------------------
    # board management
    # ------------------------------------------------------------------
    def add_constraint(self, constraint: Constraint) -> None:
        self.board.add(constraint)
        self._refresh_layers()

    def _refresh_layers(self) -> None:
        self.layers.blockSignals(True)
        self.layers.clear()
        for constraint in self.board.constraints:
            item = QTreeWidgetItem(self.layers, [
                constraint.label or type(constraint).__name__,
                constraint.source,
                f"{constraint.weight:.1f}",
            ])
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(0, Qt.Checked if constraint.enabled else Qt.Unchecked)
            item.setData(0, Qt.UserRole, constraint.identifier)
            item.setToolTip(0, constraint.describe())
        self.layers.blockSignals(False)
        self.fuse_button.setEnabled(bool(self.board.active))
        self.constraintsChanged.emit()

    def _layer_toggled(self, item: QTreeWidgetItem, column: int) -> None:
        if column != 0:
            return
        constraint = self.board.get(item.data(0, Qt.UserRole))
        if constraint is not None:
            constraint.enabled = item.checkState(0) == Qt.Checked
            self.fuse_button.setEnabled(bool(self.board.active))

    def _layer_selected(self, item: Optional[QTreeWidgetItem], _previous) -> None:
        if item is None:
            return
        constraint = self.board.get(item.data(0, Qt.UserRole))
        if constraint is None:
            return
        colours = theme.palette()
        self.explanation.setHtml(
            f"<div style='color:{colours['text']}'>"
            f"<p><b>{constraint.label or type(constraint).__name__}</b> "
            f"<span style='color:{colours['text_muted']}'>({constraint.source})</span></p>"
            f"<p style='color:{colours['text_muted']}'>{constraint.describe()}</p></div>"
        )

    def remove_selected_layer(self) -> None:
        item = self.layers.currentItem()
        if item is None:
            return
        self.board.remove(item.data(0, Qt.UserRole))
        self._refresh_layers()

    def clear_board(self) -> None:
        self.board.clear()
        self.candidates = []
        self.landmarks.clear()
        self._refresh_layers()
        self._refresh_landmarks()
        self.candidate_list.clear()
        self.map.clear_overlays()
        self._show_intro()

    # ------------------------------------------------------------------
    # fusion
    # ------------------------------------------------------------------
    def fuse(self) -> None:
        if not self.board.active:
            self.statusMessage.emit("Add at least one constraint first.")
            return

        self.candidates = self.board.candidates(count=5)
        self.candidate_list.clear()
        for candidate in self.candidates:
            item = QTreeWidgetItem(self.candidate_list, [
                str(candidate.rank),
                f"{candidate.latitude:.5f}",
                f"{candidate.longitude:.5f}",
                f"{candidate.score:.3f}",
            ])
            item.setData(0, Qt.UserRole, candidate)
            if candidate.score < 0.4:
                item.setForeground(3, QColor(theme.palette()["warning"]))

        self.map.set_candidates(self.candidates)

        if self.candidates:
            best = self.candidates[0]
            window = self.board.search_window()
            span = 0.3 if window is None else max(window[1] - window[0], 0.02)
            grid = self.board.fuse(
                (best.latitude - span, best.latitude + span,
                 best.longitude - span, best.longitude + span),
                rows=160, cols=160,
            )
            self.map.set_heatmap(grid if grid.has_signal else None)
            self.map.fit_bounds(
                best.latitude - span / 2, best.latitude + span / 2,
                best.longitude - span / 2, best.longitude + span / 2,
            )
            self.candidate_list.setCurrentItem(self.candidate_list.topLevelItem(0))
            self.statusMessage.emit(
                f"Best estimate {best.latitude:.5f}, {best.longitude:.5f} "
                f"(confidence {best.score:.2f} from {len(self.board.active)} constraints)"
            )
        else:
            self.statusMessage.emit("The constraints do not agree on any location.")

    def _candidate_selected(self, item: Optional[QTreeWidgetItem], _previous) -> None:
        if item is None:
            return
        candidate = item.data(0, Qt.UserRole)
        if candidate is None:
            return
        self._explain(candidate)

    def _explain(self, candidate: Candidate) -> None:
        colours = theme.palette()
        rows = []
        for entry in self.board.explain(candidate.latitude, candidate.longitude):
            if not entry["enabled"]:
                continue
            score = entry["score"]
            tone = colours["success"] if score > 0.7 else (
                colours["warning"] if score > 0.25 else colours["danger"]
            )
            rows.append(
                f"<tr><td style='padding-right:12px'>{entry['label']}</td>"
                f"<td style='color:{colours['text_muted']};padding-right:12px'>{entry['source']}</td>"
                f"<td style='color:{tone}'><b>{score:.3f}</b></td></tr>"
            )

        verdict = (
            "All constraints agree here."
            if all(
                (e["score"] or 0) > 0.6
                for e in self.board.explain(candidate.latitude, candidate.longitude)
                if e["enabled"]
            )
            else "Some constraints disagree - the low scores below say which."
        )
        self.explanation.setHtml(
            f"<div style='color:{colours['text']}'>"
            f"<p><b>Candidate {candidate.rank}</b> — {candidate.latitude:.5f}, "
            f"{candidate.longitude:.5f} · confidence {candidate.score:.3f}</p>"
            f"<p style='color:{colours['text_muted']}'>{verdict}</p>"
            f"<table>{''.join(rows)}</table>"
            f"<p style='color:{colours['text_muted']}'>Double-click a candidate to open it "
            f"in a map in your browser.</p></div>"
        )

    def _open_candidate(self, item: QTreeWidgetItem, _column: int) -> None:
        candidate = item.data(0, Qt.UserRole)
        if candidate is not None:
            QDesktopServices.openUrl(QUrl(candidate.map_url))

    def _reference_point(self):
        if self.candidates:
            return self.candidates[0].latitude, self.candidates[0].longitude
        gps = (self.record or {}).get("gps") or {}
        if gps:
            return gps["latitude"], gps["longitude"]
        return None

    def _show_intro(self) -> None:
        colours = theme.palette()
        self.explanation.setHtml(
            f"<div style='color:{colours['text_muted']}'>"
            "<p>No single technique locates a photograph. Each one below rules territory "
            "<i>out</i>; where several agree is where the picture was taken.</p>"
            "<p><b>Metadata</b> checks the clock against the coordinates. "
            "<b>Shadow</b> turns a shadow into the sun's height, which only happens in "
            "certain places at a given moment. <b>Landmarks</b> fix the camera exactly "
            "when three known points are visible.</p>"
            "<p>Add constraints, press <b>Fuse evidence</b>, and read the per-constraint "
            "scores to see which evidence supports the answer and which fights it.</p>"
            "</div>"
        )

    def report_data(self) -> Dict[str, Any]:
        """Everything the board knows, for the chain-of-custody log and reports."""
        return {
            "constraints": self.board.to_dict()["constraints"],
            "candidates": [c.to_dict() for c in self.candidates],
            "landmarks": [
                {"name": e["name"], "latitude": e["latitude"], "longitude": e["longitude"]}
                for e in self.landmarks
            ],
        }
