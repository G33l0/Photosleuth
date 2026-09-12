"""Grouped, searchable metadata tree (features A3 and A4)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...i18n import tr
from .. import theme

# Which EXIF prefixes land in which group, in display order.
GROUPS: List[Tuple[str, Tuple[str, ...]]] = [
    ("Camera", ("Image Make", "Image Model", "EXIF LensModel", "EXIF LensMake",
                "EXIF BodySerialNumber", "EXIF LensSerialNumber", "MakerNote")),
    ("Exposure", ("EXIF ExposureTime", "EXIF FNumber", "EXIF ISOSpeedRatings",
                  "EXIF ShutterSpeedValue", "EXIF ApertureValue", "EXIF FocalLength",
                  "EXIF Flash", "EXIF WhiteBalance", "EXIF MeteringMode",
                  "EXIF ExposureProgram", "EXIF ExposureBiasValue", "EXIF SceneCaptureType")),
    ("Location", ("GPS",)),
    ("Software", ("Image Software", "EXIF Software", "Image DateTime",
                  "EXIF DateTimeOriginal", "EXIF DateTimeDigitized", "Image Artist",
                  "Image Copyright", "Image HostComputer")),
]


class MetadataTree(QWidget):
    """A tree of metadata grouped into sections, with a live filter box."""

    tagActivated = Signal(str, str)

    def __init__(self, parent=None, show_filter: bool = True) -> None:
        super().__init__(parent)
        self._metadata: Optional[Dict[str, Any]] = None

        self.filter_box = QLineEdit(self)
        self.filter_box.setPlaceholderText(tr("Search metadata…"))
        self.filter_box.setClearButtonEnabled(True)
        self.filter_box.textChanged.connect(self._apply_filter)

        self.raw_toggle = QCheckBox(tr("All"), self)
        self.raw_toggle.setToolTip("Show every raw EXIF tag, not just the grouped ones")
        self.raw_toggle.toggled.connect(lambda _: self.set_metadata(self._metadata))

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 6)
        top.setSpacing(6)
        top.addWidget(self.filter_box, 1)
        top.addWidget(self.raw_toggle)

        self.tree = QTreeWidget(self)
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Field", "Value"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setTextElideMode(Qt.ElideMiddle)
        self.tree.header().setStretchLastSection(True)
        self.tree.setColumnWidth(0, 210)
        self.tree.itemDoubleClicked.connect(self._emit_activated)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        if show_filter:
            layout.addLayout(top)
        else:
            self.filter_box.hide()
            self.raw_toggle.hide()
        layout.addWidget(self.tree, 1)

    # -- population --------------------------------------------------------
    def set_metadata(self, metadata: Optional[Dict[str, Any]]) -> None:
        self._metadata = metadata
        self.tree.clear()
        if not metadata:
            return

        colours = theme.palette()
        exif = dict(metadata.get("exif") or {})
        consumed: set = set()

        file_rows = [
            ("Name", metadata.get("name", "")),
            ("Path", metadata.get("file", "")),
            ("Size", metadata.get("size_human") or str(metadata.get("size", ""))),
            ("Modified", metadata.get("modified", "")),
        ]
        if metadata.get("date_taken"):
            file_rows.append(("Taken", metadata["date_taken"]))
        self._add_group(tr("File Info"), file_rows, colours)

        gps = metadata.get("gps")
        location_rows: List[Tuple[str, Any]] = []
        if gps:
            location_rows.append((tr("Latitude"), f"{gps['latitude']:.6f}"))
            location_rows.append((tr("Longitude"), f"{gps['longitude']:.6f}"))
            if gps.get("altitude_m") is not None:
                location_rows.append((tr("Altitude"), f"{gps['altitude_m']} m"))
        if metadata.get("location"):
            location_rows.append((tr("Address"), metadata["location"]))
        if metadata.get("map_url"):
            location_rows.append(("Google Maps", metadata["map_url"]))
        if metadata.get("osm_url"):
            location_rows.append(("OpenStreetMap", metadata["osm_url"]))

        for group_name, prefixes in GROUPS:
            rows: List[Tuple[str, Any]] = []
            for tag in sorted(exif):
                if tag in consumed:
                    continue
                if any(tag.startswith(prefix) for prefix in prefixes):
                    rows.append((tag, exif[tag]))
                    consumed.add(tag)
            if group_name == "Location":
                rows = location_rows + rows
            if rows:
                self._add_group(tr(group_name), rows, colours)

        if self.raw_toggle.isChecked():
            leftovers = [(tag, exif[tag]) for tag in sorted(exif) if tag not in consumed]
            if leftovers:
                self._add_group(tr("Other"), leftovers, colours)

        forensics = metadata.get("forensics")
        if forensics:
            check = forensics.get("thumbnail_check") or {}
            rows = [
                ("Verdict", forensics.get("verdict", "")),
                ("Thumbnail difference", f"{check.get('distance')}/64"
                 if check.get("distance") is not None else "n/a"),
                ("Confidence", check.get("confidence", "")),
                ("SHA-256", (forensics.get("hashes") or {}).get("sha256", "")),
            ]
            for index, flag in enumerate(forensics.get("flags") or [], start=1):
                rows.append((f"Flag {index}", flag))
            self._add_group(tr("Forensics"), rows, colours)

        self.tree.expandAll()
        self._apply_filter(self.filter_box.text())

    def _add_group(self, title: str, rows, colours) -> None:
        rows = [(key, value) for key, value in rows if str(value) != ""]
        if not rows:
            return
        parent = QTreeWidgetItem(self.tree, [f"{title}  ({len(rows)})", ""])
        font = QFont()
        font.setBold(True)
        parent.setFont(0, font)
        parent.setForeground(0, QBrush(QColor(colours["accent"])))
        parent.setFirstColumnSpanned(True)
        for key, value in rows:
            child = QTreeWidgetItem(parent, [str(key), str(value)])
            child.setToolTip(1, str(value))

    # -- filtering ---------------------------------------------------------
    def _apply_filter(self, text: str) -> None:
        needle = (text or "").strip().lower()
        for i in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(i)
            visible_children = 0
            for j in range(group.childCount()):
                child = group.child(j)
                haystack = f"{child.text(0)} {child.text(1)}".lower()
                match = not needle or needle in haystack
                child.setHidden(not match)
                visible_children += int(match)
            group.setHidden(visible_children == 0)
            if needle:
                group.setExpanded(True)

    def _emit_activated(self, item: QTreeWidgetItem, _column: int) -> None:
        if item.parent() is not None:
            self.tagActivated.emit(item.text(0), item.text(1))

    def clear(self) -> None:
        self._metadata = None
        self.tree.clear()
