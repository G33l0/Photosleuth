"""Tests for manual geotagging."""

import pytest

from photosleuth.core import extract_metadata
from photosleuth.geotag import (
    parse_coordinate_text,
    remove_gps,
    validate_coordinates,
    write_gps,
)


def test_write_and_read_back(image_plain):
    write_gps(image_plain, 51.5007, -0.1246, altitude=15.0, backup=False)
    gps = extract_metadata(image_plain, geocode=False)["gps"]
    assert gps["latitude"] == pytest.approx(51.5007, abs=1e-5)
    assert gps["longitude"] == pytest.approx(-0.1246, abs=1e-5)
    assert gps["altitude_m"] == pytest.approx(15.0, abs=0.05)


def test_southern_and_western_hemispheres_round_trip(image_plain):
    write_gps(image_plain, -33.8568, -151.2153, backup=False)
    gps = extract_metadata(image_plain, geocode=False)["gps"]
    assert gps["latitude"] < 0 and gps["longitude"] < 0


def test_negative_altitude(image_plain):
    write_gps(image_plain, 31.5, 35.5, altitude=-420.0, backup=False)
    assert extract_metadata(image_plain, geocode=False)["gps"]["altitude_m"] < 0


def test_existing_exif_is_preserved(image_ne):
    before = extract_metadata(image_ne, geocode=False)["exif"]["Image Model"]
    write_gps(image_ne, 10.0, 20.0, backup=False)
    assert extract_metadata(image_ne, geocode=False)["exif"]["Image Model"] == before


def test_backup_is_written(image_plain, tmp_path):
    write_gps(image_plain, 1.0, 2.0, backup=True)
    assert (tmp_path / "plain.jpg.bak").is_file()


def test_write_to_a_copy_leaves_the_source_alone(image_plain, tmp_path):
    target = tmp_path / "tagged.jpg"
    write_gps(image_plain, 5.0, 6.0, output_path=target, backup=False)
    assert "gps" in extract_metadata(target, geocode=False)
    assert "gps" not in extract_metadata(image_plain, geocode=False)


def test_remove_gps(image_ne):
    assert "gps" in extract_metadata(image_ne, geocode=False)
    remove_gps(image_ne, backup=False)
    assert "gps" not in extract_metadata(image_ne, geocode=False)


def test_remove_gps_keeps_other_tags(image_ne):
    remove_gps(image_ne, backup=False)
    assert extract_metadata(image_ne, geocode=False)["exif"]["Image Model"] == "Model X"


@pytest.mark.parametrize("latitude,longitude", [(91, 0), (-91, 0), (0, 181), (0, -181)])
def test_out_of_range_coordinates_are_rejected(image_plain, latitude, longitude):
    with pytest.raises(ValueError):
        write_gps(image_plain, latitude, longitude)


def test_unsupported_format_is_rejected(tmp_path):
    target = tmp_path / "photo.png"
    target.write_bytes(b"not really a png")
    with pytest.raises(ValueError):
        write_gps(target, 1.0, 2.0)


@pytest.mark.parametrize(
    "text,latitude,longitude",
    [
        ("48.8584, 2.2945", 48.8584, 2.2945),
        ("-33.8568 151.2153", -33.8568, 151.2153),
        ("https://www.google.com/maps?q=51.5007,-0.1246", 51.5007, -0.1246),
        ("https://www.google.com/maps/@40.7128,-74.0060,15z", 40.7128, -74.0060),
        ("48°51'30.1\"N 2°17'40.2\"E", 48.8583, 2.2945),
        ("33°51'24.5\"S 151°12'55.1\"W", -33.8568, -151.2153),
    ],
)
def test_coordinate_parsing(text, latitude, longitude):
    parsed_lat, parsed_lon = parse_coordinate_text(text)
    assert parsed_lat == pytest.approx(latitude, abs=1e-3)
    assert parsed_lon == pytest.approx(longitude, abs=1e-3)


@pytest.mark.parametrize("text", ["", "not coordinates", "abc, def"])
def test_unparseable_coordinates_raise(text):
    with pytest.raises(ValueError):
        parse_coordinate_text(text)


def test_validate_coordinates_returns_floats():
    assert validate_coordinates("10", "20") == (10.0, 20.0)
