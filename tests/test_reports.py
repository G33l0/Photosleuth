"""Tests for CSV export and map generation."""

import csv

import pytest

from photosleuth.core import extract_metadata
from photosleuth.reports import CSV_COLUMNS, export_csv, generate_map, geotagged


@pytest.fixture
def records(image_ne, image_sw, image_plain):
    return [extract_metadata(p, geocode=False) for p in (image_ne, image_sw, image_plain)]


def test_csv_has_a_row_per_image(tmp_path, records):
    target = export_csv(records, tmp_path / "out.csv")
    with open(target, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 3
    assert list(rows[0]) == list(CSV_COLUMNS)
    assert rows[0]["camera_model"] == "Model X"


def test_csv_leaves_blank_coordinates_for_ungeotagged(tmp_path, records):
    target = export_csv(records, tmp_path / "out.csv")
    with open(target, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[-1]["latitude"] == ""


def test_csv_uses_crlf_safe_newlines(tmp_path, records):
    """newline='' keeps Excel on Windows from inserting blank rows."""
    target = export_csv(records, tmp_path / "out.csv")
    assert b"\r\r\n" not in target.read_bytes()


def test_csv_creates_missing_directories(tmp_path, records):
    target = export_csv(records, tmp_path / "a" / "b" / "out.csv")
    assert target.is_file()


def test_geotagged_filters_correctly(records):
    assert len(geotagged(records)) == 2


def test_map_contains_a_marker_per_geotagged_image(tmp_path, records):
    target = generate_map(records, tmp_path / "map.html")
    html = target.read_text(encoding="utf-8")
    assert html.count("L.marker") == 2


def test_map_escapes_popup_content(tmp_path, records):
    records[0]["location"] = "<script>alert(1)</script>"
    html = generate_map(records, tmp_path / "map.html").read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_map_without_geotagged_images_raises(tmp_path, image_plain):
    with pytest.raises(ValueError):
        generate_map([extract_metadata(image_plain, geocode=False)], tmp_path / "map.html")
