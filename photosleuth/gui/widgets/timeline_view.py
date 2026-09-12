"""Timeline of a folder by capture date (feature D20)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...i18n import tr
from .. import theme

BUCKETS = (("Day", "%Y-%m-%d"), ("Month", "%Y-%m"), ("Year", "%Y"))


def parse_timestamp(record: Dict[str, Any]) -> Optional[datetime]:
    """Prefer the capture time; fall back to the file's modified time."""
    for key in ("date_taken", "modified"):
        raw = record.get(key)
        if not raw:
            continue
        text = str(raw)
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y:%m:%d %H:%M:%S"):
            try:
                return datetime.strptime(text[:19], fmt)
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            continue
    return None


def build_buckets(records, pattern: str) -> List[Tuple[str, List[Dict[str, Any]]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    undated: List[Dict[str, Any]] = []
    for record in records:
        stamp = parse_timestamp(record)
        if stamp is None:
            undated.append(record)
            continue
        grouped.setdefault(stamp.strftime(pattern), []).append(record)
    ordered = [(key, grouped[key]) for key in sorted(grouped)]
    if undated:
        ordered.append(("No date", undated))
    return ordered


class TimelineCanvas(QWidget):
    """Draws the timeline: one column of dots per time bucket."""

    bucketClicked = Signal(str, list)

    LANE_HEIGHT = 22
    COLUMN_WIDTH = 96
    TOP_MARGIN = 46

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._buckets: List[Tuple[str, List[Dict[str, Any]]]] = []
        self._hover = -1
        self.setMouseTracking(True)
        self.setMinimumHeight(190)
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)

    def set_buckets(self, buckets) -> None:
        self._buckets = list(buckets)
        tallest = max((len(items) for _, items in self._buckets), default=0)
        height = self.TOP_MARGIN + max(3, min(tallest, 12)) * self.LANE_HEIGHT + 34
        self.setMinimumWidth(max(220, len(self._buckets) * self.COLUMN_WIDTH + 24))
        self.setMinimumHeight(height)
        self.updateGeometry()
        self.update()

    def paintEvent(self, _event) -> None:
        colours = theme.palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(colours["surface"]))

        if not self._buckets:
            painter.setPen(QColor(colours["text_muted"]))
            painter.drawText(self.rect(), Qt.AlignCenter, tr("No images loaded"))
            return

        axis_y = self.TOP_MARGIN - 14
        painter.setPen(QPen(QColor(colours["border"]), 1))
        painter.drawLine(12, axis_y, self.width() - 12, axis_y)

        label_font = QFont(self.font())
        label_font.setPointSizeF(max(7.5, label_font.pointSizeF() - 1))
        metrics = QFontMetrics(label_font)
        max_lanes = 12

        for column, (label, items) in enumerate(self._buckets):
            x = 20 + column * self.COLUMN_WIDTH
            centre = x + self.COLUMN_WIDTH // 2 - 10
            hovered = column == self._hover

            painter.setPen(QColor(colours["accent"] if hovered else colours["text_muted"]))
            painter.setFont(label_font)
            painter.drawText(
                QRect(x - 10, 8, self.COLUMN_WIDTH, 16),
                Qt.AlignCenter,
                metrics.elidedText(label, Qt.ElideRight, self.COLUMN_WIDTH - 4),
            )

            painter.setPen(QPen(QColor(colours["accent"] if hovered else colours["border"]), 2))
            painter.drawLine(centre, axis_y - 5, centre, axis_y + 5)

            for lane, record in enumerate(items[:max_lanes]):
                y = self.TOP_MARGIN + lane * self.LANE_HEIGHT
                flagged = bool((record.get("forensics") or {}).get("flags"))
                has_gps = bool(record.get("gps"))
                colour = QColor(
                    colours["warning"] if flagged
                    else (colours["accent"] if has_gps else colours["text_muted"])
                )
                painter.setBrush(colour)
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QPoint(centre, y), 6, 6)

                painter.setPen(QColor(colours["text_muted"]))
                painter.setFont(label_font)
                name = metrics.elidedText(
                    str(record.get("name", "")), Qt.ElideMiddle, self.COLUMN_WIDTH - 26
                )
                painter.drawText(QRect(centre + 11, y - 8, self.COLUMN_WIDTH - 26, 16),
                                 Qt.AlignVCenter | Qt.AlignLeft, name)

            if len(items) > max_lanes:
                painter.setPen(QColor(colours["text_muted"]))
                painter.drawText(
                    QRect(centre - 30, self.TOP_MARGIN + max_lanes * self.LANE_HEIGHT - 6, 90, 16),
                    Qt.AlignLeft, f"+{len(items) - max_lanes} more",
                )

    def _column_at(self, x: int) -> int:
        column = (x - 20) // self.COLUMN_WIDTH
        return int(column) if 0 <= column < len(self._buckets) else -1

    def mouseMoveEvent(self, event) -> None:
        column = self._column_at(event.position().toPoint().x())
        if column != self._hover:
            self._hover = column
            if column >= 0:
                label, items = self._buckets[column]
                self.setToolTip(f"{label} — {len(items)} image(s)")
            else:
                self.setToolTip("")
            self.update()

    def leaveEvent(self, _event) -> None:
        self._hover = -1
        self.update()

    def mousePressEvent(self, event) -> None:
        column = self._column_at(event.position().toPoint().x())
        if column >= 0:
            label, items = self._buckets[column]
            self.bucketClicked.emit(label, items)


class TimelineView(QWidget):
    """Timeline canvas with a bucket-size selector."""

    bucketClicked = Signal(str, list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._records: List[Dict[str, Any]] = []

        self.grouping = QComboBox(self)
        for label, _ in BUCKETS:
            self.grouping.addItem(label)
        self.grouping.setCurrentIndex(0)
        self.grouping.currentIndexChanged.connect(lambda _: self.refresh())

        self.summary = QLabel("", self)
        self.summary.setStyleSheet(f"color: {theme.palette()['text_muted']};")

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 6)
        header.addWidget(QLabel(tr("Timeline"), self))
        header.addWidget(self.grouping)
        header.addStretch(1)
        header.addWidget(self.summary)

        self.canvas = TimelineCanvas(self)
        self.canvas.bucketClicked.connect(self.bucketClicked)

        scroll = QScrollArea(self)
        scroll.setWidget(self.canvas)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addLayout(header)
        layout.addWidget(scroll, 1)

    def set_records(self, records) -> None:
        self._records = list(records)
        self.refresh()

    def refresh(self) -> None:
        pattern = BUCKETS[max(0, self.grouping.currentIndex())][1]
        buckets = build_buckets(self._records, pattern)
        self.canvas.set_buckets(buckets)
        dated = sum(len(items) for label, items in buckets if label != "No date")
        self.summary.setText(
            f"{len(self._records)} {tr('images')} · {len(buckets)} buckets · {dated} dated"
        )
