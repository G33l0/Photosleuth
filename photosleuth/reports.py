"""Reporting: CSV export and interactive HTML maps."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

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
