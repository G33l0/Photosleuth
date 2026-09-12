"""Tests for the library model and its filter proxy."""

from photosleuth.core import extract_metadata
from photosleuth.gui.models import (
    FlaggedRole,
    HasGpsRole,
    ImageLibraryModel,
    LibraryFilterProxy,
    PathRole,
    StatusRole,
)


def build(paths, geocode=False):
    model = ImageLibraryModel()
    model.add_paths([str(p) for p in paths])
    for path in paths:
        model.set_record(extract_metadata(path, geocode=geocode))
    return model


def test_adding_and_deduplicating(qapp, image_ne, image_sw):
    model = ImageLibraryModel()
    assert len(model.add_paths([image_ne, image_sw])) == 2
    assert model.add_paths([image_ne]) == []
    assert model.rowCount() == 2


def test_pending_until_analysed(qapp, image_ne):
    model = ImageLibraryModel()
    model.add_paths([image_ne])
    assert len(model.pending()) == 1
    assert model.data(model.index(0, 0), StatusRole) == "pending"
    model.set_record(extract_metadata(image_ne, geocode=False))
    assert model.pending() == []


def test_roles(qapp, image_ne, image_plain):
    model = build([image_ne, image_plain])
    assert model.data(model.index(0, 0), HasGpsRole) is True
    assert model.data(model.index(1, 0), HasGpsRole) is False
    assert model.data(model.index(0, 0), PathRole) == str(image_ne)


def test_flagged_role_follows_forensics(qapp, image_ne):
    model = build([image_ne])
    record = model.record(image_ne)
    assert model.data(model.index(0, 0), FlaggedRole) is False
    record["forensics"] = {"flags": ["something"]}
    model.set_record(record)
    assert model.data(model.index(0, 0), FlaggedRole) is True


def test_removing_and_clearing(qapp, image_ne, image_sw):
    model = build([image_ne, image_sw])
    model.remove_paths([image_ne])
    assert model.rowCount() == 1
    model.clear()
    assert model.rowCount() == 0 and model.records() == []


def test_geotagged_helper(qapp, image_ne, image_sw, image_plain):
    assert len(build([image_ne, image_sw, image_plain]).geotagged()) == 2


def test_text_filter_matches_exif(qapp, image_ne, image_plain):
    model = build([image_ne, image_plain])
    proxy = LibraryFilterProxy()
    proxy.setSourceModel(model)
    proxy.set_text("testcam")
    assert proxy.rowCount() == 1
    proxy.set_text("no-such-camera")
    assert proxy.rowCount() == 0


def test_filter_terms_are_anded(qapp, image_ne, image_plain):
    model = build([image_ne, image_plain])
    proxy = LibraryFilterProxy()
    proxy.setSourceModel(model)
    proxy.set_text("testcam model")
    assert proxy.rowCount() == 1
    proxy.set_text("testcam nonsense")
    assert proxy.rowCount() == 0


def test_gps_and_flag_toggles(qapp, image_ne, image_plain):
    model = build([image_ne, image_plain])
    proxy = LibraryFilterProxy()
    proxy.setSourceModel(model)

    proxy.set_only_geotagged(True)
    assert proxy.rowCount() == 1
    proxy.set_only_geotagged(False)

    proxy.set_only_flagged(True)
    assert proxy.rowCount() == 0
    record = model.record(image_plain)
    record["forensics"] = {"flags": ["No EXIF metadata at all"]}
    model.set_record(record)
    assert proxy.rowCount() == 1


def test_failed_file_records_the_error(qapp, not_an_image):
    model = ImageLibraryModel()
    model.add_paths([not_an_image])
    model.set_failed(str(not_an_image), "boom")
    assert "boom" in model.data(model.index(0, 0), StatusRole)
