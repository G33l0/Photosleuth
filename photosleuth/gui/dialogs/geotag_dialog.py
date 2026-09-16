"""Manual geotagging (feature B10).

Pin-dropping needs a map, and this build deliberately ships no embedded map
widget, so coordinates are entered directly: typed, pasted from a Google Maps
link, copied from another photo, or looked up from a place name.  A preview
link opens the exact spot in the user's browser before anything is written.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ...i18n import tr
from .. import theme
from ..resources import app_icon, icon


class GeotagDialog(QDialog):
    """Set or clear the GPS coordinates on one or more images."""

    def __init__(self, records: List[Dict[str, Any]], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Set Location…"))
        self.setWindowIcon(app_icon())
        self.records = list(records)
        self.resize(520, 0)
        colours = theme.palette()

        target = (
            Path(self.records[0]["file"]).name
            if len(self.records) == 1
            else f"{len(self.records)} images"
        )
        heading = QLabel(f"Writing GPS coordinates to <b>{target}</b>", self)
        heading.setWordWrap(True)

        # --- coordinate entry ------------------------------------------
        self.latitude = QDoubleSpinBox(self)
        self.latitude.setRange(-90.0, 90.0)
        self.latitude.setDecimals(6)
        self.latitude.setSingleStep(0.0001)

        self.longitude = QDoubleSpinBox(self)
        self.longitude.setRange(-180.0, 180.0)
        self.longitude.setDecimals(6)
        self.longitude.setSingleStep(0.0001)

        self.altitude = QDoubleSpinBox(self)
        self.altitude.setRange(-11000.0, 30000.0)
        self.altitude.setDecimals(1)
        self.altitude.setSuffix(" m")
        self.altitude.setSpecialValueText("—")
        self.altitude.setValue(self.altitude.minimum())

        self.paste_box = QLineEdit(self)
        self.paste_box.setPlaceholderText(
            "Paste \"48.8584, 2.2945\", 48°51'30\"N 2°17'40\"E, or a Google Maps link"
        )
        self.paste_box.returnPressed.connect(self._apply_pasted)
        paste_button = QPushButton("Use", self)
        paste_button.clicked.connect(self._apply_pasted)

        paste_row = QHBoxLayout()
        paste_row.addWidget(self.paste_box, 1)
        paste_row.addWidget(paste_button)

        self.place_box = QLineEdit(self)
        self.place_box.setPlaceholderText("…or search a place name (uses OpenStreetMap)")
        self.place_box.returnPressed.connect(self._lookup_place)
        lookup_button = QPushButton("Look up", self)
        lookup_button.clicked.connect(self._lookup_place)

        place_row = QHBoxLayout()
        place_row.addWidget(self.place_box, 1)
        place_row.addWidget(lookup_button)

        # --- copy from an already-geotagged image -----------------------
        self.copy_box = QComboBox(self)
        self.copy_box.addItem("—", None)
        copy_button = QPushButton("Copy", self)
        copy_button.clicked.connect(self._copy_from_selected)
        copy_row = QHBoxLayout()
        copy_row.addWidget(self.copy_box, 1)
        copy_row.addWidget(copy_button)

        form = QFormLayout()
        form.addRow(tr("Latitude"), self.latitude)
        form.addRow(tr("Longitude"), self.longitude)
        form.addRow(tr("Altitude"), self.altitude)
        form.addRow("Paste", paste_row)
        form.addRow("Place", place_row)
        form.addRow("Copy from", copy_row)

        entry_group = QGroupBox(tr("Location"), self)
        entry_group.setLayout(form)

        # --- options ----------------------------------------------------
        self.backup_check = QCheckBox("Keep a .bak copy of each original", self)
        self.backup_check.setChecked(True)

        self.preview_button = QPushButton("Preview on map", self)
        self.preview_button.setIcon(icon("map", colours["icon"]))
        self.preview_button.clicked.connect(self._preview)

        self.remove_button = QPushButton("Remove GPS instead", self)
        self.remove_button.setToolTip("Strip only the GPS block, keeping the rest of the EXIF")
        self.remove_button.clicked.connect(self._remove)

        options = QHBoxLayout()
        options.addWidget(self.preview_button)
        options.addWidget(self.remove_button)
        options.addStretch(1)

        self.status = QLabel("", self)
        self.status.setWordWrap(True)
        self.status.setStyleSheet(f"color: {colours['text_muted']};")

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.buttons.button(QDialogButtonBox.Ok).setText(tr("Apply"))
        self.buttons.button(QDialogButtonBox.Ok).setProperty("accent", True)
        self.buttons.accepted.connect(self._write)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(entry_group)
        layout.addLayout(options)
        layout.addWidget(self.backup_check)
        layout.addWidget(self.status)
        layout.addWidget(self.buttons)

        self.written: List[str] = []
        self.removed: List[str] = []
        self._seed()

    # -- seeding -----------------------------------------------------------
    def _seed(self) -> None:
        first_gps = None
        for record in self.records:
            gps = record.get("gps")
            if gps and first_gps is None:
                first_gps = gps
        if first_gps:
            self.latitude.setValue(first_gps["latitude"])
            self.longitude.setValue(first_gps["longitude"])
            if first_gps.get("altitude_m") is not None:
                self.altitude.setValue(float(first_gps["altitude_m"]))

        parent = self.parent()
        library = getattr(parent, "model", None)
        if library is not None:
            for record in library.geotagged():
                gps = record["gps"]
                self.copy_box.addItem(
                    f"{record.get('name', '')} ({gps['latitude']:.4f}, {gps['longitude']:.4f})",
                    (gps["latitude"], gps["longitude"], gps.get("altitude_m")),
                )

    # -- helpers -----------------------------------------------------------
    def coordinates(self):
        altitude = None
        if self.altitude.value() > self.altitude.minimum():
            altitude = self.altitude.value()
        return self.latitude.value(), self.longitude.value(), altitude

    def _apply_pasted(self) -> None:
        from ...geotag import parse_coordinate_text

        try:
            latitude, longitude = parse_coordinate_text(self.paste_box.text())
        except ValueError as exc:
            self.status.setText(f"⚠ {exc}")
            return
        self.latitude.setValue(latitude)
        self.longitude.setValue(longitude)
        self.status.setText(f"Read {latitude:.6f}, {longitude:.6f}")

    def _copy_from_selected(self) -> None:
        data = self.copy_box.currentData()
        if not data:
            return
        latitude, longitude, altitude = data
        self.latitude.setValue(latitude)
        self.longitude.setValue(longitude)
        if altitude is not None:
            self.altitude.setValue(float(altitude))
        self.status.setText("Copied coordinates from the selected image.")

    def _lookup_place(self) -> None:
        query = self.place_box.text().strip()
        if not query:
            return

        from ...connectivity import state as network_state

        current = network_state()
        if not current.usable:
            self.status.setText(
                "⚠ Place search needs the internet. "
                + ("Offline mode is on." if current.blocked_by_choice else "No connection.")
                + " You can still type or paste coordinates."
            )
            return

        self.status.setText("Looking up…")
        try:
            from geopy.geocoders import Nominatim

            from ...core import _geocoding_settings
            from ...utils import RateLimiter

            settings = _geocoding_settings()
            RateLimiter(float(settings["min_delay_seconds"])).wait()
            locator = Nominatim(
                user_agent=str(settings["user_agent"]), timeout=int(settings["timeout_seconds"])
            )
            location = locator.geocode(query)
        except Exception as exc:  # noqa: BLE001 - offline is a normal case
            self.status.setText(f"⚠ Lookup failed: {exc}")
            return
        if not location:
            self.status.setText("⚠ No match for that place.")
            return
        self.latitude.setValue(location.latitude)
        self.longitude.setValue(location.longitude)
        self.status.setText(f"Found: {location.address[:120]}")

    def _preview(self) -> None:
        latitude, longitude, _ = self.coordinates()
        QDesktopServices.openUrl(
            QUrl(f"https://www.openstreetmap.org/?mlat={latitude:.6f}&mlon={longitude:.6f}"
                 f"#map=16/{latitude:.6f}/{longitude:.6f}")
        )

    # -- actions -----------------------------------------------------------
    def _write(self) -> None:
        from ... import custody
        from ...geotag import write_gps

        latitude, longitude, altitude = self.coordinates()
        backup = self.backup_check.isChecked()
        failures = []
        self.written = []

        for record in self.records:
            path = record.get("file")
            try:
                write_gps(path, latitude, longitude, altitude=altitude, backup=backup)
                self.written.append(path)
                custody.record(
                    "geotag", path,
                    {"latitude": latitude, "longitude": longitude, "altitude": altitude},
                )
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{Path(path).name}: {exc}")

        if failures:
            QMessageBox.warning(
                self, tr("Warning"),
                "Some files could not be written:\n\n" + "\n".join(failures[:10]),
            )
        if self.written:
            self.accept()
        else:
            self.status.setText("⚠ Nothing was written.")

    def _remove(self) -> None:
        from ... import custody
        from ...geotag import remove_gps

        answer = QMessageBox.question(
            self, tr("Warning"),
            f"Remove GPS data from {len(self.records)} image(s)?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        failures = []
        self.removed = []
        for record in self.records:
            path = record.get("file")
            try:
                remove_gps(path, backup=self.backup_check.isChecked())
                self.removed.append(path)
                custody.record("remove_gps", path, {})
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{Path(path).name}: {exc}")

        if failures:
            QMessageBox.warning(
                self, tr("Warning"),
                "Some files could not be changed:\n\n" + "\n".join(failures[:10]),
            )
        if self.removed:
            self.accept()
