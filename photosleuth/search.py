"""Reverse image search via the Google Cloud Vision REST API."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Dict, List

from .config import get_api_key, load_config

try:
    import requests
except ImportError as exc:  # pragma: no cover - import guard
    raise ImportError("Missing 'requests'. Install: pip install requests") from exc

VISION_ENDPOINT = "https://vision.googleapis.com/v1/images:annotate"
TINEYE_ENDPOINT = "https://api.tineye.com/rest/search/"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # Vision rejects payloads beyond ~20 MB.

# Engines that run entirely inside PhotoSleuth via an official API.
API_ENGINES = ("google_vision", "tineye")

# Engines with no public API for uploads. Scraping their web endpoints breaks
# their terms of service and their HTML changes constantly, so PhotoSleuth
# opens the engine's own upload page and lets the user drop the file in.
BROWSER_ENGINES = {
    "google_lens": ("Google Lens", "https://lens.google.com/upload"),
    "yandex": ("Yandex Images", "https://yandex.com/images/"),
    "bing": ("Bing Visual Search", "https://www.bing.com/visualsearch"),
    "tineye_web": ("TinEye (website)", "https://tineye.com/"),
}

ENGINE_LABELS = {
    "google_vision": "Google Vision API",
    "tineye": "TinEye API",
    **{key: label for key, (label, _) in BROWSER_ENGINES.items()},
}


def available_engines():
    """Return ``[(key, label, needs_api_key)]`` for the engine picker."""
    engines = [
        ("google_vision", ENGINE_LABELS["google_vision"], True),
        ("tineye", ENGINE_LABELS["tineye"], True),
    ]
    engines += [(key, label, False) for key, (label, _) in BROWSER_ENGINES.items()]
    return engines


def engine_is_configured(engine: str) -> bool:
    if engine in BROWSER_ENGINES:
        return True
    return bool(get_api_key(engine))


class SearchError(RuntimeError):
    """Raised when a reverse image search cannot be completed."""


def reverse_image_search(image_path, engine: str = None, timeout: int = 30) -> Dict[str, Any]:
    """Run a reverse image search and return a normalised result dict.

    NOTE: this uploads the image to a third-party service.  Callers should
    confirm with the user before invoking it on sensitive images.
    """
    engine = engine or load_config().get("default_search_engine", "google_vision")

    from .connectivity import OfflineError, require

    try:
        require("Reverse image search")
    except OfflineError as exc:
        raise SearchError(str(exc)) from exc

    if engine == "google_vision":
        return _google_vision_search(image_path, timeout=timeout)
    if engine == "tineye":
        return _tineye_search(image_path, timeout=timeout)
    if engine in BROWSER_ENGINES:
        return open_in_browser(image_path, engine)
    raise SearchError(f"Unknown search engine: {engine!r}")


def open_in_browser(image_path, engine: str) -> Dict[str, Any]:
    """Open an engine's upload page and reveal the image in the file manager.

    These engines have no public upload API. Rather than scrape them, hand the
    job to the user's browser and put the file within easy reach.
    """
    import webbrowser

    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")
    if engine not in BROWSER_ENGINES:
        raise SearchError(f"{engine!r} is not a browser-handoff engine.")

    label, url = BROWSER_ENGINES[engine]
    opened = False
    # The browser itself needs the connection; opening a dead page helps nobody.
    try:
        opened = webbrowser.open(url)
    except Exception:
        opened = False

    return {
        "engine": engine,
        "engine_label": label,
        "mode": "browser",
        "file": str(path),
        "url": url,
        "opened": opened,
        "entities": [],
        "best_guess": [],
        "pages_with_matching_images": [],
        "full_matching_images": [],
        "partial_matching_images": [],
        "visually_similar_images": [],
        "landmarks": [],
        "instructions": (
            f"{label} has no public upload API. Its search page "
            f"{'was opened in your browser' if opened else 'is at ' + url}; "
            f"drag {path.name} onto it to run the search."
        ),
    }


def _tineye_search(image_path, timeout: int = 30) -> Dict[str, Any]:
    """Search the TinEye commercial API (requires a paid API key)."""
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    api_key = get_api_key("tineye")
    if not api_key:
        raise SearchError(
            "No TinEye API key configured. TinEye's API is a paid product - add the key in "
            "Settings, or use the 'TinEye (website)' engine to search by hand."
        )

    try:
        with open(path, "rb") as handle:
            response = requests.post(
                TINEYE_ENDPOINT,
                params={"api_key": api_key, "limit": 50},
                files={"image_upload": (path.name, handle, "application/octet-stream")},
                timeout=timeout,
            )
    except requests.Timeout as exc:
        raise SearchError(f"TinEye timed out after {timeout}s.") from exc
    except requests.RequestException as exc:
        raise SearchError(f"Network error contacting TinEye: {exc}") from exc

    if response.status_code in (401, 403):
        raise SearchError("TinEye rejected the API key. Check the key and your subscription.")
    if response.status_code != 200:
        raise SearchError(f"TinEye returned HTTP {response.status_code}: {response.text[:200]}")

    try:
        body = response.json()
    except ValueError as exc:
        raise SearchError("TinEye returned a response that was not valid JSON.") from exc

    if body.get("code") not in (200, None):
        messages = "; ".join(body.get("messages", [])) or "unknown error"
        raise SearchError(f"TinEye error: {messages}")

    matches = (body.get("results") or {}).get("matches", [])
    pages = []
    images = []
    for match in matches:
        for backlink in match.get("backlinks", []):
            if backlink.get("backlink"):
                pages.append({"url": backlink["backlink"], "title": (backlink.get("crawl_date") or "")})
            if backlink.get("url"):
                images.append(backlink["url"])

    return {
        "engine": "tineye",
        "engine_label": ENGINE_LABELS["tineye"],
        "mode": "api",
        "file": str(path),
        "entities": [],
        "best_guess": [],
        "pages_with_matching_images": pages,
        "full_matching_images": images,
        "partial_matching_images": [],
        "visually_similar_images": [],
        "landmarks": [],
        "total_results": (body.get("results") or {}).get("total_results", len(matches)),
    }


def _google_vision_search(image_path, timeout: int = 30) -> Dict[str, Any]:
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    api_key = get_api_key("google_vision")
    if not api_key:
        raise SearchError(
            "No Google Vision API key configured. Set one via the Configuration menu "
            "or `photosleuth --set-key google_vision=YOUR_KEY`."
        )

    size = path.stat().st_size
    if size > MAX_UPLOAD_BYTES:
        raise SearchError(f"Image is {size / 1024 / 1024:.1f} MB; Google Vision accepts up to 20 MB.")

    with open(path, "rb") as handle:
        encoded = base64.b64encode(handle.read()).decode("ascii")

    payload = {
        "requests": [
            {
                "image": {"content": encoded},
                "features": [
                    {"type": "WEB_DETECTION", "maxResults": 20},
                    {"type": "LANDMARK_DETECTION", "maxResults": 5},
                ],
            }
        ]
    }

    try:
        response = requests.post(
            VISION_ENDPOINT, params={"key": api_key}, json=payload, timeout=timeout
        )
    except requests.Timeout as exc:
        raise SearchError(f"Google Vision timed out after {timeout}s.") from exc
    except requests.RequestException as exc:
        raise SearchError(f"Network error contacting Google Vision: {exc}") from exc

    if response.status_code == 403:
        raise SearchError("Google Vision rejected the API key (403). Check the key and that billing is enabled.")
    if response.status_code == 400:
        raise SearchError(f"Google Vision rejected the request (400): {_error_message(response)}")
    if response.status_code != 200:
        raise SearchError(f"Google Vision returned HTTP {response.status_code}: {_error_message(response)}")

    try:
        body = response.json()
    except ValueError as exc:
        raise SearchError("Google Vision returned a response that was not valid JSON.") from exc

    responses = body.get("responses") or [{}]
    first = responses[0] if responses else {}
    if "error" in first:
        raise SearchError(f"Google Vision error: {first['error'].get('message', 'unknown error')}")

    return _normalise_vision(first, str(path))


def _error_message(response) -> str:
    try:
        return response.json().get("error", {}).get("message", response.text[:200])
    except ValueError:
        return response.text[:200]


def _normalise_vision(response: Dict[str, Any], image_path: str) -> Dict[str, Any]:
    web = response.get("webDetection", {}) or {}

    entities: List[Dict[str, Any]] = [
        {"description": item.get("description", ""), "score": round(float(item.get("score", 0.0)), 4)}
        for item in web.get("webEntities", [])
        if item.get("description")
    ]

    def _pages(key: str) -> List[Dict[str, str]]:
        return [
            {"url": item.get("url", ""), "title": (item.get("pageTitle") or "").strip()}
            for item in web.get(key, [])
            if item.get("url")
        ]

    def _urls(key: str) -> List[str]:
        return [item.get("url", "") for item in web.get(key, []) if item.get("url")]

    landmarks = [
        {
            "description": item.get("description", ""),
            "score": round(float(item.get("score", 0.0)), 4),
            "latitude": (item.get("locations") or [{}])[0].get("latLng", {}).get("latitude"),
            "longitude": (item.get("locations") or [{}])[0].get("latLng", {}).get("longitude"),
        }
        for item in response.get("landmarkAnnotations", [])
    ]

    return {
        "engine": "google_vision",
        "engine_label": ENGINE_LABELS["google_vision"],
        "mode": "api",
        "file": image_path,
        "entities": entities,
        "best_guess": [
            item.get("label", "") for item in web.get("bestGuessLabels", []) if item.get("label")
        ],
        "pages_with_matching_images": _pages("pagesWithMatchingImages"),
        "full_matching_images": _urls("fullMatchingImages"),
        "partial_matching_images": _urls("partialMatchingImages"),
        "visually_similar_images": _urls("visuallySimilarImages"),
        "landmarks": landmarks,
    }


def format_search_results(result: Dict[str, Any], limit: int = 10) -> str:
    """Render a search result dict for console output."""
    label = result.get("engine_label") or result.get("engine", "unknown")
    lines = [f"\n🔍 Reverse image search ({label}) — {result.get('file', '')}"]

    if result.get("mode") == "browser":
        lines.append(f"   {result.get('instructions', '')}")
        return "\n".join(lines)

    if result.get("best_guess"):
        lines.append(f"   Best guess: {', '.join(result['best_guess'])}")

    entities = result.get("entities") or []
    if entities:
        lines.append("\n   Entities found:")
        for entity in entities[:limit]:
            lines.append(f"     - {entity['description']} (score: {entity['score']:.2f})")
    else:
        lines.append("\n   No web entities found.")

    for landmark in (result.get("landmarks") or [])[:limit]:
        coords = ""
        if landmark.get("latitude") is not None:
            coords = f" @ {landmark['latitude']:.5f}, {landmark['longitude']:.5f}"
        lines.append(f"   🏛  Landmark: {landmark['description']} (score: {landmark['score']:.2f}){coords}")

    pages = result.get("pages_with_matching_images") or []
    lines.append(f"\n   Pages with matching images: {len(pages)}")
    for page in pages[:limit]:
        title = f" — {page['title']}" if page.get("title") else ""
        lines.append(f"     {page['url']}{title}")

    lines.append(f"   Full matching images: {len(result.get('full_matching_images') or [])}")
    lines.append(f"   Partial matching images: {len(result.get('partial_matching_images') or [])}")
    lines.append(f"   Visually similar images: {len(result.get('visually_similar_images') or [])}")
    return "\n".join(lines)
