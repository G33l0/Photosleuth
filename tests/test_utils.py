"""Tests for image discovery, console safety, caching and rate limiting."""

import io
import time

from photosleuth.utils import (
    GeocodeCache,
    RateLimiter,
    find_images,
    safe_print,
    supports_unicode,
    to_console_safe,
)


def test_directory_named_like_an_image_is_skipped(tmp_path, image_ne):
    """Path.iterdir() alone yielded directories whose name ended in .jpg."""
    (tmp_path / "album.jpg").mkdir()
    found = find_images(tmp_path)
    assert image_ne in found
    assert all(path.is_file() for path in found)


def test_recursive_discovery(tmp_path, image_ne):
    nested = tmp_path / "sub" / "deeper"
    nested.mkdir(parents=True)
    (nested / "copy.jpg").write_bytes(image_ne.read_bytes())
    assert len(find_images(tmp_path, recursive=False)) == 1
    assert len(find_images(tmp_path, recursive=True)) == 2


def test_discovery_is_case_insensitive(tmp_path, image_ne):
    (tmp_path / "SHOUTY.JPG").write_bytes(image_ne.read_bytes())
    assert len(find_images(tmp_path)) == 2


def test_console_fallback_for_legacy_codepage():
    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    assert supports_unicode(stream) is False
    downgraded = to_console_safe("📄 File: a.jpg", stream)
    downgraded.encode("cp1252")  # must not raise
    assert "[file]" in downgraded


def test_safe_print_never_raises_on_legacy_codepage():
    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
    safe_print("✅ 📄 🗺️ done", stream=stream)


def test_geocode_cache_survives_a_restart(tmp_path):
    path = tmp_path / "cache.json"
    GeocodeCache(path).set(48.8584, 2.2945, "Eiffel Tower, Paris")
    assert GeocodeCache(path).get(48.8584, 2.2945) == "Eiffel Tower, Paris"


def test_disabled_cache_stores_nothing(tmp_path):
    cache = GeocodeCache(tmp_path / "off.json", enabled=False)
    cache.set(1.0, 2.0, "somewhere")
    assert cache.get(1.0, 2.0) is None


def test_rate_limiter_spaces_calls():
    limiter = RateLimiter(0.12)
    start = time.monotonic()
    limiter.wait()
    limiter.wait()
    assert time.monotonic() - start >= 0.1
