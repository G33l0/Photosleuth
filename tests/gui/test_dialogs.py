"""Dialogs: compare, geotag, settings, report, custody, about."""

import json

import pytest

from photosleuth.core import extract_metadata


@pytest.fixture
def records(image_ne, image_sw):
    return [extract_metadata(path, geocode=False) for path in (image_ne, image_sw)]


# --- compare ----------------------------------------------------------------

def test_compare_counts_differences(themed, pump, records):
    from photosleuth.gui.dialogs.compare_dialog import CompareDialog

    dialog = CompareDialog(records[0], records[1])
    dialog.show()
    pump()
    differences_only = dialog.tree.topLevelItemCount()
    assert differences_only > 0
    assert "difference(s)" in dialog.counter.text()

    dialog.differences_only.setChecked(False)
    pump()
    assert dialog.tree.topLevelItemCount() > differences_only


def test_compare_identical_images(themed, pump, tmp_path, image_ne):
    from photosleuth.gui.dialogs.compare_dialog import CompareDialog

    copy = tmp_path / "copy.jpg"
    copy.write_bytes(image_ne.read_bytes())
    left = extract_metadata(image_ne, geocode=False)
    right = extract_metadata(copy, geocode=False)

    dialog = CompareDialog(left, right)
    dialog.show()
    pump()
    # Only the file name and path differ between two identical copies.
    assert dialog.tree.topLevelItemCount() <= 3


# --- geotag -----------------------------------------------------------------

def test_geotag_writes_coordinates(themed, pump, image_plain):
    from photosleuth.gui.dialogs.geotag_dialog import GeotagDialog

    record = extract_metadata(image_plain, geocode=False)
    dialog = GeotagDialog([record])
    dialog.show()
    pump()

    dialog.paste_box.setText("51.5007, -0.1246")
    dialog._apply_pasted()
    assert dialog.coordinates()[0] == pytest.approx(51.5007, abs=1e-4)

    dialog.backup_check.setChecked(False)
    dialog._write()
    gps = extract_metadata(image_plain, geocode=False)["gps"]
    assert gps["latitude"] == pytest.approx(51.5007, abs=1e-4)


def test_geotag_seeds_from_existing_gps(themed, pump, image_ne):
    from photosleuth.gui.dialogs.geotag_dialog import GeotagDialog

    dialog = GeotagDialog([extract_metadata(image_ne, geocode=False)])
    pump()
    assert dialog.latitude.value() == pytest.approx(48.8584, abs=1e-3)


def test_geotag_reports_bad_paste(themed, pump, image_plain):
    from photosleuth.gui.dialogs.geotag_dialog import GeotagDialog

    dialog = GeotagDialog([extract_metadata(image_plain, geocode=False)])
    dialog.paste_box.setText("not coordinates at all")
    dialog._apply_pasted()
    assert dialog.status.text().startswith("⚠")


def test_geotag_logs_to_custody(themed, pump, image_plain):
    from photosleuth import custody
    from photosleuth.gui.dialogs.geotag_dialog import GeotagDialog

    dialog = GeotagDialog([extract_metadata(image_plain, geocode=False)])
    dialog.latitude.setValue(10.0)
    dialog.longitude.setValue(20.0)
    dialog.backup_check.setChecked(False)
    dialog._write()
    assert any(entry["action"] == "geotag" for entry in custody.read_log())


# --- settings ---------------------------------------------------------------

def test_settings_round_trip(themed, pump):
    from photosleuth import config
    from photosleuth.gui.dialogs.settings_dialog import SettingsDialog

    dialog = SettingsDialog()
    dialog.show()
    pump()

    dialog.thumb_size.setValue(208)
    dialog.org_name.setText("Acme Forensics")
    dialog.vision_key.setText("secret-key")
    dialog.geocode_delay.setValue(2.5)
    dialog._save()

    saved = config.load_config()
    assert saved["ui"]["thumbnail_size"] == 208
    assert saved["reports"]["organisation"] == "Acme Forensics"
    assert saved["api_keys"]["google_vision"] == "secret-key"
    assert saved["geocoding"]["min_delay_seconds"] == 2.5


def test_settings_rejects_a_bad_accent_colour(themed, pump, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from photosleuth import config
    from photosleuth.gui.dialogs.settings_dialog import SettingsDialog

    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(a))

    dialog = SettingsDialog()
    dialog.accent_colour.setText("not-a-colour")
    dialog.org_name.setText("Should not be saved")
    dialog._save()

    assert warned
    assert config.load_config()["reports"]["organisation"] != "Should not be saved"


def test_settings_lists_languages_and_templates(themed):
    from photosleuth.gui.dialogs.settings_dialog import SettingsDialog

    dialog = SettingsDialog()
    languages = [dialog.language_box.itemData(i) for i in range(dialog.language_box.count())]
    assert "system" in languages and "fr" in languages
    templates = [dialog.template_box.itemData(i) for i in range(dialog.template_box.count())]
    assert "default" in templates


