"""Asset loading: application icon plus the small vector icons used in the UI.

The action icons are drawn from inline SVG so they recolour with the theme and
need no binary files in the repository.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QImage, QPixmap

ASSETS = Path(__file__).resolve().parent.parent / "assets"

# 24x24 stroke icons; {c} is replaced with the current theme's icon colour.
_SVG = {
    "open-folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "open-file": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
    "analyze": '<circle cx="11" cy="11" r="6"/><path d="M15.5 15.5 21 21"/>',
    "compare": '<rect x="3" y="4" width="7" height="16" rx="1"/><rect x="14" y="4" width="7" height="16" rx="1"/>',
    "strip": '<path d="M4 7h16"/><path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/><path d="M6 7v12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V7"/>',
    "pin": '<path d="M12 21s7-6.4 7-11a7 7 0 1 0-14 0c0 4.6 7 11 7 11z"/><circle cx="12" cy="10" r="2.5"/>',
    "report": '<path d="M6 3h9l4 4v14a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"/><path d="M8 12h8M8 16h5"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1"/>',
    "zoom-in": '<circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l6 6M10.5 8v5M8 10.5h5"/>',
    "zoom-out": '<circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l6 6M8 10.5h5"/>',
    "fit": '<path d="M4 9V5a1 1 0 0 1 1-1h4M20 9V5a1 1 0 0 0-1-1h-4M4 15v4a1 1 0 0 0 1 1h4M20 15v4a1 1 0 0 1-1 1h-4"/>',
    "rotate": '<path d="M20 12a8 8 0 1 1-2.3-5.6"/><path d="M20 4v4h-4"/>',
    "timeline": '<path d="M3 12h18"/><circle cx="7" cy="12" r="2.4"/><circle cx="13" cy="12" r="2.4"/><circle cx="19" cy="12" r="2.4"/>',
    "shield": '<path d="M12 3l7 3v6c0 4.4-3 8-7 9-4-1-7-4.6-7-9V6z"/><path d="M9 12l2 2 4-4"/>',
    "web": '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.5 2.6 2.5 14.4 0 17M12 3.5c-2.5 2.6-2.5 14.4 0 17"/>',
    "custody": '<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M8 9h8M8 13h8M8 17h4"/>',
    "cancel": '<circle cx="12" cy="12" r="8.5"/><path d="M9 9l6 6M15 9l-6 6"/>',
    "refresh": '<path d="M4 12a8 8 0 0 1 13.7-5.7L20 8"/><path d="M20 4v4h-4"/><path d="M20 12a8 8 0 0 1-13.7 5.7L4 16"/><path d="M4 20v-4h4"/>',
    "map": '<path d="M9 4 3 6.5v13L9 17l6 3 6-2.5v-13L15 7z"/><path d="M9 4v13M15 7v13"/>',
}


def app_icon_path() -> Path:
    return ASSETS / "photosleuth.ico"


@lru_cache(maxsize=1)
def app_icon() -> QIcon:
    """The window/taskbar icon, with every size the .ico provides."""
    icon = QIcon()
    ico = app_icon_path()
    if ico.is_file():
        icon.addFile(str(ico))
    for name in ("logo_1024.png", "logo.png", "logo_256.png", "logo_128.png"):
        candidate = ASSETS / name
        if candidate.is_file():
            icon.addFile(str(candidate))
    return icon


@lru_cache(maxsize=1)
def logo_pixmap(size: int = 128) -> QPixmap:
    for name in ("logo.png", "logo_256.png", "logo_128.png"):
        candidate = ASSETS / name
        if candidate.is_file():
            pixmap = QPixmap(str(candidate))
            if not pixmap.isNull():
                return pixmap.scaled(
                    size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
    return QPixmap()


@lru_cache(maxsize=256)
def icon(name: str, colour: str = "#c8d2df", size: int = 24) -> QIcon:
    """Render one of the built-in stroke icons in *colour*."""
    body = _SVG.get(name)
    if not body:
        return QIcon()
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="{size}" height="{size}" '
        f'fill="none" stroke="{colour}" stroke-width="1.7" stroke-linecap="round" '
        f'stroke-linejoin="round">{body}</svg>'
    )
    image = QImage.fromData(QByteArray(svg.encode("utf-8")), "SVG")
    if image.isNull():
        return QIcon()
    return QIcon(QPixmap.fromImage(image))


def pil_to_qimage(image) -> QImage:
    """Convert a PIL image to a QImage that owns its buffer.

    ``QImage`` does not copy the data it is handed, so the bytes object must be
    kept alive - ``.copy()`` is what makes this safe to return.
    """
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA")
    data = image.tobytes("raw", image.mode)
    fmt = QImage.Format_RGB888 if image.mode == "RGB" else QImage.Format_RGBA8888
    bytes_per_line = (3 if image.mode == "RGB" else 4) * image.width
    return QImage(data, image.width, image.height, bytes_per_line, fmt).copy()


def placeholder_pixmap(size: QSize, colour: str = "#2a3446") -> QPixmap:
    pixmap = QPixmap(size)
    pixmap.fill(colour)
    return pixmap
