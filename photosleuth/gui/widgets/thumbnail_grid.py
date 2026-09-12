"""Thumbnail grid with drag-and-drop (features A1)."""

from __future__ import annotations

from pathlib import Path
from typing import List

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QListView,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from ...i18n import tr
from ...utils import IMAGE_EXTENSIONS
from .. import theme
from ..models import FlaggedRole, HasGpsRole, PathRole, StatusRole


class ThumbnailDelegate(QStyledItemDelegate):
    """Paints a card: image, filename, and GPS / flag badges."""

    def __init__(self, parent=None, thumb_size: int = 160) -> None:
        super().__init__(parent)
        self.thumb_size = thumb_size

    def sizeHint(self, option, index) -> QSize:
        return QSize(self.thumb_size + 26, self.thumb_size + 48)

    def paint(self, painter: QPainter, option, index) -> None:
        colours = theme.palette()
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        rect = option.rect.adjusted(5, 5, -5, -5)
        selected = bool(option.state & QStyle.State_Selected)
        hovered = bool(option.state & QStyle.State_MouseOver)

        background = QColor(colours["selection"]) if selected else QColor(colours["surface"])
        if hovered and not selected:
            background = QColor(colours["surface_alt"])
        painter.setBrush(background)
        painter.setPen(QPen(QColor(colours["accent"] if selected else colours["border"]), 1))
        painter.drawRoundedRect(rect, 7, 7)

        image_rect = QRect(rect.left() + 7, rect.top() + 7, rect.width() - 14, self.thumb_size - 6)
        pixmap = index.data(Qt.DecorationRole)
        if isinstance(pixmap, QPixmap) and not pixmap.isNull():
            scaled = pixmap.scaled(
                image_rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            target = QRect(0, 0, scaled.width(), scaled.height())
            target.moveCenter(image_rect.center())
            painter.drawPixmap(target, scaled)
        else:
            painter.setBrush(QColor(colours["surface_alt"]))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(image_rect, 4, 4)
            painter.setPen(QColor(colours["text_muted"]))
            status = index.data(StatusRole) or ""
            label = "…" if status == "pending" else "?"
            painter.drawText(image_rect, Qt.AlignCenter, label)

        # Badges
        badge_x = image_rect.right() - 20
        badge_y = image_rect.top() + 4
        if index.data(HasGpsRole):
            self._badge(painter, badge_x, badge_y, colours["accent"], "◉")
            badge_x -= 22
        if index.data(FlaggedRole):
            self._badge(painter, badge_x, badge_y, colours["warning"], "!")

        text_rect = QRect(rect.left() + 7, image_rect.bottom() + 5, rect.width() - 14, 20)
        font = QFont(option.font)
        font.setPointSizeF(max(7.5, font.pointSizeF() - 0.5))
        painter.setFont(font)
        painter.setPen(QColor(colours["text"] if selected else colours["text_muted"]))
        name = QFontMetrics(font).elidedText(
            str(index.data(Qt.DisplayRole) or ""), Qt.ElideMiddle, text_rect.width()
        )
        painter.drawText(text_rect, Qt.AlignHCenter | Qt.AlignVCenter, name)

        painter.restore()

    @staticmethod
    def _badge(painter: QPainter, x: int, y: int, colour: str, glyph: str) -> None:
        painter.setBrush(QColor(colour))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(x, y, 17, 17)
        painter.setPen(QColor("#0c1126"))
        font = painter.font()
        font.setBold(True)
        font.setPointSizeF(7.5)
        painter.setFont(font)
        painter.drawText(QRect(x, y, 17, 17), Qt.AlignCenter, glyph)


class ThumbnailGrid(QWidget):
    """The library view: a wrapping grid of image cards that accepts drops."""

    pathsDropped = Signal(list)
    selectionChanged = Signal(list)
    activated = Signal(str)

    def __init__(self, model, parent=None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)

        self.view = QListView(self)
        self.view.setModel(model)
        self.view.setViewMode(QListView.IconMode)
        self.view.setResizeMode(QListView.Adjust)
        self.view.setMovement(QListView.Static)
        self.view.setWrapping(True)
        self.view.setSpacing(3)
        self.view.setUniformItemSizes(True)
        self.view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.view.setMouseTracking(True)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setFrameShape(QListView.NoFrame)
        self.view.setAcceptDrops(False)
        self.view.setDragEnabled(False)

        self.delegate = ThumbnailDelegate(self.view)
        self.view.setItemDelegate(self.delegate)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)

        self.view.selectionModel().selectionChanged.connect(self._emit_selection)
        self.view.doubleClicked.connect(
            lambda index: self.activated.emit(index.data(PathRole) or "")
        )
        self.setToolTip(tr("Drop images or a folder here"))

    # -- selection ---------------------------------------------------------
    def _emit_selection(self, *_args) -> None:
        self.selectionChanged.emit(self.selected_paths())

    def selected_paths(self) -> List[str]:
        return [
            index.data(PathRole)
            for index in self.view.selectionModel().selectedIndexes()
            if index.data(PathRole)
        ]

    def select_path(self, path: str) -> None:
        model = self.view.model()
        for row in range(model.rowCount()):
            index = model.index(row, 0)
            if index.data(PathRole) == str(path):
                self.view.setCurrentIndex(index)
                self.view.scrollTo(index)
                return

    def select_first(self) -> None:
        model = self.view.model()
        if model.rowCount():
            self.view.setCurrentIndex(model.index(0, 0))

    def set_thumbnail_size(self, size: int) -> None:
        self.delegate.thumb_size = int(size)
        self.view.setGridSize(QSize(int(size) + 26, int(size) + 48))
        self.view.reset()

    # -- drag and drop -----------------------------------------------------
    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths = collect_dropped_paths(event.mimeData())
        if paths:
            self.pathsDropped.emit(paths)
            event.acceptProposedAction()


def collect_dropped_paths(mime) -> List[str]:
    """Expand dropped URLs into a list of image files (folders are walked)."""
    from ...utils import find_images

    found: List[str] = []
    for url in mime.urls():
        if not url.isLocalFile():
            continue
        path = Path(url.toLocalFile())
        if path.is_dir():
            found.extend(str(item) for item in find_images(path, recursive=True))
        elif path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            found.append(str(path))
    # Preserve order while removing duplicates.
    seen = set()
    unique = []
    for item in found:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique
