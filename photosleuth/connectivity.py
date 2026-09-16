"""One place that decides whether the network may be used, and whether it works.

Every feature that could touch the internet asks here first. That gives three
things the app needs:

* **Nothing hangs.** A probe with a short timeout beats a thirty-second socket
  timeout inside an analysis loop.
* **Offline is a first-class state, not an error.** Features that cannot run
  say so immediately and explain why, and everything that can run from cache
  still runs.
* **Offline can be chosen.** "Work offline" is a privacy setting as much as a
  connectivity one: it guarantees no image, coordinate or query leaves the
  machine, which matters for a tool used on sensitive material.
"""

from __future__ import annotations

import socket
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, List, Optional

from .config import load_config

# Probed over HTTPS rather than by opening a raw socket, because that is the
# path the app's real calls take: behind a corporate proxy or a firewall that
# permits only 443, a raw connection to a DNS port fails while the application
# works perfectly. Only hosts PhotoSleuth already talks to are contacted, so
# the probe reveals nothing the app was not going to reveal anyway.
PROBE_URLS = (
    "https://tile.openstreetmap.org/0/0/0.png",     # map tiles
    "https://nominatim.openstreetmap.org/status.php",  # geocoding, has a status endpoint
)

# Last-resort probe when requests is unavailable.
PROBE_HOSTS = (("1.1.1.1", 53), ("8.8.8.8", 53))

PROBE_TIMEOUT = 2.0
FRESH_SECONDS = 30.0          # how long a result is trusted before re-probing
OFFLINE_RETRY_SECONDS = 10.0  # re-probe sooner when offline, to notice recovery
MODE_CACHE_SECONDS = 2.0      # keep the settings file off the hot path


class NetworkMode(str, Enum):
    """What the user has allowed."""

    AUTOMATIC = "automatic"   # use the network when it is there
    OFFLINE = "offline"       # never touch the network, whatever is available

    @classmethod
    def parse(cls, value) -> "NetworkMode":
        """Accept a member, its value, or any reasonable spelling.

        ``str()`` on a str-Enum member yields "NetworkMode.OFFLINE" rather than
        "offline" on current Pythons, so members must be handled explicitly -
        otherwise passing one silently falls back to AUTOMATIC.
        """
        if isinstance(value, cls):
            return value
        text = value.value if isinstance(value, Enum) else str(value)
        try:
            return cls(text.strip().lower())
        except (ValueError, AttributeError):
            return cls.AUTOMATIC


@dataclass(frozen=True)
class NetworkState:
    """The answer to "can this feature run right now?"."""

    online: bool
    mode: NetworkMode
    checked_at: float = 0.0
    reason: str = ""

    @property
    def usable(self) -> bool:
        """True when a network call is both permitted and likely to succeed."""
        return self.online and self.mode is not NetworkMode.OFFLINE

    @property
    def blocked_by_choice(self) -> bool:
        return self.mode is NetworkMode.OFFLINE

    @property
    def label(self) -> str:
        if self.blocked_by_choice:
            return "Working offline"
        return "Online" if self.online else "Offline"

    @property
    def detail(self) -> str:
        if self.blocked_by_choice:
            return (
                "Offline mode is on, so nothing leaves this machine. "
                "Cached addresses and map tiles are still used."
            )
        if self.online:
            return "Connected: online features are available."
        return (
            "No internet connection. Everything that works from local data or "
            "the cache still runs; online features are paused until it returns."
        )


