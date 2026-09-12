"""Shared fixtures: isolated config home and generated test images."""

import pytest
from PIL import Image

piexif = pytest.importorskip("piexif")


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Point config + cache at a temp dir so tests never touch the real one."""
    home = tmp_path / "cfg"
    monkeypatch.setenv("PHOTOSLEUTH_HOME", str(home))

    from photosleuth import core, utils

    utils.reset_default_cache()
    core.reset_geocoder()
    yield home
    utils.reset_default_cache()
    core.reset_geocoder()


def _write(path, gps=None, size=(32, 24)):
    image = Image.new("RGB", size, (90, 140, 200))
    zeroth = {piexif.ImageIFD.Make: b"TestCam", piexif.ImageIFD.Model: b"Model X"}
    exif = {
        piexif.ExifIFD.ISOSpeedRatings: 400,
        piexif.ExifIFD.DateTimeOriginal: b"2024:07:04 12:30:00",
    }
    payload = {"0th": zeroth, "Exif": exif, "GPS": gps or {}, "1st": {}, "thumbnail": None}
    image.save(path, exif=piexif.dump(payload))
    return path


@pytest.fixture
def image_ne(tmp_path):
    """Eiffel Tower: 48.858370 N, 2.294481 E."""
    gps = {
        piexif.GPSIFD.GPSLatitudeRef: b"N",
        piexif.GPSIFD.GPSLatitude: ((48, 1), (51, 1), (3013, 100)),
        piexif.GPSIFD.GPSLongitudeRef: b"E",
        piexif.GPSIFD.GPSLongitude: ((2, 1), (17, 1), (4013, 100)),
        piexif.GPSIFD.GPSAltitude: (330, 1),
        piexif.GPSIFD.GPSAltitudeRef: 0,
    }
    return _write(tmp_path / "eiffel.jpg", gps)


@pytest.fixture
def image_sw(tmp_path):
    """Southern + Western hemisphere coordinates."""
    gps = {
        piexif.GPSIFD.GPSLatitudeRef: b"S",
        piexif.GPSIFD.GPSLatitude: ((33, 1), (51, 1), (2448, 100)),
        piexif.GPSIFD.GPSLongitudeRef: b"W",
        piexif.GPSIFD.GPSLongitude: ((151, 1), (12, 1), (5508, 100)),
    }
    return _write(tmp_path / "south.jpg", gps)


@pytest.fixture
def image_plain(tmp_path):
    path = tmp_path / "plain.jpg"
    Image.new("RGB", (16, 16), (0, 0, 0)).save(path)
    return path


@pytest.fixture
def not_an_image(tmp_path):
    path = tmp_path / "broken.jpg"
    path.write_text("this is definitely not a jpeg")
    return path
