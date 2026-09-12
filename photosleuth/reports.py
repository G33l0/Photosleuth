"""Reporting: CSV export and interactive HTML maps."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

CSV_COLUMNS: Sequence[str] = (
    "file",
    "name",
    "size",
    "modified",
    "date_taken",
    "latitude",
    "longitude",
    "altitude_m",
    "location",
    "map_url",
    "camera_make",
    "camera_model",
    "lens",
    "exposure",
    "aperture",
    "iso",
    "focal_length",
    "software",
    "exif_tag_count",
)


def _row(metadata: Dict[str, Any]) -> Dict[str, Any]:
    gps = metadata.get("gps") or {}
    summary = metadata.get("summary") or {}
    return {
        "file": metadata.get("file", ""),
        "name": metadata.get("name", ""),
        "size": metadata.get("size", ""),
        "modified": metadata.get("modified", ""),
        "date_taken": metadata.get("date_taken", ""),
        "latitude": gps.get("latitude", ""),
        "longitude": gps.get("longitude", ""),
        "altitude_m": gps.get("altitude_m", ""),
        "location": metadata.get("location", ""),
        "map_url": metadata.get("map_url", ""),
        "camera_make": summary.get("Camera make", ""),
        "camera_model": summary.get("Camera model", ""),
        "lens": summary.get("Lens", ""),
        "exposure": summary.get("Exposure", ""),
        "aperture": summary.get("Aperture", ""),
        "iso": summary.get("ISO", ""),
        "focal_length": summary.get("Focal length", ""),
        "software": summary.get("Software", ""),
        "exif_tag_count": len(metadata.get("exif") or {}),
    }


def export_csv(records: Iterable[Dict[str, Any]], output_file) -> Path:
    """Write one CSV row per analysed image."""
    path = Path(output_file)
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)

    # newline="" is required on Windows or every row gets a blank line after it.
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CSV_COLUMNS))
        writer.writeheader()
        for metadata in records:
            if metadata:
                writer.writerow(_row(metadata))
    return path


def geotagged(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [record for record in records if record and record.get("gps")]


def generate_map(records: Iterable[Dict[str, Any]], output_file) -> Path:
    """Plot every geotagged image on an interactive HTML map."""
    try:
        import folium
    except ImportError as exc:  # pragma: no cover - import guard
        raise ImportError("Missing 'folium'. Install: pip install folium") from exc

    points = geotagged(records)
    if not points:
        raise ValueError("No geotagged images to plot.")

    path = Path(output_file)
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)

    latitudes = [point["gps"]["latitude"] for point in points]
    longitudes = [point["gps"]["longitude"] for point in points]
    centre = [sum(latitudes) / len(latitudes), sum(longitudes) / len(longitudes)]

    fmap = folium.Map(location=centre, zoom_start=5, tiles="OpenStreetMap")

    for point in points:
        gps = point["gps"]
        name = point.get("name") or Path(point.get("file", "")).name
        popup_lines = [f"<b>{_escape(name)}</b>"]
        if point.get("date_taken"):
            popup_lines.append(f"Taken: {_escape(point['date_taken'])}")
        if point.get("location"):
            popup_lines.append(_escape(point["location"]))
        popup_lines.append(f"{gps['latitude']:.6f}, {gps['longitude']:.6f}")
        if point.get("map_url"):
            popup_lines.append(f"<a href='{_escape(point['map_url'])}' target='_blank'>Google Maps</a>")

        folium.Marker(
            location=[gps["latitude"], gps["longitude"]],
            popup=folium.Popup("<br>".join(popup_lines), max_width=320),
            tooltip=name,
            icon=folium.Icon(color="red", icon="camera", prefix="fa"),
        ).add_to(fmap)

    if len(points) > 1:
        fmap.fit_bounds([[min(latitudes), min(longitudes)], [max(latitudes), max(longitudes)]])

    fmap.save(str(path))
    return path


def _escape(text: Any) -> str:
    """Escape user-controlled text before it goes into the map popup HTML."""
    import html

    return html.escape(str(text), quote=True)


# --------------------------------------------------------------------------
# JSON / HTML / PDF reporting
# --------------------------------------------------------------------------

TEMPLATE_DIR = Path(__file__).resolve().parent / "assets" / "templates"


def export_json(records: Iterable[Dict[str, Any]], output_file, indent: int = 2) -> Path:
    """Write the full metadata records as JSON."""
    import json

    path = Path(output_file)
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(list(records), handle, indent=indent, default=str, ensure_ascii=False)
    return path


def available_templates(custom_dir=None) -> List[str]:
    """List built-in templates plus any in the user's custom template folder."""
    names = {path.stem for path in TEMPLATE_DIR.glob("*.html")}
    if custom_dir:
        custom = Path(custom_dir).expanduser()
        if custom.is_dir():
            names.update(path.stem for path in custom.glob("*.html"))
    return sorted(names) or ["default"]


