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
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # Vision rejects payloads beyond ~20 MB.


class SearchError(RuntimeError):
    """Raised when a reverse image search cannot be completed."""


def reverse_image_search(image_path, engine: str = None, timeout: int = 30) -> Dict[str, Any]:
    """Run a reverse image search and return a normalised result dict.

    NOTE: this uploads the image to a third-party service.  Callers should
    confirm with the user before invoking it on sensitive images.
    """
    engine = engine or load_config().get("default_search_engine", "google_vision")
    if engine == "google_vision":
        return _google_vision_search(image_path, timeout=timeout)
    if engine == "tineye":
        raise SearchError("The TinEye backend is not implemented yet. Use 'google_vision'.")
    raise SearchError(f"Unknown search engine: {engine!r}")


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
    lines = [f"\n🔍 Reverse image search ({result.get('engine', 'unknown')}) — {result.get('file', '')}"]

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
