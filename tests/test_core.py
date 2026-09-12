"""Regression tests for GPS parsing and metadata extraction."""

import pytest

from photosleuth.core import (
    _ratio_to_float,
    _ref_letter,
    convert_to_decimal,
    extract_metadata,
    format_output,
    save_report,
)


class FakeRatio:
    """Mimics an exifread 2.x Ratio, which only exposed .num/.den."""

    def __init__(self, num, den):
        self.num = num
        self.den = den


def test_ratio_accepts_legacy_num_den():
    assert _ratio_to_float(FakeRatio(3, 2)) == 1.5


def test_ratio_survives_zero_denominator():
    assert _ratio_to_float(FakeRatio(1, 0)) == 1.0


def test_ratio_accepts_plain_numbers():
    assert _ratio_to_float(7) == 7.0


def test_convert_to_decimal_dms():
    class Coord:
        values = [FakeRatio(48, 1), FakeRatio(51, 1), FakeRatio(3013, 100)]

    assert convert_to_decimal(Coord()) == pytest.approx(48.858369, abs=1e-5)


def test_convert_to_decimal_handles_degrees_only():
    """Some tools write only degrees; this used to return None."""

    class Coord:
        values = [FakeRatio(10, 1)]

    assert convert_to_decimal(Coord()) == 10.0


def test_convert_to_decimal_rejects_garbage():
    class Coord:
        values = []

    assert convert_to_decimal(Coord()) is None
    assert convert_to_decimal(None) is None


@pytest.mark.parametrize(
    "raw,expected",
    [("N", "N"), ("s", "S"), (b"W", "W"), (["E"], "E"), (" n ", "N"), (None, "")],
)
def test_ref_letter_normalises(raw, expected):
    assert _ref_letter(raw) == expected


def test_extracts_northeast_coordinates(image_ne):
    meta = extract_metadata(image_ne, geocode=False)
    assert meta["gps"]["latitude"] == pytest.approx(48.858369, abs=1e-5)
    assert meta["gps"]["longitude"] == pytest.approx(2.294481, abs=1e-5)
    assert meta["gps"]["altitude_m"] == pytest.approx(330.0)


def test_southern_western_hemispheres_are_negative(image_sw):
    meta = extract_metadata(image_sw, geocode=False)
    assert meta["gps"]["latitude"] < 0
    assert meta["gps"]["longitude"] < 0


def test_exif_datetime_is_parsed_to_iso(image_ne):
    assert extract_metadata(image_ne, geocode=False)["date_taken"] == "2024-07-04T12:30:00"


def test_image_without_exif_has_no_gps(image_plain):
    meta = extract_metadata(image_plain, geocode=False)
    assert "gps" not in meta
    assert meta["has_exif"] is False


def test_non_image_does_not_raise(not_an_image):
    """A stray non-image used to abort an entire batch."""
    meta = extract_metadata(not_an_image, geocode=False)
    assert meta["exif"] == {}


def test_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        extract_metadata("/definitely/not/here.jpg")


def test_format_output_without_gps_is_safe(image_plain):
    text = format_output(extract_metadata(image_plain, geocode=False))
    assert "Not found" in text


def test_save_report_creates_missing_parent_dirs(tmp_path, image_ne):
    target = tmp_path / "deep" / "nested" / "report.json"
    save_report(extract_metadata(image_ne, geocode=False), target, "json")
    assert target.is_file()


def test_save_report_rejects_unknown_format(tmp_path, image_ne):
    with pytest.raises(ValueError):
        save_report(extract_metadata(image_ne, geocode=False), tmp_path / "x.xml", "xml")
