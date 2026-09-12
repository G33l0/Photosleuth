"""Forensics panel: thumbnail-vs-image comparison (feature D22)."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ...i18n import tr
from .. import theme
from ..resources import pil_to_qimage

VERDICT_STYLE = {
    "match": ("success", "Thumbnail matches the image"),
    "mismatch": ("danger", "Thumbnail does NOT match the image"),
    "inconclusive": ("warning", "Inconclusive"),
    "no-thumbnail": ("text_muted", "No embedded thumbnail"),
    "unreadable": ("warning", "Could not decode"),
}


class _Preview(QLabel):
    """A fixed-size image well with a caption underneath."""

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self.title = title
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(210, 170)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setFrameShape(QFrame.StyledPanel)
        self.clear_preview()

    def clear_preview(self) -> None:
        colours = theme.palette()
        self.setStyleSheet(
            f"background: {colours['surface_alt']}; color: {colours['text_muted']};"
            f" border: 1px solid {colours['border']}; border-radius: 6px;"
        )
        self.setText(f"{self.title}\n—")
        self.setPixmap(QPixmap())

    def show_pixmap(self, pixmap: QPixmap) -> None:
        if pixmap.isNull():
            self.clear_preview()
            return
        self.setText("")
        self.setPixmap(
            pixmap.scaled(self.size() * 0.94, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )


class ForensicsPanel(QWidget):
    """Side-by-side embedded thumbnail vs. the actual image, plus the verdict."""

    runRequested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._path: Optional[str] = None
        self._report: Optional[Dict[str, Any]] = None
        colours = theme.palette()

        self.verdict = QLabel(tr("No images loaded"), self)
        font = self.verdict.font()
        font.setPointSizeF(font.pointSizeF() + 2)
        font.setBold(True)
        self.verdict.setFont(font)

        self.run_button = QPushButton(tr("Analyze"), self)
        self.run_button.setEnabled(False)
        self.run_button.clicked.connect(
            lambda: self._path and self.runRequested.emit(self._path)
        )

        header = QHBoxLayout()
        header.addWidget(self.verdict, 1)
        header.addWidget(self.run_button)

        self.thumb_preview = _Preview("Embedded thumbnail", self)
        self.image_preview = _Preview("Actual image", self)

        previews = QGridLayout()
        previews.setSpacing(10)
        previews.addWidget(self.thumb_preview, 0, 0)
        previews.addWidget(self.image_preview, 0, 1)
        previews.addWidget(self._caption("Embedded thumbnail"), 1, 0)
        previews.addWidget(self._caption("Actual image"), 1, 1)

        self.details = QTextBrowser(self)
        self.details.setOpenExternalLinks(False)
        self.details.setMinimumHeight(120)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addLayout(header)
        layout.addLayout(previews, 1)
        layout.addWidget(self.details)

        self._colours = colours

    def _caption(self, text: str) -> QLabel:
        label = QLabel(text, self)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet(f"color: {theme.palette()['text_muted']};")
        return label

    # -- population --------------------------------------------------------
    def set_image(self, path: Optional[str], report: Optional[Dict[str, Any]] = None) -> None:
        self._path = str(path) if path else None
        self._report = report
        self.run_button.setEnabled(bool(self._path))
        self.thumb_preview.clear_preview()
        self.image_preview.clear_preview()

        if not self._path:
            self.verdict.setText(tr("No images loaded"))
            self.details.setHtml("")
            return

        self._load_previews(self._path)

        if not report:
            self.verdict.setText("Not analysed yet")
            self.verdict.setStyleSheet(f"color: {theme.palette()['text_muted']};")
            self.details.setHtml(
                f"<p style='color:{theme.palette()['text_muted']}'>"
                f"Press <b>{tr('Analyze')}</b> to compare the embedded thumbnail "
                "with the actual image.</p>"
            )
            return

        self._show_report(report)

    def _load_previews(self, path: str) -> None:
        from ...forensics import extract_embedded_thumbnail

        try:
            from PIL import Image, ImageOps

            blob = extract_embedded_thumbnail(path)
            if blob:
                with Image.open(io.BytesIO(blob)) as thumbnail:
                    thumbnail.load()
                    self.thumb_preview.show_pixmap(
                        QPixmap.fromImage(pil_to_qimage(thumbnail.convert("RGB")))
                    )
            with Image.open(path) as image:
                image = ImageOps.exif_transpose(image)
                image.thumbnail((420, 420), Image.LANCZOS)
                self.image_preview.show_pixmap(
                    QPixmap.fromImage(pil_to_qimage(image.convert("RGB")))
                )
        except Exception:
            # A preview failure must not hide the verdict.
            pass

    def _show_report(self, report: Dict[str, Any]) -> None:
        colours = theme.palette()
        check = report.get("thumbnail_check") or {}
        verdict = check.get("verdict", report.get("verdict", "no-thumbnail"))
        role, headline = VERDICT_STYLE.get(verdict, ("text_muted", verdict))
        self.verdict.setText(headline)
        self.verdict.setStyleSheet(f"color: {colours[role]};")

        rows = []
        if check.get("distance") is not None:
            rows.append(("Difference", f"{check['distance']} / 64 bits"))
        if check.get("confidence"):
            rows.append(("Confidence", check["confidence"]))
        if check.get("thumbnail_size"):
            rows.append(("Thumbnail size", "×".join(str(v) for v in check["thumbnail_size"])))
        if check.get("image_size"):
            rows.append(("Image size", "×".join(str(v) for v in check["image_size"])))
        hashes = report.get("hashes") or {}
        if hashes.get("sha256"):
            rows.append(("SHA-256", hashes["sha256"]))
        fingerprint = report.get("fingerprint") or {}
        if fingerprint.get("dhash"):
            rows.append(("Perceptual hash", fingerprint["dhash"]))

        table = "".join(
            f"<tr><td style='color:{colours['text_muted']};padding-right:14px;'>{key}</td>"
            f"<td style='font-family:monospace'>{value}</td></tr>"
            for key, value in rows
        )
        flags = "".join(
            f"<li style='color:{colours['warning']}'>{flag}</li>"
            for flag in report.get("flags") or []
        )
        notes = "".join(f"<li>{note}</li>" for note in check.get("notes") or [])

        self.details.setHtml(
            f"<div style='color:{colours['text']}'>"
            f"<table cellspacing='0'>{table}</table>"
            + (f"<p><b>Flags</b></p><ul>{flags}</ul>" if flags else "")
            + (f"<p><b>Notes</b></p><ul style='color:{colours['text_muted']}'>{notes}</ul>"
               if notes else "")
            + "</div>"
        )

    def clear(self) -> None:
        self.set_image(None)