def _data_uri(path, max_edge: Optional[int] = None) -> str:
    """Inline an image so the HTML/PDF is a single self-contained file."""
    import base64
    import io

    source = Path(path)
    if not source.is_file():
        return ""
    try:
        from PIL import Image

        with Image.open(source) as image:
            image.load()
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGB")
            if max_edge:
                image.thumbnail((max_edge, max_edge), Image.LANCZOS)
            buffer = io.BytesIO()
            fmt = "PNG" if image.mode == "RGBA" else "JPEG"
            image.save(buffer, fmt, quality=82)
            encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
            return f"data:image/{fmt.lower()};base64,{encoded}"
    except Exception:
        return ""


def _format_coordinates(gps: Optional[Dict[str, Any]]) -> str:
    """Six decimal places is ~11 cm - more digits are noise in a report."""
    if not gps:
        return ""
    text = f"{gps['latitude']:.6f}, {gps['longitude']:.6f}"
    if gps.get("altitude_m") is not None:
        text += f" \u00b7 {gps['altitude_m']:g} m"
    return text


def _thumbnail_box(path, max_width: int) -> tuple:
    """Display size that keeps the aspect ratio and never upscales."""
    try:
        from PIL import Image

        with Image.open(path) as image:
            if not image.width or not image.height:
                return max_width, max_width
            width = min(max_width, image.width)
            height = max(1, round(image.height * width / image.width))
            return width, height
    except Exception:
        return max_width, max_width


def _dimensions(metadata: Dict[str, Any]) -> str:
    exif = metadata.get("exif") or {}
    width = exif.get("EXIF ExifImageWidth") or exif.get("Image ImageWidth")
    height = exif.get("EXIF ExifImageLength") or exif.get("Image ImageLength")
    if width and height:
        return f"{width} x {height}"
    try:
        from PIL import Image

        with Image.open(metadata["file"]) as image:
            return f"{image.width} x {image.height}"
    except Exception:
        return ""


def build_context(
    records: Iterable[Dict[str, Any]],
    *,
    title: str = "PhotoSleuth Report",
    branding: Optional[Dict[str, Any]] = None,
    forensics: Optional[Dict[str, Dict[str, Any]]] = None,
    custody_entries: Optional[List[Dict[str, Any]]] = None,
    include_thumbnails: bool = True,
) -> Dict[str, Any]:
    """Assemble everything a template needs."""
    from datetime import datetime

    from . import __version__

    branding = branding or {}
    forensics = forensics or {}
    records = [record for record in records if record]

    images: List[Dict[str, Any]] = []
    cameras: set = set()
    dates: List[str] = []
    flagged = 0

    for metadata in records:
        item = dict(metadata)
        item["dimensions"] = _dimensions(metadata)
        item["coordinates"] = _format_coordinates(metadata.get("gps"))
        # "Taken" is already shown from date_taken; don't print it twice.
        item["summary"] = {
            label: value for label, value in (metadata.get("summary") or {}).items()
            if not (label == "Taken" and metadata.get("date_taken"))
        }
        if include_thumbnails:
            item["thumbnail"] = _data_uri(metadata.get("file", ""), max_edge=320)
            width, height = _thumbnail_box(metadata.get("file", ""), 150)
            item["thumbnail_width"] = width
            item["thumbnail_height"] = height
        entry = forensics.get(metadata.get("file", ""))
        if entry:
            item["forensics"] = entry
            item["sha256"] = (entry.get("hashes") or {}).get("sha256", "")
            if entry.get("flags"):
                flagged += 1
        summary = metadata.get("summary") or {}
        model = summary.get("Camera model")
        if model:
            cameras.add(f"{summary.get('Camera make', '')} {model}".strip())
        if metadata.get("date_taken"):
            dates.append(str(metadata["date_taken"]))
        images.append(item)

    date_range = ""
    if dates:
        low, high = min(dates), max(dates)
        date_range = low if low == high else f"{low} to {high}"

    logo = branding.get("logo_path") or ""
    logo_uri = _data_uri(logo, max_edge=128) if logo else _data_uri(
        Path(__file__).resolve().parent / "assets" / "logo_128.png", max_edge=128
    )

    return {
        "title": title,
        "generated": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z"),
        "version": __version__,
        "accent": branding.get("accent_colour") or "#1694b2",
        "organisation": branding.get("organisation", ""),
        "author": branding.get("author", ""),
        "footer_note": branding.get("footer_note", ""),
        "logo": logo_uri,
        "images": images,
        "custody": custody_entries or [],
        "stats": {
            "total": len(records),
            "geotagged": len(geotagged(records)),
            "with_exif": sum(1 for record in records if record.get("has_exif")),
            "flagged": flagged,
            "date_range": date_range,
            "cameras": ", ".join(sorted(c for c in cameras if c)),
        },
    }


