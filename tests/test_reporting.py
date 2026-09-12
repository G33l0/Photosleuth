"""Tests for HTML/PDF/JSON reporting and static map rendering."""

import json

import pytest

from photosleuth import reports
from photosleuth.core import extract_metadata


@pytest.fixture
def records(image_ne, image_sw, image_plain):
    return [extract_metadata(path, geocode=False) for path in (image_ne, image_sw, image_plain)]


def test_json_export(tmp_path, records):
    target = reports.export_json(records, tmp_path / "out.json")
    data = json.loads(target.read_text(encoding="utf-8"))
    assert len(data) == 3


def test_html_report_is_self_contained(tmp_path, records):
    target = reports.export_html(records, tmp_path / "r.html", title="Case 1")
    html = target.read_text(encoding="utf-8")
    assert "Case 1" in html
    assert "data:image/" in html          # thumbnails inlined
    assert "http://" not in html.replace("http://www.w3.org", "")


def test_html_branding_is_applied(tmp_path, records):
    target = reports.export_html(
        records, tmp_path / "r.html",
        branding={"organisation": "Acme Ltd", "author": "Jo", "footer_note": "Case 42"},
    )
    html = target.read_text(encoding="utf-8")
    assert "Acme Ltd" in html and "Jo" in html and "Case 42" in html


def test_html_escapes_hostile_metadata(tmp_path, records):
    records[0]["location"] = "<script>alert('x')</script>"
    html = reports.export_html(records, tmp_path / "r.html").read_text(encoding="utf-8")
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html


def test_thumbnails_can_be_switched_off(tmp_path, records):
    html = reports.export_html(
        records, tmp_path / "r.html", include_thumbnails=False
    ).read_text(encoding="utf-8")
    assert "data:image/jpeg" not in html


def test_pdf_export(tmp_path, records):
    target = reports.export_pdf(records, tmp_path / "r.pdf", title="Case 2")
    data = target.read_bytes()
    assert data.startswith(b"%PDF")
    assert len(data) > 5000


def test_pdf_includes_forensics(tmp_path, records, image_with_stale_thumbnail):
    from photosleuth import forensics

    record = extract_metadata(image_with_stale_thumbnail, geocode=False)
    report = forensics.analyze(image_with_stale_thumbnail, record)
    html = reports.export_html(
        [record], tmp_path / "r.html", forensics={record["file"]: report}
    ).read_text(encoding="utf-8")
    assert "Thumbnail check" in html
    assert "Photoshop" in html


def test_custody_section(tmp_path, records):
    entries = [{"timestamp": "2026-01-01T00:00:00", "action": "analyze",
                "file_name": "x.jpg", "sha256": "a" * 64}]
    html = reports.export_html(
        records, tmp_path / "r.html", custody_entries=entries
    ).read_text(encoding="utf-8")
    assert "Chain of Custody" in html
    assert "a" * 64 in html


def test_unknown_template_falls_back_to_default(tmp_path, records):
    target = reports.export_html(records, tmp_path / "r.html", template="does-not-exist")
    assert "Summary" in target.read_text(encoding="utf-8")


def test_custom_template_is_used(tmp_path, records):
    custom = tmp_path / "templates"
    custom.mkdir()
    (custom / "mini.html").write_text(
        "<html><body><h1>{{ title }}</h1><p>{{ stats.total }} images</p></body></html>",
        encoding="utf-8",
    )
    html = reports.export_html(
        records, tmp_path / "r.html", template="mini", custom_dir=custom, title="Mini"
    ).read_text(encoding="utf-8")
    assert "<h1>Mini</h1>" in html
    assert "3 images" in html
    assert "Summary" not in html


def test_available_templates_includes_custom(tmp_path):
    custom = tmp_path / "templates"
    custom.mkdir()
    (custom / "brandA.html").write_text("x", encoding="utf-8")
    names = reports.available_templates(custom)
    assert "default" in names and "brandA" in names


def test_stats_are_correct(records):
    context = reports.build_context(records, include_thumbnails=False)
    assert context["stats"]["total"] == 3
    assert context["stats"]["geotagged"] == 2
    assert context["stats"]["with_exif"] == 2


def test_coordinates_are_rounded(records):
    context = reports.build_context(records, include_thumbnails=False)
    coordinates = [item["coordinates"] for item in context["images"] if item["coordinates"]]
    assert all(len(value.split(",")[0].split(".")[1]) == 6 for value in coordinates)


# --- static map -------------------------------------------------------------

def test_projection_matches_known_tile_coordinates():
    # Greenwich at zoom 0 sits in the middle of the single world tile.
    x, y = reports._deg_to_pixel(0.0, 0.0, 0)
    assert x == pytest.approx(128.0)
    assert y == pytest.approx(128.0)


def test_projection_is_monotonic():
    west, _ = reports._deg_to_pixel(0, -120, 5)
    east, _ = reports._deg_to_pixel(0, 120, 5)
    _, north = reports._deg_to_pixel(60, 0, 5)
    _, south = reports._deg_to_pixel(-60, 0, 5)
    assert west < east
    assert north < south


def test_zoom_picks_a_level_that_fits():
    close = [(48.8584, 2.2945, "a"), (48.8600, 2.2960, "b")]
    far = [(48.8584, 2.2945, "a"), (-33.8568, 151.2153, "b")]
    assert reports._pick_zoom(close, 1280, 900) > reports._pick_zoom(far, 1280, 900)


def test_static_map_renders_without_network(tmp_path, records, monkeypatch):
    """Tile fetching is best-effort: offline still produces a valid PNG."""
    monkeypatch.setattr(reports, "_paste_tiles", lambda *a, **k: False)
    target = reports.render_static_map(records, tmp_path / "map.png", 640, 480)
    from PIL import Image

    with Image.open(target) as image:
        assert image.size == (640, 480)
        assert image.format == "PNG"


def test_static_map_without_geotags_raises(tmp_path, image_plain):
    with pytest.raises(ValueError):
        reports.render_static_map(
            [extract_metadata(image_plain, geocode=False)], tmp_path / "m.png"
        )


def test_export_map_png_accepts_records(tmp_path, records, monkeypatch):
    monkeypatch.setattr(reports, "_paste_tiles", lambda *a, **k: False)
    assert reports.export_map_png(records, tmp_path / "m.png").is_file()


def test_export_map_png_accepts_a_saved_map(tmp_path, records, monkeypatch):
    monkeypatch.setattr(reports, "_paste_tiles", lambda *a, **k: False)
    html = reports.generate_map(records, tmp_path / "m.html")
    target = reports.export_map_png(html, tmp_path / "m.png")
    assert target.is_file()
