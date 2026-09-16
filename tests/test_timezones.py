"""The compact time-zone raster that replaces 32 MB of boundary polygons."""

import pytest

from photosleuth.geolocation import timezones as tz


@pytest.fixture
def raster_only(monkeypatch):
    """Force the shipped raster, so the test never measures timezonefinder."""
    monkeypatch.setattr(tz, "_finder_checked", True)
    monkeypatch.setattr(tz, "_finder", None)


@pytest.mark.parametrize(
    "name,latitude,longitude,zone",
    [
        ("Paris", 48.8584, 2.2945, "Europe/Paris"),
        ("Sydney", -33.8688, 151.2093, "Australia/Sydney"),
        ("New York", 40.7128, -74.0060, "America/New_York"),
        ("Tokyo", 35.6762, 139.6503, "Asia/Tokyo"),
        ("Urumqi", 43.8, 87.6, "Asia/Urumqi"),
        ("Sao Paulo", -23.5505, -46.6333, "America/Sao_Paulo"),
        ("Auckland", -36.8485, 174.7633, "Pacific/Auckland"),
        ("Anchorage", 61.2181, -149.9003, "America/Anchorage"),
    ],
)
def test_known_cities_resolve(raster_only, name, latitude, longitude, zone):
    assert tz.zone_at(latitude, longitude).name == zone


def test_offset_is_returned_for_a_date(raster_only):
    from datetime import datetime

    offset, lookup = tz.offset_at(48.8584, 2.2945, datetime(2024, 7, 4, 12))
    assert offset == pytest.approx(2.0)      # CEST
    assert lookup.name == "Europe/Paris"

    winter, _ = tz.offset_at(48.8584, 2.2945, datetime(2024, 1, 4, 12))
    assert winter == pytest.approx(1.0)      # CET


def test_mid_ocean_uses_nautical_time(raster_only):
    """At sea the answer is a nautical Etc/GMT zone, not "nowhere"."""
    from datetime import datetime

    # Point Nemo, the most remote spot in the Pacific.
    lookup = tz.zone_at(-48.876, -123.393)
    assert lookup.found
    assert lookup.name.startswith("Etc/GMT")

    offset, _ = tz.offset_at(-48.876, -123.393, datetime(2024, 7, 4, 12))
    # Etc/GMT+8 is UTC-8: the sign convention in these names is inverted.
    assert offset == pytest.approx(-8.0)


def test_nautical_offset_fallback():
    assert tz.nautical_offset(0.0) == 0
    assert tz.nautical_offset(120.0) == 8
    assert tz.nautical_offset(-75.0) == -5


def test_a_border_point_is_flagged(raster_only):
    """Near a boundary the raster must admit uncertainty rather than assert.

    Arizona does not observe daylight saving, so its edges are real time-zone
    boundaries rather than administrative lines that happen to share an offset.
    """
    lookup = tz.zone_at(31.33, -109.05)
    assert lookup.found
    assert lookup.near_border is True


def test_an_interior_point_is_not_flagged(raster_only):
    assert tz.zone_at(48.8584, 2.2945).near_border is False


def test_timezonefinder_is_preferred_when_installed():
    """If the precise library is present it wins, and reports itself."""
    pytest.importorskip("timezonefinder")
    tz._finder_checked = False
    tz._finder = None
    try:
        assert tz.zone_at(48.8584, 2.2945).source == "timezonefinder"
    finally:
        tz._finder_checked = False
        tz._finder = None


def test_lookup_is_fast(raster_only):
    import time

    tz.zone_at(0.0, 0.0)          # warm the decompression
    start = time.perf_counter()
    for index in range(2000):
        tz.zone_at(index % 80 - 40, index % 300 - 150)
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0, "raster lookups should be microseconds, not milliseconds"
