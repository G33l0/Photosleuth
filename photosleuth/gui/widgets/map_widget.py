"""A pan-and-zoom OpenStreetMap widget built from tiles, with no WebEngine.

Qt WebEngine would add several hundred megabytes to the Windows build just to
show a map, so this fetches the same OSM tiles directly, caches them on disk,
and paints them itself. On top of the map it draws the fused probability
surface, candidate pins, view cones and landmarks.
"""

from __future__ import annotations

import math
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QObject, QPoint, QPointF, QRect, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from ... import __version__
from ...config import config_home
from .. import theme

TILE_SIZE = 256
TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
MIN_ZOOM, MAX_ZOOM = 1, 18
# OpenStreetMap's tile policy asks for a real User-Agent, caching, and no bulk
# downloading. All three are honoured here.
USER_AGENT = f"PhotoSleuth/{__version__} (desktop map view)"
ATTRIBUTION = "© OpenStreetMap contributors"


def deg_to_pixel(latitude: float, longitude: float, zoom: int) -> Tuple[float, float]:
    scale = TILE_SIZE * (2 ** zoom)
    x = (longitude + 180.0) / 360.0 * scale
    latitude = max(-85.05112878, min(85.05112878, latitude))
    sin_lat = math.sin(math.radians(latitude))
    y = (0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)) * scale
    return x, y


def pixel_to_deg(x: float, y: float, zoom: int) -> Tuple[float, float]:
    scale = TILE_SIZE * (2 ** zoom)
    longitude = x / scale * 360.0 - 180.0
    n = math.pi - 2.0 * math.pi * y / scale
    latitude = math.degrees(math.atan(math.sinh(n)))
    return latitude, longitude


# --------------------------------------------------------------------------
# Tile loading
# --------------------------------------------------------------------------

class _TileSignals(QObject):
    ready = Signal(str, QImage)
    failed = Signal(str)
    offline = Signal(str)


class _TileJob(QRunnable):
    def __init__(self, key: str, zoom: int, x: int, y: int, cache_dir: Path,
                 signals: _TileSignals, token: "_Cancellation") -> None:
        super().__init__()
        self.key, self.zoom, self.x, self.y = key, zoom, x, y
        self.cache_dir = cache_dir
        self.signals = signals
        self.token = token
        self.setAutoDelete(True)

    def _emit(self, signal, *args) -> None:
        """Emitting into a torn-down receiver is normal during shutdown."""
        if self.token.cancelled:
            return
        try:
            signal.emit(*args)
        except RuntimeError:
            pass

    def run(self) -> None:  # pragma: no cover - network path
        if self.token.cancelled:
            return

        path = self.cache_dir / str(self.zoom) / str(self.x) / f"{self.y}.png"
        if path.is_file():
            image = QImage(str(path))
            if not image.isNull():
                self._emit(self.signals.ready, self.key, image)
                return

        # A disk miss is as far as this goes without a connection. The job
        # still ran, so tiles saved on a previous session keep working.
        from ...connectivity import is_online

        if not is_online():
            self._emit(self.signals.offline, self.key)
            return

        try:
            import requests

            response = requests.get(
                TILE_URL.format(z=self.zoom, x=self.x, y=self.y),
                headers={"User-Agent": USER_AGENT},
                timeout=8,
            )
            if response.status_code != 200:
                self._emit(self.signals.failed, self.key)
                return
            image = QImage.fromData(response.content)
            if image.isNull():
                self._emit(self.signals.failed, self.key)
                return
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(response.content)
            except OSError:
                pass
            self._emit(self.signals.ready, self.key, image)
        except Exception:
            self._emit(self.signals.failed, self.key)


class _Cancellation:
    """Shared flag so in-flight jobs stop touching a torn-down cache."""

    def __init__(self) -> None:
        self.cancelled = False


