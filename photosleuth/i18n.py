"""Lightweight JSON-backed translations.

Qt's .ts/.qm workflow needs `lrelease` at build time; plain JSON catalogues let
anyone add a language by dropping a file into ``assets/i18n`` and keep the
PyInstaller bundle simple.  Missing keys fall back to the English source text,
so an incomplete translation degrades gracefully instead of showing blanks.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

I18N_DIR = Path(__file__).resolve().parent / "assets" / "i18n"

# Languages shipped with the app.  'en' is the source language.
BUILTIN_LANGUAGES: Dict[str, str] = {
    "en": "English",
    "es": "Español",
    "fr": "Français",
    "de": "Deutsch",
    "pt": "Português",
    "ar": "العربية",
}

RTL_LANGUAGES = {"ar", "he", "fa", "ur"}

_catalogue: Dict[str, str] = {}
_language = "en"


def available_languages() -> List[Tuple[str, str]]:
    """Return (code, display name) for every catalogue we can find."""
    found: Dict[str, str] = {"en": BUILTIN_LANGUAGES["en"]}
    if I18N_DIR.is_dir():
        for path in sorted(I18N_DIR.glob("*.json")):
            code = path.stem
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                name = data.get("__language__") or BUILTIN_LANGUAGES.get(code, code)
            except (OSError, json.JSONDecodeError):
                name = BUILTIN_LANGUAGES.get(code, code)
            found[code] = name
    return sorted(found.items(), key=lambda item: item[1])


def set_language(code: Optional[str]) -> str:
    """Load a catalogue. Returns the code actually in use."""
    global _catalogue, _language

    code = (code or "en").strip()
    if code == "system":
        code = detect_system_language()

    if code == "en":
        _catalogue = {}
        _language = "en"
        return _language

    path = I18N_DIR / f"{code}.json"
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        _catalogue = {k: v for k, v in data.items() if not k.startswith("__") and isinstance(v, str)}
        _language = code
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("Could not load translation %s: %s", code, exc)
        _catalogue = {}
        _language = "en"
    return _language


def current_language() -> str:
    return _language


def is_rtl(code: Optional[str] = None) -> bool:
    return (code or _language) in RTL_LANGUAGES


def detect_system_language() -> str:
    import locale

    try:
        code, _ = locale.getdefaultlocale()
    except (ValueError, TypeError):
        code = None
    if not code:
        return "en"
    short = code.split("_")[0].lower()
    return short if (I18N_DIR / f"{short}.json").is_file() else "en"


def tr(text: str, **kwargs) -> str:
    """Translate *text*, then apply ``str.format`` placeholders."""
    translated = _catalogue.get(text, text)
    if kwargs:
        try:
            return translated.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            # A broken placeholder in a translation must not crash the UI.
            try:
                return text.format(**kwargs)
            except Exception:
                return text
    return translated


def write_template(output_file, strings: Optional[List[str]] = None) -> Path:
    """Write a translation template so new languages can be started easily."""
    path = Path(output_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    data: Dict[str, str] = {"__language__": "Language name here", "__code__": path.stem}
    for item in strings or sorted(SOURCE_STRINGS):
        data[item] = ""
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
    return path


# Strings used by the GUI, kept here so translators have one list to work from.
SOURCE_STRINGS: List[str] = [
    "File", "Edit", "View", "Tools", "Reports", "Help", "Language",
    "Open Images…", "Open Folder…", "Recent", "Clear Recent", "Exit",
    "Library", "Details", "Timeline", "Forensics", "Reverse Search", "Custody",
    "Analyze", "Cancel", "Close", "Save", "Export", "Settings", "About",
    "Search metadata…", "Filter", "No images loaded",
    "Drop images or a folder here", "or use File → Open",
    "Camera", "Exposure", "Location", "Software", "Other", "File Info",
    "Compare", "Compare Selected", "Strip Metadata", "Set Location…",
    "Export Report…", "Export CSV", "Export JSON", "Export HTML", "Export PDF",
    "Export Map", "Chain of Custody", "Verify Log", "Light", "Dark", "System",
    "Ready", "Analyzing…", "Done", "Error", "Warning", "images", "selected",
    "Zoom In", "Zoom Out", "Fit to Window", "Actual Size", "Rotate",
    "Latitude", "Longitude", "Altitude", "Address", "Apply", "Reset",
    "Check for Updates…", "A new version is available", "You are up to date",
]
