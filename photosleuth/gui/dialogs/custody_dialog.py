"""Chain-of-custody viewer (feature E26)."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from ... import custody
from ...i18n import tr
from .. import theme
from ..resources import app_icon


class CustodyDialog(QDialog):
    """Shows the append-only log and verifies its hash chain."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Chain of Custody"))
        self.setWindowIcon(app_icon())
        self.resize(940, 600)
        colours = theme.palette()

        self.summary = QLabel("", self)
        self.summary.setWordWrap(True)

        self.verdict = QLabel("", self)
        self.verdict.setWordWrap(True)
        font = self.verdict.font()
        font.setBold(True)
        self.verdict.setFont(font)

        self.tree = QTreeWidget(self)
        self.tree.setColumnCount(5)
        self.tree.setHeaderLabels(["Time", "Action", "File", "SHA-256", "Details"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree.header().setStretchLastSection(True)

        verify_button = QPushButton(tr("Verify Log"), self)
        verify_button.clicked.connect(self.verify)
        export_button = QPushButton("Export CSV…", self)
        export_button.clicked.connect(self.export)
        refresh_button = QPushButton("Refresh", self)
        refresh_button.clicked.connect(self.reload)
        clear_button = QPushButton("Clear log…", self)
        clear_button.clicked.connect(self.clear_log)

        controls = QHBoxLayout()
        for button in (verify_button, export_button, refresh_button):
            controls.addWidget(button)
        controls.addStretch(1)
        controls.addWidget(clear_button)

        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        buttons.rejected.connect(self.reject)

        path_label = QLabel(f"Log file: {custody.log_path()}", self)
        path_label.setWordWrap(True)
        path_label.setStyleSheet(f"color: {colours['text_muted']}; font-size: 11px;")

        layout = QVBoxLayout(self)
        layout.addWidget(self.summary)
        layout.addWidget(self.verdict)
        layout.addLayout(controls)
        layout.addWidget(self.tree, 1)
        layout.addWidget(path_label)
        layout.addWidget(buttons)

        self.reload()

    def reload(self) -> None:
        colours = theme.palette()
        entries = custody.read_log()
        self.tree.clear()

        for entry in entries:
            actor = entry.get("actor", {}) or {}
            details = entry.get("details", {}) or {}
            item = QTreeWidgetItem(
                self.tree,
                [
                    str(entry.get("timestamp", ""))[:19].replace("T", " "),
                    str(entry.get("action", "")),
                    str(entry.get("file_name", "") or Path(entry.get("file", "")).name),
                    str(entry.get("sha256", "") or "")[:24],
                    json.dumps(details, default=str)[:160],
                ],
            )
            item.setToolTip(2, str(entry.get("file", "")))
            item.setToolTip(3, str(entry.get("sha256", "") or ""))
            item.setToolTip(4, f"user: {actor.get('user', '?')}@{actor.get('host', '?')}")
            if entry.get("action") == "UNPARSEABLE-LINE":
                item.setForeground(1, QBrush(QColor(colours["danger"])))

        stats = custody.summarise(entries)
        actions = ", ".join(f"{k}×{v}" for k, v in sorted(stats["actions"].items())) or "none"
        self.summary.setText(
            f"<b>{stats['total_entries']}</b> entries across "
            f"<b>{stats['unique_files']}</b> file(s) · {actions}"
        )
        self.verify(quiet=True)

    def verify(self, quiet: bool = False) -> None:
        colours = theme.palette()
        result = custody.verify_log()
        if result["valid"]:
            self.verdict.setText(f"✓ {result['reason']} ({result['entries']} entries verified)")
            self.verdict.setStyleSheet(f"color: {colours['success']};")
        else:
            self.verdict.setText(
                f"✗ Chain broken at entry {result['broken_at']}: {result['reason']}"
            )
            self.verdict.setStyleSheet(f"color: {colours['danger']};")
        if not quiet and not result["valid"]:
            QMessageBox.warning(self, tr("Warning"), self.verdict.text())

    def export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export chain of custody", "chain_of_custody.csv",
            "Comma-separated values (*.csv)",
        )
        if not path:
            return
        try:
            written = custody.export_csv(path)
        except OSError as exc:
            QMessageBox.critical(self, tr("Error"), str(exc))
            return
        QMessageBox.information(self, tr("Export"), f"Saved to {written}")

    def clear_log(self) -> None:
        answer = QMessageBox.question(
            self, tr("Warning"),
            "Delete the whole chain-of-custody log?\n\n"
            "This cannot be undone, and it destroys the audit trail.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            custody.clear_log()
            self.reload()
