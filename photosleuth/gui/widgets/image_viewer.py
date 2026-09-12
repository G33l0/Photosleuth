"""Image preview with zoom and pan (feature A2)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QImageReader, QPainter, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...i18n import tr
from .. import theme
from ..resources import icon
from .measure_overlay import MeasureMode, MeasureOverlay

MIN_SCALE = 0.04
MAX_SCALE = 24.0
# Guard against a malicious or corrupt file claiming enormous dimensions.
MAX_PIXELS = 200_000_000


class ImageCanvas(QGraphicsView):
    """A pannable, zoomable canvas holding one image."""

    scaleChanged = Signal(float)
    measurementComplete = Signal(object)
    landmarkPlaced = Signal(float, float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._item: Optional[QGraphicsPixmapItem] = None
        self._overlay: Optional[MeasureOverlay] = None
        self._measure_mode = MeasureMode.NONE
        self._fit = True
        self._rotation = 0

        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setAlignment(Qt.AlignCenter)

    # -- content -----------------------------------------------------------
    def load(self, path) -> bool:
        source = Path(path)
        self._scene.clear()
        self._item = None
        self._rotation = 0
        if not source.is_file():
            return False

        reader = QImageReader(str(source))
        reader.setAutoTransform(True)  # honour the EXIF orientation tag
        size = reader.size()
        if size.isValid() and size.width() * size.height() > MAX_PIXELS:
            return False

        image = reader.read()
        if image.isNull():
            return False

        pixmap = QPixmap.fromImage(image)
        self._item = self._scene.addPixmap(pixmap)
        self._item.setTransformationMode(Qt.SmoothTransformation)
        self._scene.setSceneRect(QRectF(pixmap.rect()))

        self._overlay = MeasureOverlay(pixmap.width(), pixmap.height())
        self._scene.addItem(self._overlay)
        self._overlay.measurementComplete.connect(self.measurementComplete)
        self._overlay.landmarkPlaced.connect(self.landmarkPlaced)
        self._overlay.set_mode(self._measure_mode)

        self.fit()
        return True

    def clear(self) -> None:
        self._scene.clear()
        self._item = None
        self._overlay = None

    # -- measuring ---------------------------------------------------------
    def set_measure_mode(self, mode: MeasureMode) -> None:
        """Switch between panning the image and drawing on it."""
        self._measure_mode = mode
        measuring = mode is not MeasureMode.NONE
        # Drag-to-pan would swallow the clicks the overlay needs.
        self.setDragMode(QGraphicsView.NoDrag if measuring else QGraphicsView.ScrollHandDrag)
        self.setCursor(Qt.CrossCursor if measuring else Qt.ArrowCursor)
        if self._overlay is not None:
            self._overlay.set_mode(mode)

    @property
    def measure_mode(self) -> MeasureMode:
        return self._measure_mode

    def clear_measurements(self) -> None:
        if self._overlay is not None:
            self._overlay.clear()

    def undo_measurement(self) -> None:
        if self._overlay is not None:
            self._overlay.undo()

    @property
    def has_image(self) -> bool:
        return self._item is not None

    # -- zoom / pan --------------------------------------------------------
    def current_scale(self) -> float:
        return float(self.transform().m11()) or 1.0

    def zoom(self, factor: float, anchor_mouse: bool = False) -> None:
        if self._item is None:
            return
        scale = self.current_scale()
        target = max(MIN_SCALE, min(MAX_SCALE, scale * factor))
        if abs(target - scale) < 1e-9:
            return
        self._fit = False
        anchor = self.transformationAnchor()
        if not anchor_mouse:
            self.setTransformationAnchor(QGraphicsView.AnchorViewCenter)
        self.scale(target / scale, target / scale)
        self.setTransformationAnchor(anchor)
        self.scaleChanged.emit(self.current_scale())

    def fit(self) -> None:
        if self._item is None:
            return
        self._fit = True
        self.fitInView(self._item, Qt.KeepAspectRatio)
        self.scaleChanged.emit(self.current_scale())

    def actual_size(self) -> None:
        if self._item is None:
            return
        self._fit = False
        self.resetTransform()
        if self._rotation:
            self.rotate(self._rotation)
        self.scaleChanged.emit(self.current_scale())

    def rotate_by(self, degrees: int) -> None:
        if self._item is None:
            return
        self._rotation = (self._rotation + degrees) % 360
        self.rotate(degrees)
        if self._fit:
            self.fit()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self._item is None:
            return
        delta = event.angleDelta().y()
        if not delta:
            return
        self.zoom(1.18 if delta > 0 else 1 / 1.18, anchor_mouse=True)
        event.accept()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._fit and self._item is not None:
            self.fitInView(self._item, Qt.KeepAspectRatio)
            # Refitting changes the scale, so the zoom readout must follow.
            self.scaleChanged.emit(self.current_scale())

    def mouseDoubleClickEvent(self, event) -> None:
        if self._measure_mode is not MeasureMode.NONE:
            event.ignore()
            return
        self.actual_size() if self._fit else self.fit()
        event.accept()


class ImageViewer(QWidget):
    """Canvas plus a compact zoom toolbar and caption."""

    measurementComplete = Signal(object)
    landmarkPlaced = Signal(float, float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.canvas = ImageCanvas(self)
        self.canvas.measurementComplete.connect(self.measurementComplete)
        self.canvas.landmarkPlaced.connect(self.landmarkPlaced)
        self._path: Optional[str] = None

        colours = theme.palette()
        bar = QHBoxLayout()
        bar.setContentsMargins(6, 5, 6, 5)
        bar.setSpacing(4)

        self.caption = QLabel(tr("No images loaded"), self)
        self.caption.setStyleSheet(f"color: {colours['text_muted']};")
        self.caption.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        bar.addWidget(self.caption, 1)

        self.zoom_label = QLabel("—", self)
        self.zoom_label.setMinimumWidth(52)
        self.zoom_label.setAlignment(Qt.AlignCenter)
        self.zoom_label.setStyleSheet(f"color: {colours['text_muted']};")
        bar.addWidget(self.zoom_label)

        for name, tip, slot in (
            ("zoom-out", tr("Zoom Out"), lambda: self.canvas.zoom(1 / 1.25)),
            ("zoom-in", tr("Zoom In"), lambda: self.canvas.zoom(1.25)),
            ("fit", tr("Fit to Window"), self.canvas.fit),
            ("rotate", tr("Rotate"), lambda: self.canvas.rotate_by(90)),
        ):
            button = QToolButton(self)
            button.setIcon(icon(name, colours["icon"]))
            button.setToolTip(tip)
            button.setAutoRaise(True)
            button.clicked.connect(slot)
            bar.addWidget(button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(bar)
        layout.addWidget(self.canvas, 1)

        self.canvas.scaleChanged.connect(self._update_zoom_label)
        self._measure_hint = QLabel("", self)
        self._measure_hint.setStyleSheet(
            f"color: {colours['accent']}; padding: 3px 8px;"
        )
        self._measure_hint.hide()
        layout.insertWidget(1, self._measure_hint)

    def set_measure_mode(self, mode) -> None:
        """Put the viewer into a measuring mode and explain what to click."""
        self.canvas.set_measure_mode(mode)
        hints = {
            MeasureMode.SHADOW: "Click three points: top of the object, its base, "
                                "then the tip of the shadow.",
            MeasureMode.LANDMARK: "Click a landmark in the photo, then click the same "
                                  "place on the map.",
            MeasureMode.LINE: "Click two points to measure a distance in pixels.",
            MeasureMode.ANGLE: "Click the vertex, then the two directions.",
        }
        text = hints.get(mode, "")
        self._measure_hint.setText(text)
        self._measure_hint.setVisible(bool(text))

    def show_image(self, path, caption: str = "") -> bool:
        ok = self.canvas.load(path)
        self._path = str(path) if ok else None
        if ok:
            self.caption.setText(caption or Path(path).name)
        else:
            self.caption.setText(f"{tr('Error')}: {Path(path).name}")
            self.zoom_label.setText("—")
        return ok

    def clear(self) -> None:
        self.canvas.clear()
        self._path = None
        self.caption.setText(tr("No images loaded"))
        self.zoom_label.setText("—")

    def _update_zoom_label(self, scale: float) -> None:
        self.zoom_label.setText(f"{scale * 100:.0f}%")
