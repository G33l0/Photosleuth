"""Settings dialog (feature F30), including Windows integration (F32/F37)."""

from __future__ import annotations

import sys
from typing import Any, Dict

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ... import config as config_module
from ...i18n import BUILTIN_LANGUAGES, available_languages, tr
from .. import theme
from ..resources import app_icon


class _PathPicker(QWidget):
    """A line edit with a Browse button."""

    def __init__(self, parent=None, directory: bool = False, filters: str = "") -> None:
        super().__init__(parent)
        self.directory = directory
        self.filters = filters
        self.edit = QLineEdit(self)
        button = QPushButton("Browse…", self)
        button.clicked.connect(self._browse)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.edit, 1)
        layout.addWidget(button)

    def _browse(self) -> None:
        if self.directory:
            path = QFileDialog.getExistingDirectory(self, "Choose a folder", self.edit.text())
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, "Choose a file", self.edit.text(), self.filters or "All files (*)"
            )
        if path:
            self.edit.setText(path)

    def text(self) -> str:
        return self.edit.text().strip()

    def setText(self, value: str) -> None:
        self.edit.setText(value or "")


class SettingsDialog(QDialog):
    """Edits every persisted preference."""

    settingsChanged = Signal(dict)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Settings"))
        self.setWindowIcon(app_icon())
        self.resize(660, 560)

        self.config: Dict[str, Any] = config_module.load_config()

        self.tabs = QTabWidget(self)
        self.tabs.addTab(self._appearance_tab(), tr("View"))
        self.tabs.addTab(self._analysis_tab(), tr("Analyze"))
        self.tabs.addTab(self._keys_tab(), tr("Reverse Search"))
        self.tabs.addTab(self._reports_tab(), tr("Reports"))
        self.tabs.addTab(self._network_tab(), "Network")
        self.tabs.addTab(self._system_tab(), "System")

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel | QDialogButtonBox.RestoreDefaults,
            self,
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self._restore_defaults)
        buttons.button(QDialogButtonBox.Save).setProperty("accent", True)

        path_label = QLabel(f"Settings file: {config_module.config_path()}", self)
        path_label.setWordWrap(True)
        path_label.setStyleSheet(f"color: {theme.palette()['text_muted']}; font-size: 11px;")

        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(path_label)
        layout.addWidget(buttons)

        self._load()

    # -- tabs --------------------------------------------------------------
    def _appearance_tab(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)

        self.theme_box = QComboBox(page)
        for label, value in ((tr("System"), "system"), (tr("Light"), "light"), (tr("Dark"), "dark")):
            self.theme_box.addItem(label, value)

        self.language_box = QComboBox(page)
        self.language_box.addItem("System default", "system")
        for code, name in available_languages():
            self.language_box.addItem(f"{name} ({code})", code)

        self.thumb_size = QSpinBox(page)
        self.thumb_size.setRange(96, 320)
        self.thumb_size.setSingleStep(16)
        self.thumb_size.setSuffix(" px")

        self.restore_session = QCheckBox("Restore the last session on startup", page)
        self.confirm_destructive = QCheckBox("Confirm before destructive actions", page)

        form.addRow("Theme", self.theme_box)
        form.addRow(tr("Language"), self.language_box)
        form.addRow("Thumbnail size", self.thumb_size)
        form.addRow("", self.restore_session)
        form.addRow("", self.confirm_destructive)
        return page

    def _analysis_tab(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)

        geo_group = QGroupBox("Geocoding", page)
        geo_form = QFormLayout(geo_group)
        self.geocode_enabled = QCheckBox("Look up addresses for GPS coordinates", geo_group)
        self.geocode_delay = QDoubleSpinBox(geo_group)
        self.geocode_delay.setRange(0.0, 10.0)
        self.geocode_delay.setSingleStep(0.25)
        self.geocode_delay.setSuffix(" s")
        self.geocode_delay.setToolTip(
            "Nominatim's usage policy allows one request per second. Lowering this risks a block."
        )
        self.geocode_timeout = QSpinBox(geo_group)
        self.geocode_timeout.setRange(1, 60)
        self.geocode_timeout.setSuffix(" s")
        self.geocode_cache = QCheckBox("Cache looked-up addresses between runs", geo_group)
        geo_form.addRow("", self.geocode_enabled)
        geo_form.addRow("Minimum delay", self.geocode_delay)
        geo_form.addRow("Timeout", self.geocode_timeout)
        geo_form.addRow("", self.geocode_cache)

        auto_group = QGroupBox("Workflow", page)
        auto_form = QFormLayout(auto_group)
        self.auto_analyze = QCheckBox("Analyse images as soon as they are opened", auto_group)
        auto_form.addRow("", self.auto_analyze)

        privacy_group = QGroupBox("Metadata stripping", page)
        privacy_form = QFormLayout(privacy_group)
        self.strip_suffix = QLineEdit(privacy_group)
        self.strip_overwrite = QCheckBox("Overwrite originals instead of writing a copy", privacy_group)
        privacy_form.addRow("Output suffix", self.strip_suffix)
        privacy_form.addRow("", self.strip_overwrite)

        custody_group = QGroupBox(tr("Chain of Custody"), page)
        custody_form = QFormLayout(custody_group)
        self.custody_enabled = QCheckBox("Log every action with file hashes", custody_group)
        self.custody_path = _PathPicker(custody_group, directory=False)
        custody_form.addRow("", self.custody_enabled)
        custody_form.addRow("Log file", self.custody_path)

        layout.addWidget(geo_group)
        layout.addWidget(auto_group)
        layout.addWidget(privacy_group)
        layout.addWidget(custody_group)
        layout.addStretch(1)
        return page

    def _keys_tab(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)

        keys_group = QGroupBox("API keys", page)
        form = QFormLayout(keys_group)
        self.vision_key = QLineEdit(keys_group)
        self.vision_key.setEchoMode(QLineEdit.Password)
        self.vision_key.setPlaceholderText("Google Cloud Vision API key")
        self.tineye_key = QLineEdit(keys_group)
        self.tineye_key.setEchoMode(QLineEdit.Password)
        self.tineye_key.setPlaceholderText("TinEye API key (paid product)")

        show_keys = QCheckBox("Show keys", keys_group)
        show_keys.toggled.connect(
            lambda on: [
                widget.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password)
                for widget in (self.vision_key, self.tineye_key)
            ]
        )

        self.default_engine = QComboBox(keys_group)
        from ...search import available_engines

        for key, label, _needs in available_engines():
            self.default_engine.addItem(label, key)

        form.addRow("Google Vision", self.vision_key)
        form.addRow("TinEye", self.tineye_key)
        form.addRow("", show_keys)
        form.addRow("Default engine", self.default_engine)

        note = QLabel(
            "Keys are stored in plain text in your settings file, the same way the CLI stores "
            "them. Engines marked “browser” need no key — PhotoSleuth opens their page for you.",
            page,
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {theme.palette()['text_muted']};")

        layout.addWidget(keys_group)
        layout.addWidget(note)
        layout.addStretch(1)
        return page

    def _reports_tab(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)

        branding = QGroupBox("Branding", page)
        form = QFormLayout(branding)
        self.org_name = QLineEdit(branding)
        self.report_author = QLineEdit(branding)
        self.accent_colour = QLineEdit(branding)
        self.accent_colour.setPlaceholderText("#1694b2")
        self.report_logo = _PathPicker(branding, filters="Images (*.png *.jpg *.jpeg *.bmp)")
        self.footer_note = QLineEdit(branding)
        form.addRow("Organisation", self.org_name)
        form.addRow("Author", self.report_author)
        form.addRow("Accent colour", self.accent_colour)
        form.addRow("Logo", self.report_logo)
        form.addRow("Footer note", self.footer_note)

        templates = QGroupBox("Templates", page)
        template_form = QFormLayout(templates)
        self.template_box = QComboBox(templates)
        self.custom_template_dir = _PathPicker(templates, directory=True)
        self.custom_template_dir.edit.textChanged.connect(self._refresh_templates)
        template_form.addRow("Default template", self.template_box)
        template_form.addRow("Custom template folder", self.custom_template_dir)

        contents = QGroupBox("Include in reports", page)
        contents_layout = QVBoxLayout(contents)
        self.include_thumbnails = QCheckBox("Image thumbnails", contents)
        self.include_map = QCheckBox("Map of geotagged images", contents)
        self.include_forensics = QCheckBox("Forensic findings", contents)
        self.include_custody = QCheckBox("Chain-of-custody log", contents)
        for widget in (self.include_thumbnails, self.include_map,
                       self.include_forensics, self.include_custody):
            contents_layout.addWidget(widget)

        layout.addWidget(branding)
        layout.addWidget(templates)
        layout.addWidget(contents)
        layout.addStretch(1)
        return page

    def _network_tab(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        colours = theme.palette()

        mode_group = QGroupBox("Internet access", page)
        mode_layout = QVBoxLayout(mode_group)
        self.network_mode = QComboBox(mode_group)
        self.network_mode.addItem("Use the internet when it is available", "automatic")
        self.network_mode.addItem("Work offline — never use the internet", "offline")
        mode_layout.addWidget(self.network_mode)

        explanation = QLabel(
            "PhotoSleuth does almost everything without a connection: metadata, "
            "forensics, EXIF checks, shadow and landmark geolocation, measurements "
            "and every report format.<br><br>"
            "The internet is used only for <b>address lookup</b>, <b>map tiles</b>, "
            "<b>reverse image search</b> and <b>update checks</b>. Offline, cached "
            "addresses and map tiles are still used and nothing stalls waiting for "
            "a connection.<br><br>"
            "<b>Work offline</b> is also a privacy setting: with it on, no image, "
            "coordinate or query leaves this machine for any reason.",
            mode_group,
        )
        explanation.setWordWrap(True)
        explanation.setStyleSheet(f"color: {colours['text_muted']};")
        mode_layout.addWidget(explanation)

        self.warn_before_upload = QCheckBox(
            "Ask before sending an image to a web service", mode_group
        )
        mode_layout.addWidget(self.warn_before_upload)

        cache_group = QGroupBox("Offline map cache", page)
        cache_layout = QVBoxLayout(cache_group)
        self.cache_label = QLabel("", cache_group)
        self.cache_label.setWordWrap(True)
        cache_layout.addWidget(self.cache_label)

        cache_hint = QLabel(
            "Map tiles you have already viewed are kept on disk and redrawn when "
            "you are offline. Panning around an area while connected is enough to "
            "make it available later.",
            cache_group,
        )
        cache_hint.setWordWrap(True)
        cache_hint.setStyleSheet(f"color: {colours['text_muted']};")
        cache_layout.addWidget(cache_hint)

        buttons = QHBoxLayout()
        refresh = QPushButton("Refresh", cache_group)
        refresh.clicked.connect(self._refresh_cache_size)
        clear_tiles = QPushButton("Clear map cache", cache_group)
        clear_tiles.clicked.connect(self._clear_tile_cache)
        clear_geo = QPushButton("Clear address cache", cache_group)
        clear_geo.clicked.connect(self._clear_geocode_cache)
        for button in (refresh, clear_tiles, clear_geo):
            buttons.addWidget(button)
        buttons.addStretch(1)
        cache_layout.addLayout(buttons)

        layout.addWidget(mode_group)
        layout.addWidget(cache_group)
        layout.addStretch(1)
        self._refresh_cache_size()
        return page

    def _refresh_cache_size(self) -> None:
        try:
            from ..widgets.map_widget import shared_tile_cache

            megabytes = shared_tile_cache().disk_usage_mb()
        except Exception:
            megabytes = 0.0
        self.cache_label.setText(f"Cached map tiles: <b>{megabytes:.1f} MB</b>")

    def _clear_tile_cache(self) -> None:
        from ..widgets.map_widget import shared_tile_cache

        removed = shared_tile_cache().clear_disk()
        self._refresh_cache_size()
        QMessageBox.information(self, tr("Settings"), f"Removed {removed} cached tile(s).")

    def _clear_geocode_cache(self) -> None:
        from ...utils import default_cache

        default_cache().clear()
        QMessageBox.information(self, tr("Settings"), "Cached addresses cleared.")

    def _system_tab(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)

        updates = QGroupBox("Updates", page)
        update_form = QFormLayout(updates)
        self.check_updates = QCheckBox("Check for new versions on startup", updates)
        self.update_repo = QLineEdit(updates)
        update_form.addRow("", self.check_updates)
        update_form.addRow("GitHub repository", self.update_repo)

        self.integration_group = QGroupBox("Windows integration", page)
        integration_layout = QVBoxLayout(self.integration_group)
        self.explorer_button = QPushButton("Add “Analyze with PhotoSleuth” to Explorer", page)
        self.explorer_remove = QPushButton("Remove Explorer entry", page)
        self.assoc_button = QPushButton("Register PhotoSleuth as an image handler", page)
        self.assoc_remove = QPushButton("Unregister image handler", page)
        for button in (self.explorer_button, self.explorer_remove,
                       self.assoc_button, self.assoc_remove):
            integration_layout.addWidget(button)
        self.explorer_button.clicked.connect(lambda: self._integration("explorer", True))
        self.explorer_remove.clicked.connect(lambda: self._integration("explorer", False))
        self.assoc_button.clicked.connect(lambda: self._integration("assoc", True))
        self.assoc_remove.clicked.connect(lambda: self._integration("assoc", False))

        if not sys.platform.startswith("win"):
            self.integration_group.setEnabled(False)
            self.integration_group.setToolTip("Available on Windows only.")

        portable = QGroupBox("Storage", page)
        portable_layout = QVBoxLayout(portable)
        mode = "portable" if config_module.is_portable() else "per-user"
        portable_layout.addWidget(QLabel(f"Mode: <b>{mode}</b>", portable))
        portable_layout.addWidget(QLabel(f"Data folder: {config_module.config_home()}", portable))
        hint = QLabel(
            "To run portably, place an empty file named <code>portable.txt</code> next to "
            "PhotoSleuth.exe — settings, cache and logs then live beside the program.",
            portable,
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {theme.palette()['text_muted']};")
        portable_layout.addWidget(hint)

        layout.addWidget(updates)
        layout.addWidget(self.integration_group)
        layout.addWidget(portable)
        layout.addStretch(1)
        return page

    # -- load / save -------------------------------------------------------
    def _load(self) -> None:
        config = self.config
        ui = config.get("ui", {})
        geo = config.get("geocoding", {})
        privacy = config.get("privacy", {})
        keys = config.get("api_keys", {})
        reports = config.get("reports", {})
        updates = config.get("updates", {})
        custody = config.get("custody", {})
        network = config.get("network", {})

        self._select(self.theme_box, ui.get("theme", "system"))
        self._select(self.language_box, ui.get("language", "system"))
        self.thumb_size.setValue(int(ui.get("thumbnail_size", 160)))
        self.restore_session.setChecked(bool(ui.get("restore_session", True)))
        self.confirm_destructive.setChecked(bool(ui.get("confirm_destructive", True)))
        self.auto_analyze.setChecked(bool(ui.get("auto_analyze_on_open", True)))

        self.geocode_enabled.setChecked(bool(geo.get("enabled", True)))
        self.geocode_delay.setValue(float(geo.get("min_delay_seconds", 1.0)))
        self.geocode_timeout.setValue(int(geo.get("timeout_seconds", 10)))
        self.geocode_cache.setChecked(bool(geo.get("cache_enabled", True)))

        self.strip_suffix.setText(privacy.get("output_suffix", "_clean"))
        self.strip_overwrite.setChecked(bool(privacy.get("overwrite", False)))

        self.custody_enabled.setChecked(bool(custody.get("enabled", True)))
        self.custody_path.setText(custody.get("log_file", ""))

        self.vision_key.setText(keys.get("google_vision", ""))
        self.tineye_key.setText(keys.get("tineye", ""))
        self._select(self.default_engine, config.get("default_search_engine", "google_vision"))

        self.org_name.setText(reports.get("organisation", ""))
        self.report_author.setText(reports.get("author", ""))
        self.accent_colour.setText(reports.get("accent_colour", "#1694b2"))
        self.report_logo.setText(reports.get("logo_path", ""))
        self.footer_note.setText(reports.get("footer_note", ""))
        self.custom_template_dir.setText(reports.get("custom_template_dir", ""))
        self._refresh_templates()
        self._select(self.template_box, reports.get("template", "default"))
        self.include_thumbnails.setChecked(bool(reports.get("include_thumbnails", True)))
        self.include_map.setChecked(bool(reports.get("include_map", True)))
        self.include_forensics.setChecked(bool(reports.get("include_forensics", True)))
        self.include_custody.setChecked(bool(reports.get("include_custody", False)))

        self._select(self.network_mode, network.get("mode", "automatic"))
        self.warn_before_upload.setChecked(bool(network.get("warn_before_upload", True)))

        self.check_updates.setChecked(bool(updates.get("check_on_startup", False)))
        self.update_repo.setText(updates.get("repository", "G33l0/Photosleuth"))

    def _refresh_templates(self) -> None:
        from ...reports import available_templates

        current = self.template_box.currentData()
        self.template_box.clear()
        for name in available_templates(self.custom_template_dir.text() or None):
            self.template_box.addItem(name, name)
        if current:
            self._select(self.template_box, current)

    @staticmethod
    def _select(box: QComboBox, value) -> None:
        index = box.findData(value)
        box.setCurrentIndex(index if index >= 0 else 0)

    def _save(self) -> None:
        accent = self.accent_colour.text().strip() or "#1694b2"
        if not accent.startswith("#") or len(accent) not in (4, 7):
            QMessageBox.warning(
                self, tr("Warning"),
                "The accent colour must be a hex value such as #1694b2.",
            )
            return

        payload = {
            "default_search_engine": self.default_engine.currentData() or "google_vision",
            "api_keys": {
                "google_vision": self.vision_key.text().strip(),
                "tineye": self.tineye_key.text().strip(),
            },
            "privacy": {
                "output_suffix": self.strip_suffix.text().strip() or "_clean",
                "overwrite": self.strip_overwrite.isChecked(),
            },
            "geocoding": {
                "enabled": self.geocode_enabled.isChecked(),
                "min_delay_seconds": float(self.geocode_delay.value()),
                "timeout_seconds": int(self.geocode_timeout.value()),
                "cache_enabled": self.geocode_cache.isChecked(),
            },
            "ui": {
                "theme": self.theme_box.currentData() or "system",
                "language": self.language_box.currentData() or "system",
                "thumbnail_size": int(self.thumb_size.value()),
                "restore_session": self.restore_session.isChecked(),
                "confirm_destructive": self.confirm_destructive.isChecked(),
                "auto_analyze_on_open": self.auto_analyze.isChecked(),
            },
            "custody": {
                "enabled": self.custody_enabled.isChecked(),
                "log_file": self.custody_path.text(),
            },
            "reports": {
                "template": self.template_box.currentData() or "default",
                "custom_template_dir": self.custom_template_dir.text(),
                "organisation": self.org_name.text().strip(),
                "author": self.report_author.text().strip(),
                "logo_path": self.report_logo.text(),
                "accent_colour": accent,
                "footer_note": self.footer_note.text().strip(),
                "include_thumbnails": self.include_thumbnails.isChecked(),
                "include_map": self.include_map.isChecked(),
                "include_forensics": self.include_forensics.isChecked(),
                "include_custody": self.include_custody.isChecked(),
            },
            "network": {
                "mode": self.network_mode.currentData() or "automatic",
                "warn_before_upload": self.warn_before_upload.isChecked(),
            },
            "updates": {
                "check_on_startup": self.check_updates.isChecked(),
                "repository": self.update_repo.text().strip() or "G33l0/Photosleuth",
            },
        }

        try:
            config_module.update_config(**payload)
        except OSError as exc:
            QMessageBox.critical(self, tr("Error"), f"Could not save settings:\n{exc}")
            return

        # Geocoding settings are cached in module state; drop it so the new
        # delay and cache flag take effect immediately.
        from ...connectivity import monitor
        from ...core import reset_geocoder
        from ...utils import reset_default_cache

        reset_geocoder()
        reset_default_cache()
        # The network mode may have changed; drop the cached probe result.
        monitor().invalidate()

        self.settingsChanged.emit(payload)
        self.accept()

    def _restore_defaults(self) -> None:
        answer = QMessageBox.question(
            self, tr("Settings"),
            "Reset every setting to its default? Saved API keys are kept.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        import copy

        keys = self.config.get("api_keys", {})
        self.config = copy.deepcopy(config_module.DEFAULT_CONFIG)
        self.config["api_keys"] = keys
        self._load()

    def _integration(self, kind: str, install: bool) -> None:
        from ...integration import (
            register_explorer_menu,
            register_image_association,
            unregister_explorer_menu,
            unregister_image_association,
        )

        actions = {
            ("explorer", True): register_explorer_menu,
            ("explorer", False): unregister_explorer_menu,
            ("assoc", True): register_image_association,
            ("assoc", False): unregister_image_association,
        }
        try:
            message = actions[(kind, install)]()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, tr("Error"), str(exc))
            return
        QMessageBox.information(self, tr("Settings"), message)