# --- report dialog ----------------------------------------------------------

@pytest.mark.parametrize("fmt,suffix", [("csv", ".csv"), ("json", ".json"), ("html", ".html")])
def test_report_dialog_exports(themed, pump, tmp_path, records, fmt, suffix):
    from photosleuth.gui.dialogs.report_dialog import ReportDialog

    dialog = ReportDialog(records)
    dialog.show()
    pump()
    dialog.format_buttons[fmt].setChecked(True)
    target = tmp_path / f"out{suffix}"
    dialog.path_edit.setText(str(target))
    dialog._export()
    assert target.is_file() and target.stat().st_size > 0


def test_report_dialog_pdf(themed, pump, tmp_path, records):
    from photosleuth.gui.dialogs.report_dialog import ReportDialog

    dialog = ReportDialog(records)
    dialog.format_buttons["pdf"].setChecked(True)
    target = tmp_path / "report.pdf"
    dialog.path_edit.setText(str(target))
    dialog._export()
    assert target.read_bytes().startswith(b"%PDF")


def test_report_options_only_apply_to_reports(themed, pump, records):
    from photosleuth.gui.dialogs.report_dialog import ReportDialog

    dialog = ReportDialog(records)
    dialog.format_buttons["pdf"].setChecked(True)
    assert dialog.options_group.isEnabled() is True
    dialog.format_buttons["csv"].setChecked(True)
    assert dialog.options_group.isEnabled() is False


def test_report_dialog_blocks_a_map_without_geotags(themed, pump, image_plain):
    from PySide6.QtWidgets import QDialogButtonBox

    from photosleuth.gui.dialogs.report_dialog import ReportDialog

    dialog = ReportDialog([extract_metadata(image_plain, geocode=False)])
    dialog.format_buttons["map_png"].setChecked(True)
    pump()
    assert dialog.buttons.button(QDialogButtonBox.Save).isEnabled() is False
    assert "No geotagged" in dialog.status.text()


def test_report_dialog_logs_the_export(themed, pump, tmp_path, records):
    from photosleuth import custody
    from photosleuth.gui.dialogs.report_dialog import ReportDialog

    dialog = ReportDialog(records)
    dialog.format_buttons["json"].setChecked(True)
    dialog.path_edit.setText(str(tmp_path / "x.json"))
    dialog._export()
    assert any(entry["action"] == "export" for entry in custody.read_log())


# --- custody ----------------------------------------------------------------

def test_custody_dialog_shows_and_verifies(themed, pump, image_ne):
    from photosleuth import custody
    from photosleuth.gui.dialogs.custody_dialog import CustodyDialog

    custody.record("analyze", image_ne)
    custody.record("strip", image_ne)

    dialog = CustodyDialog()
    dialog.show()
    pump()
    assert dialog.tree.topLevelItemCount() == 2
    assert "Chain intact" in dialog.verdict.text()


def test_custody_dialog_detects_tampering(themed, pump, image_ne):
    from photosleuth import custody
    from photosleuth.gui.dialogs.custody_dialog import CustodyDialog

    custody.record("analyze", image_ne)
    custody.record("export", image_ne)
    path = custody.log_path()
    lines = path.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[0])
    entry["action"] = "forged"
    lines[0] = json.dumps(entry)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    dialog = CustodyDialog()
    pump()
    assert "Chain broken" in dialog.verdict.text()


def test_custody_dialog_exports(themed, pump, tmp_path, image_ne, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    from photosleuth import custody
    from photosleuth.gui.dialogs.custody_dialog import CustodyDialog

    custody.record("analyze", image_ne)
    target = tmp_path / "log.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)

    CustodyDialog().export()
    assert target.is_file()


# --- about / updates --------------------------------------------------------

def test_about_dialog_reports_the_environment(themed, pump):
    import sys

    from PySide6.QtWidgets import QLabel, QTextBrowser

    from photosleuth import __version__, config
    from photosleuth.gui.dialogs.about_dialog import AboutDialog

    dialog = AboutDialog()
    dialog.show()
    pump()

    headings = " ".join(label.text() for label in dialog.findChildren(QLabel))
    assert f"PhotoSleuth {__version__}" in headings

    details = dialog.findChild(QTextBrowser).toPlainText()
    assert sys.version.split()[0] in details
    assert "PySide6" in details
    assert str(config.config_home()) in details


@pytest.mark.parametrize(
    "info_kwargs,expected",
    [
        ({"latest": "v2.0.0", "url": "https://x", "available": True}, "is available"),
        ({"latest": "v1.1.0"}, "up to date"),
        ({"error": "network down"}, "Could not check"),
    ],
)
def test_update_dialog_states(themed, pump, info_kwargs, expected):
    from photosleuth.gui.dialogs.about_dialog import UpdateDialog
    from photosleuth.updates import UpdateInfo

    info = UpdateInfo(current="1.1.0", **info_kwargs)
    dialog = UpdateDialog(info)
    dialog.show()
    pump()
    assert expected in info.message