def render_html(context: Dict[str, Any], template: str = "default", custom_dir=None) -> str:
    """Render a report template to an HTML string."""
    try:
        from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape
    except ImportError as exc:  # pragma: no cover - import guard
        raise ImportError("Missing 'Jinja2'. Install: pip install Jinja2") from exc

    search_paths = [str(TEMPLATE_DIR)]
    if custom_dir and Path(custom_dir).expanduser().is_dir():
        search_paths.insert(0, str(Path(custom_dir).expanduser()))

    environment = Environment(
        loader=FileSystemLoader(search_paths),
        autoescape=select_autoescape(["html", "xml"]),
    )
    name = template if str(template).endswith(".html") else f"{template}.html"
    try:
        rendered = environment.get_template(name)
    except TemplateNotFound:
        rendered = environment.get_template("default.html")
    return rendered.render(**context)


def export_html(
    records: Iterable[Dict[str, Any]],
    output_file,
    *,
    title: str = "PhotoSleuth Report",
    branding: Optional[Dict[str, Any]] = None,
    forensics: Optional[Dict[str, Dict[str, Any]]] = None,
    custody_entries: Optional[List[Dict[str, Any]]] = None,
    template: str = "default",
    custom_dir=None,
    include_thumbnails: bool = True,
) -> Path:
    """Write a self-contained HTML report."""
    context = build_context(
        records, title=title, branding=branding, forensics=forensics,
        custody_entries=custody_entries, include_thumbnails=include_thumbnails,
    )
    html = render_html(context, template=template, custom_dir=custom_dir)
    path = Path(output_file)
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path


# A QGuiApplication must exist (and stay alive) before Qt can lay out text.
# Creating and destroying one per export crashes, so the instance is cached.
_qt_application = None


def _ensure_qt_application():
    """Return a live QGuiApplication, creating a headless one if needed."""
    global _qt_application

    import os
    import sys as _sys

    from PySide6.QtGui import QGuiApplication

    existing = QGuiApplication.instance()
    if existing is not None:
        return existing

    # On a machine with no display (a server, a CI runner, or a CLI session
    # over SSH) Qt aborts the whole process unless a headless platform plugin
    # is selected before the application is constructed.
    if _sys.platform.startswith("linux") and not (
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    ):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    _qt_application = QGuiApplication([_sys.argv[0] if _sys.argv else "photosleuth"])
    return _qt_application


def export_pdf(
    records: Iterable[Dict[str, Any]],
    output_file,
    *,
    title: str = "PhotoSleuth Report",
    branding: Optional[Dict[str, Any]] = None,
    forensics: Optional[Dict[str, Dict[str, Any]]] = None,
    custody_entries: Optional[List[Dict[str, Any]]] = None,
    template: str = "default",
    custom_dir=None,
    include_thumbnails: bool = True,
) -> Path:
    """Render the same template to PDF using Qt's document engine.

    Qt is already a dependency of the desktop app, so this needs no extra
    PDF library and keeps HTML and PDF output identical.
    """
    context = build_context(
        records, title=title, branding=branding, forensics=forensics,
        custody_entries=custody_entries, include_thumbnails=include_thumbnails,
    )
    html = render_html(context, template=template, custom_dir=custom_dir)

    try:
        from PySide6.QtCore import QMarginsF, QSizeF
        from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter, QTextDocument
    except ImportError as exc:  # pragma: no cover - import guard
        raise ImportError(
            "PDF export needs PySide6. Install it with: pip install PySide6"
        ) from exc

    _ensure_qt_application()

    path = Path(output_file)
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)

    try:
        writer = QPdfWriter(str(path))
        writer.setPageSize(QPageSize(QPageSize.A4))
        writer.setPageMargins(QMarginsF(14, 16, 14, 16), QPageLayout.Millimeter)
        writer.setTitle(title)
        writer.setCreator(f"PhotoSleuth {context['version']}")
        writer.setResolution(96)

        document = QTextDocument()
        document.setHtml(html)
        page = writer.pageLayout().paintRectPixels(writer.resolution())
        document.setPageSize(QSizeF(page.width(), page.height()))
        document.print_(writer)
    except Exception as exc:
        raise RuntimeError(f"PDF rendering failed: {exc}") from exc

    return path


TILE_SIZE = 256
TILE_SERVER = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
OSM_ATTRIBUTION = "(c) OpenStreetMap contributors"


def _deg_to_pixel(latitude: float, longitude: float, zoom: int):
    """Web-Mercator projection: degrees -> global pixel coordinates."""
    import math

    scale = TILE_SIZE * (2 ** zoom)
    x = (longitude + 180.0) / 360.0 * scale
    latitude = max(-85.05112878, min(85.05112878, latitude))
    sin_lat = math.sin(math.radians(latitude))
    y = (0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)) * scale
    return x, y


def _pick_zoom(points, width: int, height: int, padding: int = 80) -> int:
    """Largest zoom level at which every marker still fits on the canvas."""
    if len(points) < 2:
        return 14
    latitudes = [p[0] for p in points]
    longitudes = [p[1] for p in points]
    for zoom in range(18, 0, -1):
        corners = [
            _deg_to_pixel(min(latitudes), min(longitudes), zoom),
            _deg_to_pixel(max(latitudes), max(longitudes), zoom),
        ]
        span_x = abs(corners[1][0] - corners[0][0])
        span_y = abs(corners[1][1] - corners[0][1])
        if span_x <= width - padding and span_y <= height - padding:
            return zoom
    return 1


def render_static_map(
    records: Iterable[Dict[str, Any]],
    output_file,
    width: int = 1280,
    height: int = 900,
    zoom: Optional[int] = None,
    timeout: int = 10,
) -> Path:
    """Draw a real map PNG by compositing OpenStreetMap tiles.

    This replaces screenshotting a browser: it needs no Qt WebEngine (which
    would add several hundred megabytes to the Windows build) and produces a
    deterministic image.  Tiles need network access, exactly as the HTML map
    does; without it the markers are still plotted on a plain background.
    """
    from PIL import Image, ImageDraw

    points = [
        (
            record["gps"]["latitude"],
            record["gps"]["longitude"],
            str(record.get("name") or Path(record.get("file", "")).name),
        )
        for record in records
        if record and record.get("gps")
    ]
    if not points:
        raise ValueError("No geotagged images to plot.")

    path = Path(output_file)
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)

    zoom = int(zoom) if zoom else _pick_zoom(points, width, height)
    centre_lat = sum(p[0] for p in points) / len(points)
    centre_lon = sum(p[1] for p in points) / len(points)
    centre_x, centre_y = _deg_to_pixel(centre_lat, centre_lon, zoom)
    left = centre_x - width / 2
    top = centre_y - height / 2

    canvas = Image.new("RGB", (width, height), (233, 231, 225))
    tiles_loaded = _paste_tiles(canvas, left, top, width, height, zoom, timeout)

    draw = ImageDraw.Draw(canvas, "RGBA")
    if not tiles_loaded:
        draw.text(
            (14, 14),
            "Map tiles unavailable (offline) - markers shown on a blank canvas.",
            fill=(120, 40, 40),
        )

    for latitude, longitude, name in points:
        px, py = _deg_to_pixel(latitude, longitude, zoom)
        x, y = px - left, py - top
        if not (-40 <= x <= width + 40 and -40 <= y <= height + 40):
            continue
        _draw_marker(draw, x, y, name)

    draw.rectangle([0, height - 18, width, height], fill=(255, 255, 255, 190))
    draw.text((6, height - 15), OSM_ATTRIBUTION, fill=(60, 60, 60))

    canvas.save(path, "PNG")
    return path


