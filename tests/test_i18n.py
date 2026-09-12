"""Translation loading and fallbacks."""

import pytest

from photosleuth import i18n


@pytest.fixture(autouse=True)
def reset_language():
    yield
    i18n.set_language("en")


def test_english_is_the_source_language():
    i18n.set_language("en")
    assert i18n.tr("Analyze") == "Analyze"
    assert i18n.current_language() == "en"


@pytest.mark.parametrize("code", ["es", "fr", "de", "pt", "ar"])
def test_shipped_languages_translate(code):
    assert i18n.set_language(code) == code
    assert i18n.tr("Analyze") != "Analyze"


def test_unknown_key_falls_back_to_english():
    i18n.set_language("fr")
    assert i18n.tr("Some string nobody translated") == "Some string nobody translated"


def test_unknown_language_falls_back_to_english():
    assert i18n.set_language("xx") == "en"
    assert i18n.tr("Analyze") == "Analyze"


def test_placeholders_are_formatted():
    i18n.set_language("en")
    assert i18n.tr("{count} files", count=3) == "3 files"


def test_broken_placeholder_does_not_raise():
    i18n.set_language("en")
    assert i18n.tr("{missing}", other=1) == "{missing}"


def test_rtl_detection():
    assert i18n.is_rtl("ar") is True
    assert i18n.is_rtl("en") is False


def test_available_languages_includes_english_and_shipped():
    codes = [code for code, _name in i18n.available_languages()]
    assert "en" in codes and "fr" in codes and "ar" in codes


def test_template_can_be_written(tmp_path):
    target = i18n.write_template(tmp_path / "it.json")
    import json

    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["__code__"] == "it"
    assert "Analyze" in data
