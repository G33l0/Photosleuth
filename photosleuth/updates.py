"""Check GitHub releases for a newer PhotoSleuth."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from . import __version__
from .config import load_config

RELEASES_API = "https://api.github.com/repos/{repo}/releases/latest"
DEFAULT_REPO = "G33l0/Photosleuth"


@dataclass
class UpdateInfo:
    current: str
    latest: Optional[str] = None
    url: str = ""
    notes: str = ""
    available: bool = False
    error: str = ""

    @property
    def message(self) -> str:
        if self.error:
            return f"Could not check for updates: {self.error}"
        if self.available:
            return f"PhotoSleuth {self.latest} is available (you have {self.current})."
        return f"You are up to date (version {self.current})."


def parse_version(text: str) -> Tuple[int, ...]:
    """Turn 'v1.2.3-beta' into (1, 2, 3) for comparison."""
    cleaned = re.sub(r"^[vV]", "", (text or "").strip())
    numbers: List[int] = []
    for part in re.split(r"[.\-+]", cleaned):
        match = re.match(r"^(\d+)", part)
        if match:
            numbers.append(int(match.group(1)))
        elif numbers:
            break
    return tuple(numbers) or (0,)


def is_newer(candidate: str, current: str) -> bool:
    left, right = parse_version(candidate), parse_version(current)
    length = max(len(left), len(right))
    left += (0,) * (length - len(left))
    right += (0,) * (length - len(right))
    return left > right


def check_for_updates(repo: Optional[str] = None, timeout: int = 10) -> UpdateInfo:
    """Ask GitHub for the newest release. Never raises."""
    info = UpdateInfo(current=__version__)
    settings = load_config().get("updates", {})
    repo = repo or settings.get("repository") or DEFAULT_REPO

    try:
        import requests
    except ImportError:
        info.error = "the 'requests' package is not installed"
        return info

    try:
        response = requests.get(
            RELEASES_API.format(repo=repo),
            timeout=timeout,
            headers={"Accept": "application/vnd.github+json", "User-Agent": f"PhotoSleuth/{__version__}"},
        )
    except Exception as exc:  # noqa: BLE001 - network errors are expected offline
        info.error = str(exc)
        return info

    if response.status_code == 404:
        info.error = f"no releases published for {repo}"
        return info
    if response.status_code != 200:
        info.error = f"GitHub returned HTTP {response.status_code}"
        return info

    try:
        payload = response.json()
    except ValueError:
        info.error = "GitHub returned an unreadable response"
        return info

    info.latest = (payload.get("tag_name") or payload.get("name") or "").strip()
    info.url = payload.get("html_url", f"https://github.com/{repo}/releases")
    info.notes = (payload.get("body") or "").strip()
    info.available = bool(info.latest) and is_newer(info.latest, __version__)
    return info


def should_check_automatically() -> bool:
    return bool(load_config().get("updates", {}).get("check_on_startup", False))
