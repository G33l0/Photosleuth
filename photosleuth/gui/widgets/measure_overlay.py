"""Drawing measurements on the photograph itself (feature 35).

Three modes feed the analysers: a plain line, an angle between two rays, and
the shadow pair - object then shadow - that the solar techniques need.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsItem, QGraphicsObject

from .. import theme


class MeasureMode(Enum):
    NONE = "none"
    LINE = "line"
    ANGLE = "angle"
    SHADOW = "shadow"
    LANDMARK = "landmark"


@dataclass
class Measurement:
    """Points in *image* coordinates, so results survive zooming."""

    mode: MeasureMode
    points: List[Tuple[float, float]] = field(default_factory=list)
    label: str = ""

    @property
    def length(self) -> float:
        if len(self.points) < 2:
            return 0.0
        return math.dist(self.points[0], self.points[1])

    @property
    def is_complete(self) -> bool:
        return len(self.points) >= self.required_points(self.mode)

    @staticmethod
    def required_points(mode: MeasureMode) -> int:
        return {
            MeasureMode.LINE: 2,
            MeasureMode.ANGLE: 3,
            MeasureMode.SHADOW: 3,
            MeasureMode.LANDMARK: 1,
            MeasureMode.NONE: 0,
        }[mode]

    def shadow_observation(self):
        """Object top, object base, shadow tip -> a solar observation."""
        from ...geolocation.shadow import observation_from_points

        if self.mode is not MeasureMode.SHADOW or len(self.points) < 3:
            return None
        return observation_from_points(self.points[0], self.points[1], self.points[2])

    def angle_degrees(self) -> Optional[float]:
        """Planar angle at the vertex. Only a guide: true angles need the lens."""
        if self.mode is not MeasureMode.ANGLE or len(self.points) < 3:
            return None
        vertex, first, second = self.points[0], self.points[1], self.points[2]
        a = math.atan2(first[1] - vertex[1], first[0] - vertex[0])
        b = math.atan2(second[1] - vertex[1], second[0] - vertex[0])
        return abs(math.degrees(((b - a) + math.pi) % (2 * math.pi) - math.pi))


class MeasureOverlay(QGraphicsObject):
    """Transparent item over the photo that captures clicks and draws results."""

    measurementChanged = Signal(object)
    measurementComplete = Signal(object)
    landmarkPlaced = Signal(float, float)

    def __init__(self, width: float, height: float, parent=None) -> None:
        super().__init__(parent)
        self._width = float(width)
        self._height = float(height)
        self.mode = MeasureMode.NONE
        self.current: Optional[Measurement] = None
        self.completed: List[Measurement] = []
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.setZValue(100)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._width, self._height)

    # -- control -------------------------------------------------------
    def set_mode(self, mode: MeasureMode) -> None:
        self.mode = mode
        self.current = None if mode is MeasureMode.NONE else Measurement(mode=mode)
        self.setAcceptedMouseButtons(Qt.LeftButton if mode is not MeasureMode.NONE else Qt.NoButton)
        self.update()

    def clear(self) -> None:
        self.current = Measurement(mode=self.mode) if self.mode is not MeasureMode.NONE else None
        self.completed.clear()
        self.update()
        self.measurementChanged.emit(None)

    def undo(self) -> None:
        if self.current and self.current.points:
            self.current.points.pop()
        elif self.completed:
            self.completed.pop()
        self.update()
        self.measurementChanged.emit(self.current)

    # -- input ---------------------------------------------------------
    def mousePressEvent(self, event) -> None:
        if self.mode is MeasureMode.NONE:
            event.ignore()
            return

        position = event.pos()
        point = (float(position.x()), float(position.y()))

        if self.mode is MeasureMode.LANDMARK:
            self.completed.append(Measurement(mode=self.mode, points=[point]))
            self.landmarkPlaced.emit(point[0], point[1])
            self.update()
            event.accept()
            return

        if self.current is None or self.current.is_complete:
            self.current = Measurement(mode=self.mode)

        self.current.points.append(point)
        self.measurementChanged.emit(self.current)

        if self.current.is_complete:
            self.completed.append(self.current)
            self.measurementComplete.emit(self.current)

        self.update()
        event.accept()

    # -- painting ------------------------------------------------------
    def paint(self, painter: QPainter, _option, _widget=None) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        for measurement in self.completed:
            self._draw(painter, measurement, active=False)
        if self.current and self.current.points and self.current not in self.completed:
            self._draw(painter, self.current, active=True)

    def _draw(self, painter: QPainter, measurement: Measurement, active: bool) -> None:
        colours = theme.palette()
        scale = max(self._width, self._height) / 900.0
        width = max(1.5, 2.4 * scale)

        accent = QColor(colours["accent"] if active else colours["success"])
        warning = QColor(colours["warning"])
        points = [QPointF(x, y) for x, y in measurement.points]

        if measurement.mode is MeasureMode.LANDMARK:
            painter.setPen(QPen(warning, width))
            painter.setBrush(Qt.NoBrush)
            radius = 9 * scale
            for point in points:
                painter.drawEllipse(point, radius, radius)
                painter.drawLine(QPointF(point.x() - radius * 1.7, point.y()),
                                 QPointF(point.x() + radius * 1.7, point.y()))
                painter.drawLine(QPointF(point.x(), point.y() - radius * 1.7),
                                 QPointF(point.x(), point.y() + radius * 1.7))
            return

        if measurement.mode is MeasureMode.SHADOW:
            # Object in accent, shadow in warning, so the pair reads at a glance.
            if len(points) >= 2:
                painter.setPen(QPen(accent, width, Qt.SolidLine, Qt.RoundCap))
                painter.drawLine(points[0], points[1])
            if len(points) >= 3:
                painter.setPen(QPen(warning, width, Qt.DashLine, Qt.RoundCap))
                painter.drawLine(points[1], points[2])
                observation = measurement.shadow_observation()
                if observation:
                    self._annotate(
                        painter, points[2],
                        f"sun {observation.elevation:.1f}°  ratio {observation.ratio:.2f}",
                        scale,
                    )
        elif measurement.mode is MeasureMode.ANGLE:
            painter.setPen(QPen(accent, width, Qt.SolidLine, Qt.RoundCap))
            for point in points[1:]:
                painter.drawLine(points[0], point)
            angle = measurement.angle_degrees()
            if angle is not None:
                self._annotate(painter, points[0], f"{angle:.1f}° (planar)", scale)
        else:
            painter.setPen(QPen(accent, width, Qt.SolidLine, Qt.RoundCap))
            if len(points) >= 2:
                painter.drawLine(points[0], points[1])
                self._annotate(painter, points[1], f"{measurement.length:.0f} px", scale)

        painter.setBrush(accent)
        painter.setPen(QPen(QColor("#ffffff"), max(1.0, scale)))
        for point in points:
            painter.drawEllipse(point, 4.5 * scale, 4.5 * scale)

    def _annotate(self, painter: QPainter, point: QPointF, text: str, scale: float) -> None:
        font = QFont(painter.font())
        font.setPointSizeF(max(7.0, 9.0 * scale))
        font.setBold(True)
        painter.setFont(font)

        metrics = painter.fontMetrics()
        rect = QRectF(
            point.x() + 10 * scale, point.y() - metrics.height() - 4 * scale,
            metrics.horizontalAdvance(text) + 12 * scale, metrics.height() + 6 * scale,
        )
        painter.setBrush(QColor(12, 17, 38, 215))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, 4 * scale, 4 * scale)
        painter.setPen(QColor("#e6edf5"))
        painter.drawText(rect, Qt.AlignCenter, text)
