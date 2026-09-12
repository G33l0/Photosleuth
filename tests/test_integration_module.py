"""Windows shell integration: guarded so it is safe to run anywhere."""

import sys

import pytest

from photosleuth import integration


def test_extensions_cover_the_common_formats():
    for extension in (".jpg", ".jpeg", ".png", ".tiff", ".heic"):
        assert extension in integration.ASSOCIATED_EXTENSIONS


def test_launcher_command_quotes_the_executable():
    command = integration.launcher_command()
    assert command.startswith('"')
    assert "%1" in command


def test_icon_path_points_at_the_ico():
    assert integration.icon_path().endswith((".ico", ".exe,0", ",0"))


@pytest.mark.skipif(sys.platform.startswith("win"), reason="non-Windows guard")
def test_functions_refuse_politely_off_windows():
    assert integration.is_windows() is False
    for call in (
        integration.register_explorer_menu,
        integration.unregister_explorer_menu,
        integration.register_image_association,
        integration.unregister_image_association,
    ):
        with pytest.raises(integration.IntegrationError):
            call()


@pytest.mark.skipif(sys.platform.startswith("win"), reason="non-Windows guard")
def test_status_is_reported_off_windows():
    status = integration.association_status()
    assert status["platform"] == "not-windows"
    assert status["associations"] == 0


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows only")
def test_register_and_unregister_round_trip():
    integration.register_explorer_menu()
    assert integration.association_status()["explorer_menu"] is True
    integration.unregister_explorer_menu()
    assert integration.association_status()["explorer_menu"] is False
