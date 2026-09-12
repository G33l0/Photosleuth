"""Library model: the set of images loaded into the window.

One model backs the thumbnail grid, the timeline and every export, so the views
can never disagree about what is loaded.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QSize,
    QSortFilterProxyModel,
    Qt,
    Signal,
)
from PySide6.QtGui import QIcon, QImage, QPixmap

# Custom roles
PathRole = Qt.UserRole + 1
MetadataRole = Qt.UserRole + 2
HasGpsRole = Qt.UserRole + 3
FlaggedRole = Qt.UserRole + 4
DateRole = Qt.UserRole + 5
SearchTextRole = Qt.UserRole + 6
StatusRole = Qt.UserRole + 7


class ImageLibraryModel(QAbstractListModel):
    """Holds one entry per loaded image, with its metadata once analysed."""

    countChanged = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._paths: List[str] = []
        self._records: Dict[str, Dict[str, Any]] = {}
        self._thumbs: Dict[str, QPixmap] = {}
        self._status: Dict[str, str] = {}
        self._thumb_size = 160

    # -- Qt model interface ------------------------------------------------
    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._paths)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._paths):
            return None
        path = self._paths[index.row()]
        record = self._records.get(path)

        if role == Qt.DisplayRole:
            return Path(path).name
        if role == Qt.ToolTipRole:
            return self._tooltip(path, record)
        if role == Qt.DecorationRole:
            return self._thumbs.get(path)
        if role == PathRole:
            return path
        if role == MetadataRole:
            return record
        if role == HasGpsRole:
            return bool(record and record.get("gps"))
        if role == FlaggedRole:
            return bool(record and (record.get("forensics") or {}).get("flags"))
        if role == DateRole:
            return (record or {}).get("date_taken") or (record or {}).get("modified") or ""
        if role == StatusRole:
            return self._status.get(path, "pending")
        if role == SearchTextRole:
            return self._search_text(path, record)
        if role == Qt.SizeHintRole:
            return QSize(self._thumb_size + 26, self._thumb_size + 48)
        return None

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    # -- content management ------------------------------------------------
    def add_paths(self, paths) -> List[str]:
        """Add files that are not already loaded. Returns the new paths."""
        fresh = []
        for item in paths:
            text = str(Path(item))
            if text not in self._records and text not in fresh and text not in self._paths:
                fresh.append(text)
        if not fresh:
            return []
        start = len(self._paths)
        self.beginInsertRows(QModelIndex(), start, start + len(fresh) - 1)
        self._paths.extend(fresh)
        for path in fresh:
            self._status[path] = "pending"
        self.endInsertRows()
        self.countChanged.emit(len(self._paths))
        return fresh

    def set_record(self, metadata: Dict[str, Any]) -> None:
        path = str(Path(metadata.get("file", "")))
        if not path:
            return
        if path not in self._paths:
            self.add_paths([path])
        self._records[path] = metadata
        self._status[path] = "ready"
        row = self._paths.index(path)
        index = self.index(row, 0)
        self.dataChanged.emit(index, index)

    def set_failed(self, path: str, message: str) -> None:
        path = str(Path(path))
        if path in self._paths:
            self._status[path] = f"error: {message}"
            row = self._paths.index(path)
            self.dataChanged.emit(self.index(row, 0), self.index(row, 0))

    def set_thumbnail(self, path: str, image: QImage) -> None:
        path = str(Path(path))
        if path not in self._paths:
            return
        pixmap = QPixmap.fromImage(image) if isinstance(image, QImage) else image
        self._thumbs[path] = pixmap
        row = self._paths.index(path)
        self.dataChanged.emit(self.index(row, 0), self.index(row, 0), [Qt.DecorationRole])

    def remove_paths(self, paths) -> None:
        for item in list(paths):
            path = str(Path(item))
            if path not in self._paths:
                continue
            row = self._paths.index(path)
            self.beginRemoveRows(QModelIndex(), row, row)
            self._paths.pop(row)
            self._records.pop(path, None)
            self._thumbs.pop(path, None)
            self._status.pop(path, None)
            self.endRemoveRows()
        self.countChanged.emit(len(self._paths))

    def clear(self) -> None:
        self.beginResetModel()
        self._paths.clear()
        self._records.clear()
        self._thumbs.clear()
        self._status.clear()
        self.endResetModel()
        self.countChanged.emit(0)

    def set_thumbnail_size(self, size: int) -> None:
        self._thumb_size = int(size)
        if self._paths:
            self.dataChanged.emit(
                self.index(0, 0), self.index(len(self._paths) - 1, 0), [Qt.SizeHintRole]
            )

    # -- convenience accessors --------------------------------------------
    @property
    def thumbnail_size(self) -> int:
        return self._thumb_size

    def paths(self) -> List[str]:
        return list(self._paths)

    def record(self, path) -> Optional[Dict[str, Any]]:
        return self._records.get(str(Path(path)))

    def records(self) -> List[Dict[str, Any]]:
        """Analysed records, in load order."""
        return [self._records[p] for p in self._paths if p in self._records]

    def geotagged(self) -> List[Dict[str, Any]]:
        return [record for record in self.records() if record.get("gps")]

    def pending(self) -> List[str]:
        return [p for p in self._paths if self._status.get(p) == "pending"]

    def index_of(self, path) -> QModelIndex:
        text = str(Path(path))
        if text in self._paths:
            return self.index(self._paths.index(text), 0)
        return QModelIndex()

    # -- helpers -----------------------------------------------------------
    def _tooltip(self, path: str, record: Optional[Dict[str, Any]]) -> str:
        lines = [f"<b>{Path(path).name}</b>", f"<span>{path}</span>"]
        if not record:
            status = self._status.get(path, "pending")
            lines.append("Analysing…" if status == "pending" else status)
            return "<br>".join(lines)
        lines.append(f"{record.get('size_human', '')} · {record.get('modified', '')[:19]}")
        if record.get("date_taken"):
            lines.append(f"Taken: {record['date_taken']}")
        gps = record.get("gps")
        if gps:
            lines.append(f"GPS: {gps['latitude']:.5f}, {gps['longitude']:.5f}")
        if record.get("location"):
            lines.append(str(record["location"])[:90])
        flags = (record.get("forensics") or {}).get("flags") or []
        for flag in flags:
            lines.append(f"<span>⚑ {flag}</span>")
        return "<br>".join(lines)

    def _search_text(self, path: str, record: Optional[Dict[str, Any]]) -> str:
        """One flat string per image, so the filter box searches everything."""
        parts = [path, Path(path).name]
        if record:
            parts.append(str(record.get("location", "")))
            parts.append(str(record.get("date_taken", "")))
            for key, value in (record.get("summary") or {}).items():
                parts.append(f"{key} {value}")
            for key, value in (record.get("exif") or {}).items():
                parts.append(f"{key} {value}")
            gps = record.get("gps")
            if gps:
                parts.append(f"{gps['latitude']:.6f} {gps['longitude']:.6f} gps geotagged")
            for flag in (record.get("forensics") or {}).get("flags") or []:
                parts.append(flag)
        return "\n".join(parts).lower()


class LibraryFilterProxy(QSortFilterProxyModel):
    """Live text filter plus quick toggles for geotagged / flagged images."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._text = ""
        self._only_gps = False
        self._only_flagged = False
        self.setDynamicSortFilter(True)

    def set_text(self, text: str) -> None:
        self._text = (text or "").strip().lower()
        self._invalidate()

    def set_only_geotagged(self, enabled: bool) -> None:
        self._only_gps = bool(enabled)
        self._invalidate()

    def set_only_flagged(self, enabled: bool) -> None:
        self._only_flagged = bool(enabled)
        self._invalidate()

    def _invalidate(self) -> None:
        """Re-run the filter.

        ``invalidateFilter()`` and its row/column variants are all deprecated
        in Qt 6.11; ``invalidate()`` is the supported call.
        """
        self.invalidate()

    def filterAcceptsRow(self, row: int, parent: QModelIndex) -> bool:
        model = self.sourceModel()
        if model is None:
            return True
        index = model.index(row, 0, parent)
        if self._only_gps and not model.data(index, HasGpsRole):
            return False
        if self._only_flagged and not model.data(index, FlaggedRole):
            return False
        if not self._text:
            return True
        haystack = model.data(index, SearchTextRole) or ""
        # Space-separated terms are ANDed, which is what people expect.
        return all(term in haystack for term in self._text.split())