class ConnectivityMonitor:
    """Caches the last probe and hands out the current state cheaply."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._online: Optional[bool] = None
        self._checked_at = 0.0
        self._listeners: List[Callable[[NetworkState], None]] = []
        self._probing = False
        self._mode: Optional[NetworkMode] = None
        self._mode_read_at = 0.0

    # -- mode ----------------------------------------------------------
    def mode(self) -> NetworkMode:
        """The configured mode, cached so widgets can ask on every repaint."""
        now = time.monotonic()
        with self._lock:
            fresh = self._mode is not None and (now - self._mode_read_at) < MODE_CACHE_SECONDS
            if fresh:
                return self._mode

        resolved = NetworkMode.parse(
            load_config().get("network", {}).get("mode", NetworkMode.AUTOMATIC.value)
        )
        with self._lock:
            self._mode = resolved
            self._mode_read_at = now
        return resolved

    # -- state ---------------------------------------------------------
    def state(self, refresh: bool = False) -> NetworkState:
        """Current state, re-probing only when the cached answer is stale."""
        mode = self.mode()
        if mode is NetworkMode.OFFLINE:
            # Never probe in offline mode: that would be a network call too.
            return NetworkState(False, mode, time.monotonic(), "Offline mode is enabled.")

        with self._lock:
            age = time.monotonic() - self._checked_at
            ttl = FRESH_SECONDS if self._online else OFFLINE_RETRY_SECONDS
            stale = self._online is None or age > ttl

        if refresh or stale:
            self._probe()

        with self._lock:
            return NetworkState(
                online=bool(self._online),
                mode=mode,
                checked_at=self._checked_at,
                reason="" if self._online else "No route to the internet.",
            )

    def is_online(self, refresh: bool = False) -> bool:
        return self.state(refresh=refresh).usable

    def _probe(self) -> None:
        online = _reachable()
        with self._lock:
            changed = self._online is not None and self._online != online
            self._online = online
            self._checked_at = time.monotonic()

        if changed:
            self._notify()

    def refresh_async(self) -> None:
        """Probe on a worker thread; listeners hear about any change."""
        with self._lock:
            if self._probing:
                return
            self._probing = True

        def run() -> None:
            try:
                self._probe()
            finally:
                with self._lock:
                    self._probing = False

        threading.Thread(target=run, name="photosleuth-connectivity", daemon=True).start()

    # -- observers -----------------------------------------------------
    def add_listener(self, callback: Callable[[NetworkState], None]) -> None:
        self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[NetworkState], None]) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _notify(self) -> None:
        state = NetworkState(bool(self._online), self.mode(), self._checked_at)
        for callback in list(self._listeners):
            try:
                callback(state)
            except Exception:
                # A broken listener must not take the monitor down with it.
                continue

    def invalidate(self) -> None:
        """Forget the cached answer, e.g. after the user changes the mode."""
        with self._lock:
            self._online = None
            self._checked_at = 0.0
            self._mode = None
            self._mode_read_at = 0.0


def _reachable() -> bool:
    """Is the internet reachable by the same route the app's calls take?"""
    try:
        import requests
    except ImportError:
        requests = None

    if requests is not None:
        for url in PROBE_URLS:
            try:
                response = requests.head(url, timeout=PROBE_TIMEOUT, allow_redirects=True)
                # Any answer at all proves a route exists; a 4xx from the server
                # still means the packets got there and back.
                if response.status_code < 500:
                    return True
            except requests.RequestException:
                continue

    for host, port in PROBE_HOSTS:
        try:
            with socket.create_connection((host, port), timeout=PROBE_TIMEOUT):
                return True
        except OSError:
            continue
    return False


_monitor = ConnectivityMonitor()


def monitor() -> ConnectivityMonitor:
    return _monitor


def state(refresh: bool = False) -> NetworkState:
    return _monitor.state(refresh=refresh)


def is_online(refresh: bool = False) -> bool:
    """True when a network call is permitted and a route exists."""
    return _monitor.is_online(refresh=refresh)


def set_mode(mode) -> NetworkMode:
    """Persist the network mode and drop any cached probe result."""
    from .config import update_config

    resolved = NetworkMode.parse(mode)
    update_config(network={"mode": resolved.value})
    _monitor.invalidate()
    return resolved


class OfflineError(RuntimeError):
    """Raised when a feature genuinely cannot proceed without the network."""

    def __init__(self, feature: str, current: Optional[NetworkState] = None) -> None:
        current = current or state()
        self.feature = feature
        self.state = current
        if current.blocked_by_choice:
            message = (
                f"{feature} needs the internet, and PhotoSleuth is set to work offline. "
                "Change this in Settings → Network if you want to allow it."
            )
        else:
            message = (
                f"{feature} needs the internet, and there is no connection right now. "
                "It will work again once you are back online."
            )
        super().__init__(message)


def require(feature: str, refresh: bool = False) -> NetworkState:
    """Raise :class:`OfflineError` unless *feature* may use the network."""
    current = state(refresh=refresh)
    if not current.usable:
        raise OfflineError(feature, current)
    return current


def available(feature: str = "") -> bool:
    """Non-raising form of :func:`require`, for enabling and disabling UI."""
    return state().usable
