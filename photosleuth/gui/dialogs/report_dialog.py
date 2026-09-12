"""Export dialog: CSV, JSON, HTML, PDF and maps (features E23, E24, E25, B9)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from ... import config as config_module
from ...i18n import tr
from .. import theme
from ..resources import app_icon

FORMATS = [
    ("pdf", "PDF report", "PDF document (*.pdf)", ".pdf"),
    ("html", "HTML report", "Web page (*.html)", ".html"),
    ("csv", "CSV table", "Comma-separated values (*.csv)", ".csv"),
    ("json", "JSON data", "JSON file (*.json)", ".json"),
    ("map_html", "Map (HTML)", "Web page (*.html)", ".html"),
    ("map_png", "Map (PNG image)", "PNG image (*.png)", ".png"),
]


class ReportDialog(QDialog):
    """Pick a format and destination, then export."""

    exported = Signal(str, str)   # format, path

    def __init__(self, records: List[Dict[str, Any]], parent=None, selected_only: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Export Report…"))
        self.setWindowIcon(app_icon())
        self.records = [record for record in records if record]
        self.resize(600, 0)

        config = config_module.load_config()
        self.report_settings = config.get("reports", {})
        colours = theme.palette()

        geotagged = sum(1 for record in self.records if record.get("gps"))
        heading = QLabel(
            f"Exporting <b>{len(self.records)}</b> image(s)"
            + (" (current selection)" if selected_only else "")
            + f" · {geotagged} geotagged",
            self,
        )

        # --- format ------------------------------------------------------
        format_group = QGroupBox("Format", self)
        format_layout = QVBoxLayout(format_group)
        self.format_buttons: Dict[str, QRadioButton] = {}
        for key, label, _filter, _suffix in FORMATS:
            button = QRadioButton(label, format_group)
            format_layout.addWidget(button)
            self.format_buttons[key] = button

        # --- destination --------------------------------------------------
        self.path_edit = QLineEdit(self)
        browse = QPushButton("Browse…", self)
        browse.clicked.connect(self._browse)
        path_row = QHBoxLayout()
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(browse)

        self.title_edit = QLineEdit(self)
        self.title_edit.setText("PhotoSleuth Report")

        self.template_box = QComboBox(self)
        from ...reports import available_templates

        for name in available_templates(self.report_settings.get("custom_template_dir") or None):
            self.template_box.addItem(name, name)
        index = self.template_box.findData(self.report_settings.get("template", "default"))
        if index >= 0:
            self.template_box.setCurrentIndex(index)

        self.thumbnails_check = QCheckBox("Include thumbnails", self)
        self.thumbnails_check.setChecked(bool(self.report_settings.get("include_thumbnails", True)))
        self.forensics_check = QCheckBox("Include forensic findings", self)
        self.forensics_check.setChecked(bool(self.report_settings.get("include_forensics", True)))
        self.custody_check = QCheckBox("Include chain-of-custody log", self)
        self.custody_check.setChecked(bool(self.report_settings.get("include_custody", False)))

        self.options_group = QGroupBox("Report options", self)
        options_form = QFormLayout(self.options_group)
        options_form.addRow("Title", self.title_edit)
        options_form.addRow("Template", self.template_box)
        options_form.addRow("", self.thumbnails_check)
        options_form.addRow("", self.forensics_check)
        options_form.addRow("", self.custody_check)

        destination_group = QGroupBox("Destination", self)
        destination_form = QFormLayout(destination_group)
        destination_form.addRow("Save to", path_row)

        self.status = QLabel("", self)
        self.status.setWordWrap(True)
        self.status.setStyleSheet(f"color: {colours['text_muted']};")

        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel, self)
        self.buttons.button(QDialogButtonBox.Save).setText(tr("Export"))
        self.buttons.button(QDialogButtonBox.Save).setProperty("accent", True)
        self.buttons.accepted.connect(self._export)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(format_group)
        layout.addWidget(self.options_group)
        layout.addWidget(destination_group)
        layout.addWidget(self.status)
        layout.addWidget(self.buttons)

        self.result_path: str = ""

        # Wiring happens last: every widget the handler touches now exists.
        for button in self.format_buttons.values():
            button.toggled.connect(self._format_changed)
        self.format_buttons["pdf"].setChecked(True)
        self._format_changed()

    # -- helpers -----------------------------------------------------------
    def current_format(self) -> str:
        for key, button in self.format_buttons.items():
            if button.isChecked():
                return key
        return "pdf"

    def _format_spec(self):
        key = self.current_format()
        for item in FORMATS:
            if item[0] == key:
                return item
        return FORMATS[0]

    def _format_changed(self) -> None:
        if not hasattr(self, "options_group"):
            return
        key, label, _filter, suffix = self._format_spec()
        self.options_group.setEnabled(key in ("pdf", "html"))

        needs_gps = key in ("map_html", "map_png")
        geotagged = sum(1 for record in self.records if record.get("gps"))
        save_button = self.buttons.button(QDialogButtonBox.Save)
        if needs_gps and geotagged == 0:
            self.status.setText("⚠ No geotagged images, so a map cannot be produced.")
            if save_button:
                save_button.setEnabled(False)
        else:
            self.status.setText("")
            if save_button:
                save_button.setEnabled(True)

        current = self.path_edit.text().strip()
        if current:
            self.path_edit.setText(str(Path(current).with_suffix(suffix)))

    def _browse(self) -> None:
        key, label, file_filter, suffix = self._format_spec()
        suggestion = self.path_edit.text().strip() or f"photosleuth_{key}{suffix}"
        path, _ = QFileDialog.getSaveFileName(self, tr("Export"), suggestion, file_filter)
        if path:
            if not Path(path).suffix:
                path += suffix
            self.path_edit.setText(path)

    # -- export ------------------------------------------------------------
    def _export(self) -> None:
        key, label, _filter, suffix = self._format_spec()
        target = self.path_edit.text().strip()
        if not target:
            self._browse()
            target = self.path_edit.text().strip()
        if not target:
            return
        if not Path(target).suffix:
            target += suffix

        branding = dict(self.report_settings)
        custody_entries = None
        if self.custody_check.isChecked():
            from ... import custody as custody_module

            custody_entries = custody_module.read_log(limit=500)

        forensics_map = {}
        if self.forensics_check.isChecked():
            forensics_map = {
                record["file"]: record["forensics"]
                for record in self.records
                if record.get("forensics")
            }

        try:
            path = self._run_export(key, target, branding, forensics_map, custody_entries)
        except Exception as exc:  # noqa: BLE001 - surfaced to the user
            QMessageBox.critical(self, tr("Error"), f"Export failed:\n\n{exc}")
            return

        try:
            from ... import custody as custody_module

            custody_module.record("export", path, {"format": key, "images": len(self.records)})
        except Exception:
            pass

        self.result_path = str(path)
        self.exported.emit(key, str(path))
        self.accept()

    def _run_export(self, key: str, target: str, branding, forensics_map, custody_entries):
        from ... import reports

        if key == "csv":
            return reports.export_csv(self.records, target)
        if key == "json":
            return reports.export_json(self.records, target)
        if key == "map_html":
            return reports.generate_map(self.records, target)
        if key == "map_png":
            return reports.render_static_map(self.records, target)

        common = dict(
            title=self.title_edit.text().strip() or "PhotoSleuth Report",
            branding=branding,
            forensics=forensics_map,
            custody_entries=custody_entries,
            template=self.template_box.currentData() or "default",
            custom_dir=branding.get("custom_template_dir") or None,
            include_thumbnails=self.thumbnails_check.isChecked(),
        )
        if key == "html":
            return reports.export_html(self.records, target, **common)
        return reports.export_pdf(self.records, target, **common)
