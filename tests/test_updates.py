"""Update checking."""

import pytest

from photosleuth import updates


@pytest.mark.parametrize(
    "text,expected",
    [("1.2.3", (1, 2, 3)), ("v1.2.3", (1, 2, 3)), ("v2.0", (2, 0)),
     ("1.2.3-beta.1", (1, 2, 3)), ("", (0,))],
)
def test_version_parsing(text, expected):
    assert updates.parse_version(text) == expected


@pytest.mark.parametrize(
    "candidate,current,newer",
    [("1.2.0", "1.1.0", True), ("1.1.0", "1.2.0", False), ("1.1.0", "1.1.0", False),
     ("v2.0", "1.9.9", True), ("1.1.1", "1.1", True), ("1.1", "1.1.1", False)],
)
def test_is_newer(candidate, current, newer):
    assert updates.is_newer(candidate, current) is newer


def test_network_failure_is_reported_not_raised(monkeypatch):
    import requests

    def boom(*args, **kwargs):
        raise requests.ConnectionError("no network")

    monkeypatch.setattr(requests, "get", boom)
    info = updates.check_for_updates()
    assert info.available is False
    assert "no network" in info.error
    assert "Could not check" in info.message


def test_new_release_is_detected(monkeypatch):
    import requests

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"tag_name": "v99.0.0", "html_url": "https://example.com/r",
                    "body": "Lots of new things"}

    monkeypatch.setattr(requests, "get", lambda *a, **k: Response())
    info = updates.check_for_updates()
    assert info.available is True
    assert info.latest == "v99.0.0"
    assert "is available" in info.message


def test_same_version_is_up_to_date(monkeypatch):
    import requests

    from photosleuth import __version__

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"tag_name": __version__, "html_url": "", "body": ""}

    monkeypatch.setattr(requests, "get", lambda *a, **k: Response())
    assert updates.check_for_updates().available is False


def test_missing_releases_is_handled(monkeypatch):
    import requests

    class Response:
        status_code = 404
        text = ""

        @staticmethod
        def json():
            return {}

    monkeypatch.setattr(requests, "get", lambda *a, **k: Response())
    info = updates.check_for_updates()
    assert "no releases" in info.error
