"""About box and the update checker's result dialog (feature F31)."""

from __future__ import annotations

import platform
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from ... import __author__, __version__, config as config_module
from ...i18n import tr
from .. import theme
from ..resources import app_icon, logo_pixmap


class AboutDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("About"))
        self.setWindowIcon(app_icon())
        self.resize(520, 420)
        colours = theme.palette()

        logo = QLabel(self)
        logo.setPixmap(logo_pixmap(96))
        logo.setAlignment(Qt.AlignCenter)

        title = QLabel(f"<h2 style='margin-bottom:2px'>PhotoSleuth {__version__}</h2>", self)
        title.setAlignment(Qt.AlignCenter)

        subtitle = QLabel(
            f"<span style='color:{colours['text_muted']}'>"
            f"Image metadata &amp; location analyzer<br>by {__author__}</span>",
            self,
        )
        subtitle.setAlignment(Qt.AlignCenter)

        try:
            from PySide6 import __version__ as qt_version
        except ImportError:
            qt_version = "?"

        details = QTextBrowser(self)
        details.setOpenExternalLinks(True)
        details.setHtml(
            f"""
            <div style='color:{colours['text']}'>
            <table cellspacing='0'>
              <tr><td style='color:{colours['text_muted']};padding-right:12px'>Python</td>
                  <td>{sys.version.split()[0]}</td></tr>
              <tr><td style='color:{colours['text_muted']};padding-right:12px'>PySide6</td>
                  <td>{qt_version}</td></tr>
              <tr><td style='color:{colours['text_muted']};padding-right:12px'>Platform</td>
                  <td>{platform.platform()}</td></tr>
              <tr><td style='color:{colours['text_muted']};padding-right:12px'>Settings</td>
                  <td>{config_module.config_home()}</td></tr>
              <tr><td style='color:{colours['text_muted']};padding-right:12px'>Mode</td>
                  <td>{'portable' if config_module.is_portable() else 'installed'}</td></tr>
            </table>
            <p style='color:{colours['text_muted']}'>Released under the MIT licence.
            Geocoding by OpenStreetMap Nominatim. Use only on images you own or
            have permission to analyse.</p>
            </div>
            """
        )

        self.update_button = QPushButton(tr("Check for Updates…"), self)
        self.update_button.clicked.connect(self._check_updates)

        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        buttons.rejected.connect(self.reject)

        row = QHBoxLayout()
        row.addWidget(self.update_button)
        row.addStretch(1)
        row.addWidget(buttons)

        layout = QVBoxLayout(self)
        layout.addWidget(logo)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(details, 1)
        layout.addLayout(row)

    def _check_updates(self) -> None:
        self.update_button.setEnabled(False)
        self.update_button.setText("Checking…")
        from ...updates import check_for_updates

        info = check_for_updates()
        self.update_button.setEnabled(True)
        self.update_button.setText(tr("Check for Updates…"))
        UpdateDialog(info, self).exec()


class UpdateDialog(QDialog):
    """Reports the outcome of an update check."""

    def __init__(self, info, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Check for Updates…"))
        self.setWindowIcon(app_icon())
        self.resize(460, 0)
        self.info = info
        colours = theme.palette()

        headline = QLabel(info.message, self)
        headline.setWordWrap(True)
        font = headline.font()
        font.setBold(True)
        headline.setFont(font)
        if info.available:
            headline.setStyleSheet(f"color: {colours['accent']};")
        elif info.error:
            headline.setStyleSheet(f"color: {colours['warning']};")

        layout = QVBoxLayout(self)
        layout.addWidget(headline)

        if info.notes:
            notes = QTextBrowser(self)
            notes.setPlainText(info.notes[:4000])
            notes.setMaximumHeight(220)
            layout.addWidget(notes)

        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        buttons.rejected.connect(self.reject)

        if info.available and info.url:
            download = QPushButton("Open download page", self)
            download.setProperty("accent", True)
            download.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(info.url)))
            buttons.addButton(download, QDialogButtonBox.ActionRole)

        layout.addWidget(buttons)
