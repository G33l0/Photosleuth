"""Tests for EXIF stripping."""

import pytest

from photosleuth.core import extract_metadata
from photosleuth.privacy import default_output_path, has_sensitive_metadata, strip_exif


def test_strip_removes_gps_and_exif(image_ne):
    destination, removed = strip_exif(image_ne)
    assert removed > 0
    assert destination.name == "eiffel_clean.jpg"
    cleaned = extract_metadata(destination, geocode=False)
    assert "gps" not in cleaned
    assert cleaned["exif"] == {}


def test_strip_leaves_the_original_untouched(image_ne):
    strip_exif(image_ne)
    assert "gps" in extract_metadata(image_ne, geocode=False)


def test_overwrite_replaces_in_place(image_ne):
    destination, _ = strip_exif(image_ne, overwrite=True)
    assert destination == image_ne
    assert "gps" not in extract_metadata(image_ne, geocode=False)


def test_pixels_are_preserved(image_ne):
    from PIL import Image

    destination, _ = strip_exif(image_ne)
    with Image.open(image_ne) as before, Image.open(destination) as after:
        assert before.size == after.size


def test_custom_suffix(image_ne):
    destination, _ = strip_exif(image_ne, suffix="_scrubbed")
    assert destination.name == "eiffel_scrubbed.jpg"


def test_explicit_output_path(image_ne, tmp_path):
    target = tmp_path / "out" / "safe.jpg"
    destination, _ = strip_exif(image_ne, output_path=target)
    assert destination == target and target.is_file()


def test_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        strip_exif("/definitely/not/here.jpg")


def test_unsupported_format_is_rejected(tmp_path):
    weird = tmp_path / "photo.xyz"
    weird.write_bytes(b"nope")
    with pytest.raises(ValueError):
        strip_exif(weird)


def test_failure_leaves_no_temp_files_behind(tmp_path, not_an_image):
    with pytest.raises(Exception):
        strip_exif(not_an_image)
    assert not list(tmp_path.glob(".clean-*"))


def test_default_output_path_uses_configured_suffix(image_ne):
    from photosleuth import config

    config.set_privacy_options(output_suffix="_nometa")
    assert default_output_path(image_ne).name == "eiffel_nometa.jpg"


def test_sensitive_metadata_detection(image_ne, image_plain):
    assert has_sensitive_metadata(extract_metadata(image_ne, geocode=False)) is True
    assert has_sensitive_metadata(extract_metadata(image_plain, geocode=False)) is False
