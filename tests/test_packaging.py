"""Guards on assets, packaging metadata and version consistency."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "photosleuth" / "assets"


def test_version_is_consistent_everywhere():
    from photosleuth import __version__

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(rf'(?m)^version\s*=\s*"{re.escape(__version__)}"', pyproject)

    installer = (ROOT / "packaging" / "installer.iss").read_text(encoding="utf-8")
    assert re.search(rf'#define\s+AppVersion\s+"{re.escape(__version__)}"', installer)

    version_info = (ROOT / "packaging" / "version_info.txt").read_text(encoding="utf-8")
    assert f"'{__version__}'" in version_info


def test_repository_is_consistent_everywhere():
    """Every file that names the project repo must agree on owner/name."""
    from photosleuth import config, updates

    expected = "G33l0/Photosleuth"
    assert updates.DEFAULT_REPO == expected
    assert config.DEFAULT_CONFIG["updates"]["repository"] == expected

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert f"https://github.com/{expected}" in pyproject

    installer = (ROOT / "packaging" / "installer.iss").read_text(encoding="utf-8")
    assert f"https://github.com/{expected}" in installer

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"https://github.com/{expected}" in readme


def test_author_is_credited_consistently():
    """The tool's author (IamG2) is credited everywhere an author is named."""
    import re

    from photosleuth import __author__

    assert __author__ == "IamG2"

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert f'name = "{__author__}"' in pyproject

    installer = (ROOT / "packaging" / "installer.iss").read_text(encoding="utf-8")
    assert re.search(rf'#define\s+AppPublisher\s+"{re.escape(__author__)}"', installer)

    version_info = (ROOT / "packaging" / "version_info.txt").read_text(encoding="utf-8")
    assert f"'CompanyName', '{__author__}'" in version_info

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"Developed by **{__author__}**" in readme


def test_licence_holder_is_the_repository_owner():
    """Copyright sits with the repo owner, which is separate from authorship."""
    import re

    licence = (ROOT / "LICENSE").read_text(encoding="utf-8")
    holder = re.search(r"Copyright \(c\)\s*\d{4}\s+(.+)", licence).group(1).strip()
    assert holder == "G33l0"

    version_info = (ROOT / "packaging" / "version_info.txt").read_text(encoding="utf-8")
    assert holder in version_info


def test_icon_has_every_windows_size():
    from PIL import Image

    ico = ASSETS / "photosleuth.ico"
    assert ico.is_file()
    with Image.open(ico) as image:
        sizes = {size[0] for size in image.info["sizes"]}
    # Windows uses 16 in Explorer lists, 32 on the desktop and 256 for tiles.
    assert {16, 32, 48, 256}.issubset(sizes)


def test_logo_files_exist_and_are_square():
    from PIL import Image

    for name in ("logo.png", "logo_256.png", "logo_128.png", "mark.png"):
        path = ASSETS / name
        assert path.is_file(), f"missing {name}"
        with Image.open(path) as image:
            assert image.width == image.height


def test_logo_svg_is_valid_xml():
    import xml.dom.minidom

    document = xml.dom.minidom.parse(str(ASSETS / "logo.svg"))
    assert document.documentElement.tagName == "svg"


def test_installer_artwork_exists():
    from PIL import Image

    for name, size in (("installer_wizard.bmp", (164, 314)), ("installer_banner.bmp", (150, 57))):
        with Image.open(ASSETS / name) as image:
            assert image.size == size


def test_every_translation_is_valid_json():
    import json

    from photosleuth.i18n import BUILTIN_LANGUAGES

    files = list((ASSETS / "i18n").glob("*.json"))
    assert files
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data.get("__language__")
        assert path.stem in BUILTIN_LANGUAGES


def test_translations_have_no_empty_strings():
    import json

    for path in (ASSETS / "i18n").glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        blank = [key for key, value in data.items() if value == ""]
        assert not blank, f"{path.name} has untranslated keys: {blank[:5]}"


def test_report_template_ships():
    assert (ASSETS / "templates" / "default.html").is_file()


def test_leaflet_is_vendored_so_maps_work_offline():
    """Exported maps must open without a CDN."""
    assert (ASSETS / "vendor" / "leaflet.js").is_file()
    assert (ASSETS / "vendor" / "leaflet.css").is_file()


def test_package_data_covers_the_assets():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for pattern in ("assets/*.ico", "assets/i18n/*.json", "assets/templates/*.html",
                    "assets/vendor/*.js", "assets/timezones.bin"):
        assert pattern in pyproject


def test_pyinstaller_spec_excludes_webengine():
    spec = (ROOT / "packaging" / "photosleuth.spec").read_text(encoding="utf-8")
    assert "PySide6.QtWebEngineCore" in spec
    assert "photosleuth/assets" in spec


def test_qt_libraries_are_not_filtered():
    """Qt shared libraries are left alone.

    Filtering the QML, Quick and PDF stacks saved about 20 MB and passed every
    check available on Linux, but the application ships on Windows where that
    could not be verified. The saving was given back rather than risk a failure
    that first appears on a user's machine.
    """
    spec = (ROOT / "packaging" / "photosleuth.spec").read_text(encoding="utf-8")
    assert "UNUSED_QT_LIBRARIES" not in spec
    assert "a.binaries = TOC(" not in spec


def test_folium_is_not_a_dependency():
    """Maps are rendered from a vendored Leaflet, not the folium stack."""
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "folium" not in pyproject
    assert "folium" not in requirements


def test_timezone_boundaries_are_bundled():
    """The precise boundary data ships; accuracy beats 32 MB here."""
    spec = (ROOT / "packaging" / "photosleuth.spec").read_text(encoding="utf-8")
    assert 'collect_data_files("timezonefinder")' in spec
    assert '"timezonefinder"' not in spec.split("excludes = [")[1].split("]")[0]
    assert "photosleuth.geolocation" in spec


def test_timezone_raster_ships_as_a_fallback():
    """Kept so a pip install without timezonefinder still answers, at 43 KB."""
    raster = ASSETS / "timezones.bin"
    assert raster.is_file()
    assert raster.stat().st_size < 500_000


def test_installer_registers_associations_without_hijacking_defaults():
    installer = (ROOT / "packaging" / "installer.iss").read_text(encoding="utf-8")
    assert "OpenWithProgids" in installer
    # Setting these would steal the user's default image viewer.
    assert "UserChoice" not in installer
    assert 'Subkey: "Software\\Classes\\.jpg"; ValueType: string; ValueName: ""' not in installer


def test_entry_points_are_declared():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'photosleuth = "photosleuth.cli:run"' in pyproject
    assert 'photosleuth-gui = "photosleuth.gui.app:main"' in pyproject


def test_requirements_match_project_dependencies():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    for package in ("exifread", "geopy", "Pillow", "requests", "piexif",
                    "Jinja2", "numpy", "timezonefinder"):
        assert package in pyproject, f"{package} missing from pyproject"
        assert package in requirements, f"{package} missing from requirements.txt"
