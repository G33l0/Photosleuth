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


def _scene(width=320, height=240, shift=0, seed=11):
    """A busy, deterministic image so perceptual hashes are meaningful."""
    import random

    from PIL import ImageDraw

    rng = random.Random(seed)
    image = Image.new("RGB", (width, height), (30, 60, 110))
    draw = ImageDraw.Draw(image)
    for _ in range(14):
        x, y = rng.randint(0, width), rng.randint(0, height)
        draw.ellipse(
            [x, y, x + 60, y + 60],
            fill=(rng.randint(60, 255), rng.randint(60, 255), 90),
        )
    draw.rectangle([30 + shift, 40, 150 + shift, 150], fill=(240, 200, 40))
    return image


def _thumbnail_bytes(image, size=(160, 120)):
    import io

    buffer = io.BytesIO()
    image.resize(size, Image.LANCZOS).save(buffer, "JPEG")
    return buffer.getvalue()


@pytest.fixture
def image_with_matching_thumbnail(tmp_path):
    """An untouched photo: embedded thumbnail matches the pixels."""
    scene = _scene()
    path = tmp_path / "honest.jpg"
    scene.save(
        path,
        exif=piexif.dump({
            "0th": {piexif.ImageIFD.Make: b"Cam"},
            "Exif": {}, "GPS": {}, "1st": {},
            "thumbnail": _thumbnail_bytes(scene),
        }),
    )
    return path


@pytest.fixture
def image_with_stale_thumbnail(tmp_path):
    """An edited photo: pixels changed, original thumbnail left behind."""
    original = _scene()
    edited = _scene(shift=130)
    path = tmp_path / "tampered.jpg"
    edited.save(
        path,
        exif=piexif.dump({
            "0th": {
                piexif.ImageIFD.Make: b"Cam",
                piexif.ImageIFD.Software: b"Adobe Photoshop 25.0",
            },
            "Exif": {}, "GPS": {}, "1st": {},
            "thumbnail": _thumbnail_bytes(original),
        }),
    )
    return path


@pytest.fixture
def gallery(tmp_path, image_ne, image_sw, image_plain,
            image_with_matching_thumbnail, image_with_stale_thumbnail):
    """Every fixture image lives in tmp_path, so this is just the folder."""
    return tmp_path
