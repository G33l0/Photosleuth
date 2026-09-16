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


def test_map_contains_a_point_per_geotagged_image(tmp_path, records):
    import json
    import re

    target = generate_map(records, tmp_path / "map.html")
    html = target.read_text(encoding="utf-8")
    points = json.loads(re.search(r"var points = (\[.*?\]);", html, re.S).group(1))
    assert len(points) == 2
    assert all("lat" in point and "lon" in point for point in points)


def test_map_is_self_contained(tmp_path, records):
    """The page must open with no internet: Leaflet is embedded, not fetched."""
    html = generate_map(records, tmp_path / "map.html").read_text(encoding="utf-8")
    assert "cdnjs.cloudflare.com" not in html
    assert "L.map" in html and "leaflet" in html.lower()


def test_markers_need_no_image_files(tmp_path, records):
    """Leaflet's default pin is a PNG from an images/ folder that is not there.

    Inlining the stylesheet removes the base path Leaflet uses to find it, so
    the default markers render as broken images. The map therefore draws its
    own inline SVG pin instead.
    """
    html = generate_map(records, tmp_path / "map.html").read_text(encoding="utf-8")
    assert "L.divIcon" in html
    assert "<svg" in html
    # The markers this page creates must carry the custom icon, not the default.
    assert "icon: pin" in html


def test_marker_icon_is_drawn_not_fetched(tmp_path, records):
    """No marker image may be requested by the page's own markup."""
    import re

    html = generate_map(records, tmp_path / "map.html").read_text(encoding="utf-8")
    page_script = html.split("var points =")[1]
    assert not re.search(r"marker-icon|marker-shadow", page_script)


def test_map_round_trips_through_the_reader(tmp_path, records):
    from photosleuth.reports import _records_from_map_html

    target = generate_map(records, tmp_path / "map.html")
    recovered = _records_from_map_html(target)
    assert len(recovered) == 2
    assert recovered[0]["gps"]["latitude"] == pytest.approx(
        records[0]["gps"]["latitude"], abs=1e-5
    )


def test_map_escapes_popup_content(tmp_path, records):
    records[0]["location"] = "<script>alert(1)</script>"
    html = generate_map(records, tmp_path / "map.html").read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_map_without_geotagged_images_raises(tmp_path, image_plain):
    with pytest.raises(ValueError):
        generate_map([extract_metadata(image_plain, geocode=False)], tmp_path / "map.html")