def _paste_tiles(canvas, left: float, top: float, width: int, height: int,
                 zoom: int, timeout: int) -> bool:
    """Fetch and paste the tiles covering the viewport. True if any loaded."""
    import io
    import math

    try:
        import requests
        from PIL import Image
    except ImportError:
        return False

    from . import __version__

    session = requests.Session()
    # OSM's tile policy requires an identifying User-Agent.
    session.headers["User-Agent"] = f"PhotoSleuth/{__version__} (map export)"

    max_index = 2 ** zoom
    first_x = math.floor(left / TILE_SIZE)
    first_y = math.floor(top / TILE_SIZE)
    last_x = math.floor((left + width) / TILE_SIZE)
    last_y = math.floor((top + height) / TILE_SIZE)

    loaded = 0
    for tile_x in range(first_x, last_x + 1):
        for tile_y in range(first_y, last_y + 1):
            if not 0 <= tile_y < max_index:
                continue
            url = TILE_SERVER.format(z=zoom, x=tile_x % max_index, y=tile_y)
            try:
                response = session.get(url, timeout=timeout)
                if response.status_code != 200:
                    continue
                with Image.open(io.BytesIO(response.content)) as tile:
                    tile.load()
                    canvas.paste(
                        tile.convert("RGB"),
                        (int(tile_x * TILE_SIZE - left), int(tile_y * TILE_SIZE - top)),
                    )
                loaded += 1
            except Exception:
                continue
    return loaded > 0


def _draw_marker(draw, x: float, y: float, label: str) -> None:
    """A pin with a white halo, matching the app's accent colours."""
    radius, stem = 9, 15
    draw.polygon(
        [(x - radius * 0.72, y - stem + radius * 0.55),
         (x + radius * 0.72, y - stem + radius * 0.55),
         (x, y)],
        fill=(255, 255, 255, 235),
    )
    draw.ellipse(
        [x - radius - 2, y - stem - radius - 2, x + radius + 2, y - stem + radius + 2],
        fill=(255, 255, 255, 235),
    )
    draw.ellipse(
        [x - radius, y - stem - radius, x + radius, y - stem + radius],
        fill=(22, 148, 178, 255),
    )
    draw.ellipse(
        [x - radius * 0.36, y - stem - radius * 0.36,
         x + radius * 0.36, y - stem + radius * 0.36],
        fill=(255, 255, 255, 255),
    )
    if label:
        draw.text((x + radius + 5, y - stem - 6), label[:26], fill=(28, 34, 46, 255))


def export_map_png(
    source,
    output_file=None,
    width: int = 1280,
    height: int = 900,
    **_legacy,
) -> Path:
    """Write a map PNG.

    Accepts either a list of metadata records (preferred) or the path of a
    previously saved folium HTML file, whose markers are read back out, so
    older callers keep working.
    """
    if output_file is None:
        raise ValueError("export_map_png() needs an output file.")

    if isinstance(source, (str, Path)):
        records = _records_from_map_html(Path(source))
    else:
        records = list(source)
    return render_static_map(records, output_file, width=width, height=height)


def _records_from_map_html(path: Path) -> List[Dict[str, Any]]:
    """Recover marker coordinates from a folium map saved by generate_map()."""
    import re

    if not path.is_file():
        raise FileNotFoundError(f"Map file not found: {path}")
    text = path.read_text(encoding="utf-8", errors="ignore")
    pairs = re.findall(r"L\.marker\(\s*\[([-\d.]+),\s*([-\d.]+)\]", text)
    records = [
        {"gps": {"latitude": float(lat), "longitude": float(lon)}, "name": ""}
        for lat, lon in pairs
    ]
    if not records:
        raise ValueError("No markers found in that map file.")
    return records