class TileCache(QObject):
    """Memory cache in front of a disk cache in front of the tile server."""

    tileReady = Signal()

    def __init__(self, parent=None, memory_limit: int = 512) -> None:
        super().__init__(parent)
        self.token = _Cancellation()
        self.directory = config_home() / "tile_cache"
        self.memory: Dict[str, QPixmap] = {}
        self.memory_limit = memory_limit
        self.pending: set = set()
        self.failed: set = set()
        self.offline_misses: set = set()
        self.missing_offline = False
        self.enabled = True
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(4)   # be a good citizen towards the tile server
        self.signals = _TileSignals()
        self.signals.ready.connect(self._store)
        self.signals.failed.connect(self._fail)
        self.signals.offline.connect(self._offline_miss)

        # Coming back online, previously unreachable tiles deserve another go.
        from ...connectivity import monitor

        monitor().add_listener(self._connectivity_changed)

    def get(self, zoom: int, x: int, y: int) -> Optional[QPixmap]:
        key = f"{zoom}/{x}/{y}"
        if key in self.memory:
            return self.memory[key]
        if key in self.pending or key in self.failed or not self.enabled:
            return None
        if key in self.offline_misses:
            return None
        self.pending.add(key)
        self.pool.start(
            _TileJob(key, zoom, x, y, self.directory, self.signals, self.token)
        )
        return None

    def _store(self, key: str, image: QImage) -> None:
        self.pending.discard(key)
        if len(self.memory) >= self.memory_limit:
            # Cheap eviction: drop the oldest quarter rather than track usage.
            for stale in list(self.memory)[: self.memory_limit // 4]:
                self.memory.pop(stale, None)
        self.memory[key] = QPixmap.fromImage(image)
        self.tileReady.emit()

    def _fail(self, key: str) -> None:
        self.pending.discard(key)
        self.failed.add(key)

    def _offline_miss(self, key: str) -> None:
        """Not a failure - just nothing cached for a tile we cannot fetch."""
        self.pending.discard(key)
        self.offline_misses.add(key)
        self.missing_offline = True

    def _connectivity_changed(self, state) -> None:
        if state.usable and self.offline_misses:
            # Retry only what the lack of a connection blocked.
            self.offline_misses.clear()
            self.missing_offline = False
            self.tileReady.emit()

    def clear_failures(self) -> None:
        self.failed.clear()
        self.offline_misses.clear()
        self.missing_offline = False

    def disk_usage_mb(self) -> float:
        """How much of the disk the tile cache is using."""
        try:
            return sum(
                f.stat().st_size for f in self.directory.rglob("*.png") if f.is_file()
            ) / 1024 / 1024
        except OSError:
            return 0.0

    def clear_disk(self) -> int:
        """Delete the cached tiles. Returns how many files went."""
        removed = 0
        try:
            for file in self.directory.rglob("*.png"):
                try:
                    file.unlink()
                    removed += 1
                except OSError:
                    continue
        except OSError:
            pass
        self.memory.clear()
        self.clear_failures()
        return removed

    def shutdown(self, timeout_ms: int = 2000) -> None:
        """Stop fetching and let queued jobs drain quietly."""
        self.token.cancelled = True
        self.pool.clear()
        self.pool.waitForDone(timeout_ms)


_shared_cache: Optional[TileCache] = None


def shared_tile_cache() -> TileCache:
    """One cache for the whole process.

    Tiles are expensive to fetch and OpenStreetMap asks clients not to re-request
    them, so every map view shares one memory cache. Keeping it unparented also
    means a closing window cannot delete it out from under a running job.
    """
    global _shared_cache
    if _shared_cache is None:
        _shared_cache = TileCache()
    return _shared_cache


# --------------------------------------------------------------------------
# The widget
# --------------------------------------------------------------------------

class MapWidget(QWidget):
    """Slippy map with probability, candidate, cone and landmark overlays."""

    clicked = Signal(float, float)          # latitude, longitude
    viewChanged = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self.centre_lat = 20.0
        self.centre_lon = 0.0
        self.zoom = 2

        self.cache = shared_tile_cache()
        self.cache.tileReady.connect(self.update)

        self._drag_origin: Optional[QPoint] = None
        self._dragged = False
        self._cursor_lat: Optional[float] = None
        self._cursor_lon: Optional[float] = None

        self.heatmap: Optional[QImage] = None
        self.heatmap_bounds: Optional[Tuple[float, float, float, float]] = None
        self.candidates: List[Any] = []
        self.markers: List[Dict[str, Any]] = []
        self.cones: List[Dict[str, Any]] = []

    # -- view ----------------------------------------------------------
    def set_centre(self, latitude: float, longitude: float, zoom: Optional[int] = None) -> None:
        self.centre_lat = max(-85.0, min(85.0, float(latitude)))
        self.centre_lon = ((float(longitude) + 180.0) % 360.0) - 180.0
        if zoom is not None:
            self.zoom = max(MIN_ZOOM, min(MAX_ZOOM, int(zoom)))
        self.viewChanged.emit()
        self.update()

    def fit_bounds(self, lat_min: float, lat_max: float, lon_min: float, lon_max: float) -> None:
        """Centre and zoom so a region fills the widget."""
        self.centre_lat = (lat_min + lat_max) / 2.0
        self.centre_lon = (lon_min + lon_max) / 2.0
        for zoom in range(MAX_ZOOM, MIN_ZOOM - 1, -1):
            x0, y0 = deg_to_pixel(lat_max, lon_min, zoom)
            x1, y1 = deg_to_pixel(lat_min, lon_max, zoom)
            if abs(x1 - x0) <= self.width() * 0.9 and abs(y1 - y0) <= self.height() * 0.9:
                self.zoom = zoom
                break
        else:
            self.zoom = MIN_ZOOM
        self.viewChanged.emit()
        self.update()

    def screen_of(self, latitude: float, longitude: float) -> QPointF:
        cx, cy = deg_to_pixel(self.centre_lat, self.centre_lon, self.zoom)
        px, py = deg_to_pixel(latitude, longitude, self.zoom)
        return QPointF(px - cx + self.width() / 2.0, py - cy + self.height() / 2.0)

    def coords_of(self, point) -> Tuple[float, float]:
        cx, cy = deg_to_pixel(self.centre_lat, self.centre_lon, self.zoom)
        x = cx + point.x() - self.width() / 2.0
        y = cy + point.y() - self.height() / 2.0
        return pixel_to_deg(x, y, self.zoom)

    # -- overlays ------------------------------------------------------
    def set_heatmap(self, grid, threshold: float = 0.35) -> None:
        """Render a fused probability grid as a translucent overlay."""
        if grid is None:
            self.heatmap = None
            self.heatmap_bounds = None
            self.update()
            return

        import numpy as np

        values = np.clip(np.asarray(grid.values, dtype=float), 0.0, 1.0)
        rows, cols = values.shape
        rgba = np.zeros((rows, cols, 4), dtype=np.uint8)

        # Below the threshold the cell is left transparent, so the map stays
        # readable and the eye is drawn only to plausible ground.
        strength = np.clip((values - threshold) / max(1e-6, 1.0 - threshold), 0.0, 1.0)
        rgba[..., 0] = (40 + 215 * strength).astype(np.uint8)
        rgba[..., 1] = (214 * (1.0 - strength) + 40 * strength).astype(np.uint8)
        rgba[..., 2] = (224 * (1.0 - strength) + 62 * strength).astype(np.uint8)
        rgba[..., 3] = (strength * 190).astype(np.uint8)

        # Row 0 of the grid is the southern edge; screen y grows downward.
        rgba = np.ascontiguousarray(rgba[::-1])
        image = QImage(rgba.data, cols, rows, 4 * cols, QImage.Format_RGBA8888).copy()

        self.heatmap = image
        self.heatmap_bounds = (grid.lat_min, grid.lat_max, grid.lon_min, grid.lon_max)
        self.update()

    def set_candidates(self, candidates) -> None:
        self.candidates = list(candidates or [])
        self.update()

    def set_markers(self, markers) -> None:
        """Markers are dicts: latitude, longitude, label, colour."""
        self.markers = list(markers or [])
        self.update()

    def set_cones(self, cones) -> None:
        """Cones are dicts: latitude, longitude, bearing, half_angle, max_km."""
        self.cones = list(cones or [])
        self.update()

    def clear_overlays(self) -> None:
        self.heatmap = None
        self.heatmap_bounds = None
        self.candidates = []
        self.markers = []
        self.cones = []
        self.update()

    # -- painting ------------------------------------------------------
    def paintEvent(self, _event) -> None:
        colours = theme.palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(colours["surface_alt"]))

        self._paint_tiles(painter)
        self._paint_heatmap(painter)
        self._paint_cones(painter, colours)
        self._paint_markers(painter, colours)
        self._paint_candidates(painter, colours)
        self._paint_chrome(painter, colours)

    def _paint_tiles(self, painter: QPainter) -> None:
        cx, cy = deg_to_pixel(self.centre_lat, self.centre_lon, self.zoom)
        left = cx - self.width() / 2.0
        top = cy - self.height() / 2.0
        count = 2 ** self.zoom

        first_x = math.floor(left / TILE_SIZE)
        first_y = math.floor(top / TILE_SIZE)
        last_x = math.floor((left + self.width()) / TILE_SIZE)
        last_y = math.floor((top + self.height()) / TILE_SIZE)

        for tile_x in range(first_x, last_x + 1):
            for tile_y in range(first_y, last_y + 1):
                if not 0 <= tile_y < count:
                    continue
                pixmap = self.cache.get(self.zoom, tile_x % count, tile_y)
                if pixmap is None:
                    continue
                painter.drawPixmap(
                    QPoint(int(tile_x * TILE_SIZE - left), int(tile_y * TILE_SIZE - top)),
                    pixmap,
                )

    def _paint_heatmap(self, painter: QPainter) -> None:
        if self.heatmap is None or self.heatmap_bounds is None:
            return
        lat_min, lat_max, lon_min, lon_max = self.heatmap_bounds
        top_left = self.screen_of(lat_max, lon_min)
        bottom_right = self.screen_of(lat_min, lon_max)
        rect = QRect(
            int(top_left.x()), int(top_left.y()),
            max(1, int(bottom_right.x() - top_left.x())),
            max(1, int(bottom_right.y() - top_left.y())),
        )
        painter.setOpacity(0.72)
        painter.drawImage(rect, self.heatmap)
        painter.setOpacity(1.0)

    def _paint_cones(self, painter: QPainter, colours) -> None:
        for cone in self.cones:
            origin = self.screen_of(cone["latitude"], cone["longitude"])
            metres_per_pixel = (
                156543.03392 * math.cos(math.radians(self.centre_lat)) / (2 ** self.zoom)
            )
            radius = (cone.get("max_km", 2.0) * 1000.0) / max(metres_per_pixel, 1e-6)
            if radius < 3:
                continue

            polygon = QPolygonF([origin])
            half = cone.get("half_angle", 30.0)
            start = cone.get("bearing", 0.0) - half
            for step in range(25):
                angle = math.radians(start + (2 * half) * step / 24.0)
                polygon.append(QPointF(
                    origin.x() + math.sin(angle) * radius,
                    origin.y() - math.cos(angle) * radius,
                ))
            polygon.append(origin)

            colour = QColor(colours["accent"])
            colour.setAlpha(55)
            painter.setBrush(colour)
            painter.setPen(QPen(QColor(colours["accent"]), 1))
            painter.drawPolygon(polygon)

    @staticmethod
    def _draw_label(painter: QPainter, x: float, y: float, text: str,
                    colour: str = "#12202e") -> None:
        """Label with a halo.

        OSM tiles are light whatever theme the app is in, so a theme-coloured
        label would vanish against them in dark mode.
        """
        painter.save()
        painter.setPen(QPen(QColor(255, 255, 255, 220), 3))
        path_font = QFont(painter.font())
        painter.setFont(path_font)
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            painter.setPen(QColor(255, 255, 255, 230))
            painter.drawText(QPointF(x + dx, y + dy), text)
        painter.setPen(QColor(colour))
        painter.drawText(QPointF(x, y), text)
        painter.restore()

    def _paint_markers(self, painter: QPainter, colours) -> None:
        for marker in self.markers:
            point = self.screen_of(marker["latitude"], marker["longitude"])
            colour = QColor(marker.get("colour", colours["warning"]))
            painter.setBrush(colour)
            painter.setPen(QPen(QColor("#0c1126"), 1))
            painter.drawEllipse(point, 6, 6)
            label = marker.get("label", "")
            if label:
                self._draw_label(painter, point.x() + 10, point.y() + 4, str(label)[:28])

    def _paint_candidates(self, painter: QPainter, colours) -> None:
        for candidate in self.candidates:
            point = self.screen_of(candidate.latitude, candidate.longitude)
            best = candidate.rank == 1
            radius = 11 if best else 8

            colour = QColor(colours["accent"] if best else colours["text_muted"])
            painter.setBrush(colour)
            painter.setPen(QPen(QColor("#ffffff"), 2))
            painter.drawEllipse(point, radius, radius)

            font = QFont(painter.font())
            font.setBold(True)
            font.setPointSizeF(8.0)
            painter.setFont(font)
            painter.setPen(QColor("#0c1126"))
            painter.drawText(
                QRect(int(point.x() - radius), int(point.y() - radius), radius * 2, radius * 2),
                Qt.AlignCenter,
                str(candidate.rank),
            )

            # Only the leading candidate is labelled: when several cluster in
            # one spot their labels would otherwise overprint each other.
            if best:
                self._draw_label(
                    painter,
                    point.x() + radius + 4,
                    point.y() + 4,
                    f"{candidate.latitude:.4f}, {candidate.longitude:.4f} ({candidate.score:.2f})",
                )

    def _paint_chrome(self, painter: QPainter, colours) -> None:
        font = QFont(painter.font())
        font.setPointSizeF(7.5)
        painter.setFont(font)

        # A solid strip keeps the attribution legible over any tile.
        painter.fillRect(
            QRect(0, self.height() - 16, self.width(), 16), QColor(255, 255, 255, 205)
        )
        painter.setPen(QColor("#3d4a5c"))
        painter.drawText(QPointF(6, self.height() - 4), ATTRIBUTION)

        readout = f"z{self.zoom}  {self.centre_lat:.4f}, {self.centre_lon:.4f}"
        if self._cursor_lat is not None:
            readout = f"z{self.zoom}  cursor {self._cursor_lat:.4f}, {self._cursor_lon:.4f}"
        painter.drawText(QPointF(self.width() - 232, self.height() - 4), readout)

        notice = ""
        if not self.cache.enabled:
            notice = "Map tiles are turned off"
        elif self.cache.missing_offline:
            from ...connectivity import state as network_state

            current = network_state()
            notice = (
                "Working offline - showing cached map tiles only"
                if current.blocked_by_choice
                else "No connection - showing cached map tiles only"
            )
        if notice:
            painter.fillRect(QRect(0, 0, self.width(), 20), QColor(255, 240, 210, 230))
            painter.setPen(QColor("#8a5a00"))
            painter.drawText(QPointF(8, 14), notice)

    # -- interaction ---------------------------------------------------
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_origin = event.position().toPoint()
            self._dragged = False
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:
        point = event.position().toPoint()
        self._cursor_lat, self._cursor_lon = self.coords_of(point)

        if self._drag_origin is not None:
            delta = point - self._drag_origin
            if delta.manhattanLength() > 2:
                self._dragged = True
                cx, cy = deg_to_pixel(self.centre_lat, self.centre_lon, self.zoom)
                self.centre_lat, self.centre_lon = pixel_to_deg(
                    cx - delta.x(), cy - delta.y(), self.zoom
                )
                self.centre_lat = max(-85.0, min(85.0, self.centre_lat))
                self._drag_origin = point
                self.viewChanged.emit()
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        self.setCursor(Qt.ArrowCursor)
        if event.button() == Qt.LeftButton:
            if not self._dragged:
                latitude, longitude = self.coords_of(event.position().toPoint())
                self.clicked.emit(latitude, longitude)
            self._drag_origin = None

    def leaveEvent(self, _event) -> None:
        self._cursor_lat = self._cursor_lon = None
        self.update()

    def closeEvent(self, event) -> None:
        # The cache is shared, so only this view's connection is dropped.
        try:
            self.cache.tileReady.disconnect(self.update)
        except (RuntimeError, TypeError):
            pass
        super().closeEvent(event)

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if not delta:
            return
        point = event.position().toPoint()
        before = self.coords_of(point)
        self.zoom = max(MIN_ZOOM, min(MAX_ZOOM, self.zoom + (1 if delta > 0 else -1)))

        # Keep the point under the cursor fixed while zooming.
        after = self.coords_of(point)
        self.centre_lat += before[0] - after[0]
        self.centre_lon += before[1] - after[1]
        self.centre_lat = max(-85.0, min(85.0, self.centre_lat))

        self.viewChanged.emit()
        self.update()
        event.accept()

    def keyPressEvent(self, event) -> None:
        step = 60
        if event.key() in (Qt.Key_Plus, Qt.Key_Equal):
            self.set_centre(self.centre_lat, self.centre_lon, self.zoom + 1)
        elif event.key() == Qt.Key_Minus:
            self.set_centre(self.centre_lat, self.centre_lon, self.zoom - 1)
        elif event.key() in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            cx, cy = deg_to_pixel(self.centre_lat, self.centre_lon, self.zoom)
            dx = -step if event.key() == Qt.Key_Left else step if event.key() == Qt.Key_Right else 0
            dy = -step if event.key() == Qt.Key_Up else step if event.key() == Qt.Key_Down else 0
            latitude, longitude = pixel_to_deg(cx + dx, cy + dy, self.zoom)
            self.set_centre(latitude, longitude)
        else:
            super().keyPressEvent(event)
