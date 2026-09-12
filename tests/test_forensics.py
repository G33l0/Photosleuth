"""Tests for the thumbnail-mismatch check and hashing."""

import pytest

from photosleuth import forensics
from photosleuth.core import extract_metadata


def test_matching_thumbnail_is_a_match(image_with_matching_thumbnail):
    check = forensics.compare_thumbnail(image_with_matching_thumbnail)
    assert check.has_thumbnail is True
    assert check.verdict == "match"
    assert check.distance is not None and check.distance <= forensics.LIKELY_MATCH


def test_stale_thumbnail_is_a_mismatch(image_with_stale_thumbnail):
    metadata = extract_metadata(image_with_stale_thumbnail, geocode=False)
    check = forensics.compare_thumbnail(image_with_stale_thumbnail, metadata)
    assert check.verdict == "mismatch"
    assert check.is_mismatch is True
    assert check.distance >= forensics.LIKELY_MISMATCH


def test_editor_software_is_reported(image_with_stale_thumbnail):
    metadata = extract_metadata(image_with_stale_thumbnail, geocode=False)
    report = forensics.analyze(image_with_stale_thumbnail, metadata)
    assert any("Photoshop" in flag for flag in report["flags"])
    assert "Embedded thumbnail does not match the image" in report["flags"]


def test_image_without_a_thumbnail_is_not_flagged_as_tampered(image_ne):
    check = forensics.compare_thumbnail(image_ne)
    assert check.has_thumbnail is False
    assert check.verdict == "no-thumbnail"
    assert check.is_mismatch is False


def test_missing_exif_is_flagged(image_plain):
    metadata = extract_metadata(image_plain, geocode=False)
    report = forensics.analyze(image_plain, metadata)
    assert any("No EXIF" in flag for flag in report["flags"])


def test_dhash_is_stable_and_scale_tolerant(image_with_matching_thumbnail):
    from PIL import Image

    with Image.open(image_with_matching_thumbnail) as image:
        image.load()
        full = forensics.dhash(image)
        half = forensics.dhash(image.resize((image.width // 2, image.height // 2)))
    assert forensics.hamming(full, full) == 0
    assert forensics.hamming(full, half) <= forensics.LIKELY_MATCH


def test_different_images_hash_differently(
    image_with_matching_thumbnail, image_with_stale_thumbnail
):
    a = forensics.perceptual_fingerprint(image_with_matching_thumbnail)
    b = forensics.perceptual_fingerprint(image_with_stale_thumbnail)
    assert a["dhash"] != b["dhash"]


def test_identical_content_hashes_identically(tmp_path, image_with_matching_thumbnail):
    copy = tmp_path / "copy.jpg"
    copy.write_bytes(image_with_matching_thumbnail.read_bytes())
    assert (
        forensics.perceptual_fingerprint(copy)["dhash"]
        == forensics.perceptual_fingerprint(image_with_matching_thumbnail)["dhash"]
    )


def test_file_hashes(image_ne):
    digests = forensics.file_hashes(image_ne, ("md5", "sha256"))
    assert len(digests["sha256"]) == 64
    assert len(digests["md5"]) == 32
    assert forensics.file_hashes(image_ne, ("sha256",))["sha256"] == digests["sha256"]


def test_analyze_tolerates_a_non_image(not_an_image):
    report = forensics.analyze(not_an_image, {"exif": {}, "has_exif": False})
    assert "verdict" in report
    assert report["hashes"]["sha256"]
