"""Offline/online handling: choice, detection, and graceful degradation."""

import pytest

from photosleuth import config, connectivity as net


@pytest.fixture(autouse=True)
def fresh_monitor():
    """Each test starts with no cached probe result or mode."""
    net.monitor().invalidate()
    yield
    net.set_mode(net.NetworkMode.AUTOMATIC)
    net.monitor().invalidate()


@pytest.fixture
def pretend(monkeypatch):
    """Force the reachability probe to a known answer."""

    def _set(online: bool):
        monkeypatch.setattr(net, "_reachable", lambda: online)
        net.monitor().invalidate()

    return _set


# --- modes ------------------------------------------------------------------

def test_default_mode_is_automatic():
    assert net.monitor().mode() is net.NetworkMode.AUTOMATIC


def test_mode_is_persisted():
    net.set_mode(net.NetworkMode.OFFLINE)
    assert config.load_config()["network"]["mode"] == "offline"
    assert net.monitor().mode() is net.NetworkMode.OFFLINE


@pytest.mark.parametrize("value", ["offline", "OFFLINE", " Offline "])
def test_mode_parsing_is_forgiving(value):
    assert net.NetworkMode.parse(value) is net.NetworkMode.OFFLINE


def test_unknown_mode_falls_back_to_automatic():
    assert net.NetworkMode.parse("nonsense") is net.NetworkMode.AUTOMATIC


# --- state ------------------------------------------------------------------

def test_offline_mode_never_probes(monkeypatch):
    """Probing in offline mode would itself be a network call."""
    probes = []
    monkeypatch.setattr(net, "_reachable", lambda: probes.append(1) or True)

    net.set_mode(net.NetworkMode.OFFLINE)
    for _ in range(5):
        net.state(refresh=True)
    assert probes == []


def test_offline_mode_state(pretend):
    pretend(True)
    net.set_mode(net.NetworkMode.OFFLINE)
    state = net.state()
    assert state.usable is False
    assert state.blocked_by_choice is True
    assert state.label == "Working offline"
    assert "nothing leaves this machine" in state.detail


def test_online_state(pretend):
    pretend(True)
    state = net.state(refresh=True)
    assert state.online is True
    assert state.usable is True
    assert state.label == "Online"


def test_offline_state(pretend):
    pretend(False)
    state = net.state(refresh=True)
    assert state.usable is False
    assert state.blocked_by_choice is False
    assert state.label == "Offline"
    assert "still runs" in state.detail


def test_result_is_cached(monkeypatch):
    calls = []
    monkeypatch.setattr(net, "_reachable", lambda: calls.append(1) or True)
    net.monitor().invalidate()

    net.state(refresh=True)
    for _ in range(50):
        net.is_online()
    assert len(calls) == 1


def test_listeners_hear_about_changes(monkeypatch):
    """A change is only a change against a known previous state."""
    seen = []
    monitor = net.monitor()
    listener = seen.append
    monitor.add_listener(listener)
    try:
        reachable = {"value": True}
        monkeypatch.setattr(net, "_reachable", lambda: reachable["value"])

        monitor.invalidate()
        net.state(refresh=True)          # establishes "online"; not a change yet
        assert seen == []

        reachable["value"] = False       # no invalidate: the previous state stands
        net.state(refresh=True)
        assert [state.online for state in seen] == [False]

        reachable["value"] = True
        net.state(refresh=True)
        assert [state.online for state in seen] == [False, True]
    finally:
        monitor.remove_listener(listener)


def test_a_broken_listener_does_not_break_the_monitor(pretend):
    def explode(_state):
        raise RuntimeError("listener is broken")

    monitor = net.monitor()
    monitor.add_listener(explode)
    try:
        pretend(True)
        net.state(refresh=True)
        pretend(False)
        assert net.state(refresh=True).online is False
    finally:
        monitor.remove_listener(explode)


# --- require / OfflineError -------------------------------------------------

def test_require_passes_when_online(pretend):
    pretend(True)
    assert net.require("Something").usable is True


def test_require_raises_when_disconnected(pretend):
    pretend(False)
    with pytest.raises(net.OfflineError) as excinfo:
        net.require("Reverse image search")
    assert "no connection" in str(excinfo.value)


def test_require_explains_a_deliberate_choice(pretend):
    pretend(True)
    net.set_mode(net.NetworkMode.OFFLINE)
    with pytest.raises(net.OfflineError) as excinfo:
        net.require("Reverse image search")
    message = str(excinfo.value)
    assert "set to work offline" in message
    assert "Settings" in message


# --- feature degradation ----------------------------------------------------

def test_geocoding_returns_promptly_when_offline(pretend, isolated_config):
    import time

    from photosleuth import core

    pretend(False)
    start = time.perf_counter()
    result = core.reverse_geocode(48.8584, 2.2945)
    elapsed = time.perf_counter() - start

    assert "Offline" in result
    assert elapsed < 0.5, "offline geocoding must not wait on a network timeout"


def test_geocoding_still_uses_the_cache_when_offline(pretend, isolated_config):
    from photosleuth import core
    from photosleuth.utils import default_cache

    default_cache().set(48.8584, 2.2945, "Cached address, Paris")
    pretend(False)
    assert core.reverse_geocode(48.8584, 2.2945) == "Cached address, Paris"


def test_reverse_search_fails_with_a_clear_message(pretend, isolated_config, image_ne):
    from photosleuth import search

    pretend(False)
    with pytest.raises(search.SearchError) as excinfo:
        search.reverse_image_search(image_ne)
    assert "internet" in str(excinfo.value).lower()


def test_update_check_reports_offline_rather_than_failing(pretend, isolated_config):
    from photosleuth import updates

    pretend(False)
    info = updates.check_for_updates()
    assert info.available is False
    assert "no internet connection" in info.error


def test_update_check_names_offline_mode(pretend, isolated_config):
    from photosleuth import updates

    pretend(True)
    net.set_mode(net.NetworkMode.OFFLINE)
    assert "work offline" in updates.check_for_updates().error


def test_static_map_still_plots_markers_offline(pretend, tmp_path, isolated_config, image_ne):
    from PIL import Image

    from photosleuth import reports
    from photosleuth.core import extract_metadata

    pretend(False)
    target = reports.render_static_map(
        [extract_metadata(image_ne, geocode=False)], tmp_path / "m.png", 400, 300
    )
    with Image.open(target) as image:
        assert image.size == (400, 300)
