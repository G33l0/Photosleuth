"""Reverse image search panel (features D16 and D17).

Results arrive as URLs; their thumbnails are fetched lazily in the background
so the panel stays responsive, and nothing is fetched until the user has
consented to the search itself.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QDesktopServices, QImage, QPixmap
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ...i18n import tr
from .. import theme
from ..resources import icon

MAX_THUMBNAILS = 24


class SearchPanel(QWidget):
    """Engine picker, consent gate, results grid and entity list."""

    searchRequested = Signal(str, str)   # path, engine
    statusMessage = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._path: Optional[str] = None
        self._result: Optional[Dict[str, Any]] = None
        self._thumb_worker = None
        colours = theme.palette()

        from ...search import available_engines

        self.engine_box = QComboBox(self)
        for key, label, needs_key in available_engines():
            suffix = "  (API key)" if needs_key else "  (browser)"
            self.engine_box.addItem(f"{label}{suffix}", key)

        self.search_button = QPushButton(tr("Reverse Search"), self)
        self.search_button.setProperty("accent", True)
        self.search_button.setIcon(icon("web", colours["accent_text"]))
        self.search_button.setEnabled(False)
        self.search_button.clicked.connect(self._request)

        self.file_label = QLabel(tr("No images loaded"), self)
        self.file_label.setStyleSheet(f"color: {colours['text_muted']};")

        top = QHBoxLayout()
        top.addWidget(QLabel(tr("Reverse Search"), self))
        top.addWidget(self.engine_box, 1)
        top.addWidget(self.search_button)

        self.progress = QProgressBar(self)
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)

        self.summary = QTextBrowser(self)
        self.summary.setOpenExternalLinks(False)
        self.summary.setMinimumHeight(110)
        self.summary.anchorClicked.connect(self._open_url)

        self.results = QListWidget(self)
        self.results.setViewMode(QListWidget.IconMode)
        self.results.setIconSize(QSize(118, 118))
        self.results.setGridSize(QSize(132, 150))
        self.results.setResizeMode(QListWidget.Adjust)
        self.results.setMovement(QListWidget.Static)
        self.results.setSelectionMode(QAbstractItemView.SingleSelection)
        self.results.setSpacing(4)
        self.results.itemDoubleClicked.connect(self._open_item)
        self.results.setToolTip("Double-click a result to open it in your browser")

        splitter = QSplitter(Qt.Vertical, self)
        splitter.addWidget(self.summary)
        splitter.addWidget(self.results)
        splitter.setStretchFactor(1, 3)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addLayout(top)
        layout.addWidget(self.file_label)
        layout.addWidget(self.progress)
        layout.addWidget(splitter, 1)

        self._set_placeholder()

    # -- state -------------------------------------------------------------
    def set_image(self, path: Optional[str]) -> None:
        self._path = str(path) if path else None
        self.search_button.setEnabled(bool(self._path))
        self.file_label.setText(Path(self._path).name if self._path else tr("No images loaded"))

    def current_engine(self) -> str:
        return self.engine_box.currentData() or "google_vision"

    def _request(self) -> None:
        if not self._path:
            return
        engine = self.current_engine()

        from ...search import BROWSER_ENGINES

        if engine not in BROWSER_ENGINES:
            answer = QMessageBox.question(
                self,
                "Upload image?",
                f"This sends <b>{Path(self._path).name}</b> to a third-party service "
                f"({self.engine_box.currentText().split('  ')[0]}).<br><br>Continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                self.statusMessage.emit("Reverse search cancelled.")
                return

        self.set_busy(True)
        self.searchRequested.emit(self._path, engine)

    def set_busy(self, busy: bool) -> None:
        self.progress.setVisible(busy)
        self.search_button.setEnabled(not busy and bool(self._path))
        if busy:
            self.summary.setHtml(
                f"<p style='color:{theme.palette()['text_muted']}'>Searching…</p>"
            )
            self.results.clear()

    # -- results -----------------------------------------------------------
    def show_result(self, result: Dict[str, Any]) -> None:
        self.set_busy(False)
        self._result = result
        colours = theme.palette()
        self.results.clear()

        if result.get("mode") == "browser":
            self.summary.setHtml(
                f"<p style='color:{colours['text']}'>{result.get('instructions', '')}</p>"
                f"<p><a href='{result.get('url', '')}'>{result.get('url', '')}</a></p>"
            )
            return

        parts: List[str] = []
        if result.get("best_guess"):
            parts.append(
                f"<p><b>Best guess:</b> {', '.join(result['best_guess'])}</p>"
            )
        entities = result.get("entities") or []
        if entities:
            rows = "".join(
                f"<tr><td style='padding-right:14px'>{entity['description']}</td>"
                f"<td style='color:{colours['text_muted']}'>{entity['score']:.2f}</td></tr>"
                for entity in entities[:15]
            )
            parts.append(f"<p><b>Entities</b></p><table cellspacing='0'>{rows}</table>")
        for landmark in result.get("landmarks") or []:
            coords = ""
            if landmark.get("latitude") is not None:
                coords = f" ({landmark['latitude']:.5f}, {landmark['longitude']:.5f})"
            parts.append(f"<p><b>Landmark:</b> {landmark['description']}{coords}</p>")

        pages = result.get("pages_with_matching_images") or []
        if pages:
            links = "".join(
                f"<li><a href='{page['url']}'>{(page.get('title') or page['url'])[:110]}</a></li>"
                for page in pages[:25]
            )
            parts.append(f"<p><b>Pages with matching images ({len(pages)})</b></p><ul>{links}</ul>")

        counts = (
            f"<p style='color:{colours['text_muted']}'>"
            f"Full matches: {len(result.get('full_matching_images') or [])} · "
            f"Partial: {len(result.get('partial_matching_images') or [])} · "
            f"Similar: {len(result.get('visually_similar_images') or [])}</p>"
        )
        parts.append(counts)

        self.summary.setHtml(
            f"<div style='color:{colours['text']}'>{''.join(parts) or 'No matches found.'}</div>"
        )

        urls: List[str] = []
        for key in ("full_matching_images", "partial_matching_images", "visually_similar_images"):
            urls.extend(result.get(key) or [])
        self._populate_thumbnails(urls[:MAX_THUMBNAILS])

    def _populate_thumbnails(self, urls: List[str]) -> None:
        for url in urls:
            item = QListWidgetItem(self.results)
            item.setText(_short_host(url))
            item.setToolTip(url)
            item.setData(Qt.UserRole, url)
            item.setTextAlignment(Qt.AlignHCenter | Qt.AlignBottom)
        if urls:
            self.statusMessage.emit(f"Fetching {len(urls)} result thumbnail(s)…")

    def set_thumbnail(self, url: str, image: QImage) -> None:
        for row in range(self.results.count()):
            item = self.results.item(row)
            if item.data(Qt.UserRole) == url:
                item.setIcon(QPixmap.fromImage(image))
                return

    def show_error(self, message: str) -> None:
        self.set_busy(False)
        colours = theme.palette()
        self.summary.setHtml(
            f"<p style='color:{colours['danger']}'><b>{tr('Error')}:</b> {message}</p>"
        )
        self.results.clear()

    def _set_placeholder(self) -> None:
        colours = theme.palette()
        self.summary.setHtml(
            f"<div style='color:{colours['text_muted']}'>"
            "<p>Pick an engine and press <b>Reverse Search</b>.</p>"
            "<p><b>Google Vision</b> and <b>TinEye</b> run inside PhotoSleuth and need an API key "
            "(add one in Settings). The other engines have no public upload API, so PhotoSleuth "
            "opens their search page in your browser for you to drop the file onto.</p>"
            "<p>Nothing is uploaded until you confirm.</p></div>"
        )

    def _open_item(self, item: QListWidgetItem) -> None:
        url = item.data(Qt.UserRole)
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def _open_url(self, url: QUrl) -> None:
        QDesktopServices.openUrl(url)
        self.summary.setSource(QUrl())  # keep the browser from navigating away

    def clear(self) -> None:
        self._result = None
        self.results.clear()
        self._set_placeholder()


def _short_host(url: str) -> str:
    """Readable label for a result tile: the site it came from."""
    try:
        from urllib.parse import urlparse

        host = urlparse(url).netloc or url
    except Exception:
        host = url
    host = host[4:] if host.startswith("www.") else host
    return host[:22]
