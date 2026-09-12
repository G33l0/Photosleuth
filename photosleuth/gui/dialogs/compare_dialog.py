"""Side-by-side metadata comparison of two images (feature A5)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from ...i18n import tr
from .. import theme
from ..resources import app_icon
from ..widgets.image_viewer import ImageViewer

# Fields compared outside the raw EXIF block.
CORE_FIELDS: List[Tuple[str, str]] = [
    ("name", "File name"),
    ("size_human", "Size"),
    ("modified", "Modified"),
    ("date_taken", "Taken"),
    ("location", "Address"),
]


def _flatten(metadata: Dict[str, Any]) -> Dict[str, str]:
    """One flat field->value map per image, so the two can be diffed."""
    flat: Dict[str, str] = {}
    for key, label in CORE_FIELDS:
        if metadata.get(key):
            flat[label] = str(metadata[key])
    gps = metadata.get("gps") or {}
    if gps:
        flat["Latitude"] = f"{gps['latitude']:.6f}"
        flat["Longitude"] = f"{gps['longitude']:.6f}"
        if gps.get("altitude_m") is not None:
            flat["Altitude"] = f"{gps['altitude_m']} m"
    for tag, value in (metadata.get("exif") or {}).items():
        flat[tag] = str(value)
    forensics = metadata.get("forensics") or {}
    if forensics:
        flat["Forensic verdict"] = str(forensics.get("verdict", ""))
        sha = (forensics.get("hashes") or {}).get("sha256")
        if sha:
            flat["SHA-256"] = sha
    return flat


class CompareDialog(QDialog):
    """Two previews above a diff table of every metadata field."""

    def __init__(self, left: Dict[str, Any], right: Dict[str, Any], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Compare"))
        self.setWindowIcon(app_icon())
        self.resize(1040, 720)

        self.left = left
        self.right = right
        self._left_flat = _flatten(left)
        self._right_flat = _flatten(right)

        colours = theme.palette()

        self.left_view = ImageViewer(self)
        self.right_view = ImageViewer(self)
        self.left_view.show_image(left.get("file", ""), Path(left.get("file", "")).name)
        self.right_view.show_image(right.get("file", ""), Path(right.get("file", "")).name)

        previews = QHBoxLayout()
        previews.setSpacing(8)
        previews.addWidget(self.left_view, 1)
        previews.addWidget(self.right_view, 1)

        self.differences_only = QCheckBox("Show differences only", self)
        self.differences_only.setChecked(True)
        self.differences_only.toggled.connect(self._populate)

        self.counter = QLabel("", self)
        self.counter.setStyleSheet(f"color: {colours['text_muted']};")

        controls = QHBoxLayout()
        controls.addWidget(self.differences_only)
        controls.addStretch(1)
        controls.addWidget(self.counter)

        self.tree = QTreeWidget(self)
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(
            ["Field", Path(left.get("file", "A")).name, Path(right.get("file", "B")).name]
        )
        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tree.header().setStretchLastSection(True)

        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addLayout(previews, 3)
        layout.addLayout(controls)
        layout.addWidget(self.tree, 2)
        layout.addWidget(buttons)

        self._populate()

    def _populate(self) -> None:
        colours = theme.palette()
        only_differences = self.differences_only.isChecked()
        self.tree.clear()

        keys = sorted(set(self._left_flat) | set(self._right_flat))
        differences = 0
        shown = 0

        bold = QFont()
        bold.setBold(True)

        for key in keys:
            left_value = self._left_flat.get(key, "—")
            right_value = self._right_flat.get(key, "—")
            differs = left_value != right_value
            differences += int(differs)
            if only_differences and not differs:
                continue
            item = QTreeWidgetItem(self.tree, [key, left_value, right_value])
            item.setToolTip(1, left_value)
            item.setToolTip(2, right_value)
            if differs:
                colour = QBrush(QColor(colours["warning"]))
                item.setForeground(1, colour)
                item.setForeground(2, colour)
                item.setFont(0, bold)
            shown += 1

        self.counter.setText(
            f"{differences} difference(s) across {len(keys)} field(s) · showing {shown}"
        )
