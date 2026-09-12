"""Windows shell integration: Explorer context menu (F32) and file
associations (F37).

Everything is written under ``HKEY_CURRENT_USER``, so no administrator rights
are needed and an uninstall only has to remove the user's own keys.  Every
function is a safe no-op on other platforms.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional, Tuple

PROG_ID = "PhotoSleuth.Image"
MENU_KEY = "PhotoSleuth"
MENU_TEXT = "Analyze with PhotoSleuth"

# Extensions offered to Windows as "Open with PhotoSleuth".
ASSOCIATED_EXTENSIONS: Tuple[str, ...] = (
    ".jpg", ".jpeg", ".jpe", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp",
    ".heic", ".heif", ".dng", ".cr2", ".nef", ".arw",
)


class IntegrationError(RuntimeError):
    """Raised when a registry operation cannot be completed."""


def is_windows() -> bool:
    return sys.platform.startswith("win")


def _require_windows() -> None:
    if not is_windows():
        raise IntegrationError("Shell integration is only available on Windows.")


def launcher_command() -> str:
    """The command Windows should run, quoted for the registry.

    A frozen build launches the .exe directly; a source checkout goes through
    ``pythonw -m photosleuth.gui`` so no console window flashes up.
    """
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable).resolve()}" "%1"'

    executable = Path(sys.executable)
    if is_windows():
        pythonw = executable.with_name("pythonw.exe")
        if pythonw.is_file():
            executable = pythonw
    return f'"{executable}" -m photosleuth "%1" --gui'


def icon_path() -> str:
    if getattr(sys, "frozen", False):
        return f"{Path(sys.executable).resolve()},0"
    ico = Path(__file__).resolve().parent / "assets" / "photosleuth.ico"
    return str(ico)


# --------------------------------------------------------------------------
# Explorer context menu
# --------------------------------------------------------------------------

def register_explorer_menu() -> str:
    """Add "Analyze with PhotoSleuth" to files and folders."""
    _require_windows()
    import winreg

    command = launcher_command()
    targets = [
        rf"Software\Classes\*\shell\{MENU_KEY}",
        rf"Software\Classes\Directory\shell\{MENU_KEY}",
        rf"Software\Classes\Directory\Background\shell\{MENU_KEY}",
    ]

    for index, base in enumerate(targets):
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as key:
                winreg.SetValueEx(key, None, 0, winreg.REG_SZ, MENU_TEXT)
                winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, icon_path())
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + r"\command") as key:
                # The background entry has no "%1"; pass the open folder instead.
                value = command.replace('"%1"', '"%V"') if index == 2 else command
                winreg.SetValueEx(key, None, 0, winreg.REG_SZ, value)
        except OSError as exc:
            raise IntegrationError(f"Could not write {base}: {exc}") from exc

    _notify_shell()
    return "Added “Analyze with PhotoSleuth” to the Explorer right-click menu."


def unregister_explorer_menu() -> str:
    _require_windows()
    import winreg

    removed = 0
    for base in (
        rf"Software\Classes\*\shell\{MENU_KEY}",
        rf"Software\Classes\Directory\shell\{MENU_KEY}",
        rf"Software\Classes\Directory\Background\shell\{MENU_KEY}",
    ):
        removed += int(_delete_tree(winreg.HKEY_CURRENT_USER, base))
    _notify_shell()
    return f"Removed {removed} Explorer menu entr{'y' if removed == 1 else 'ies'}."


# --------------------------------------------------------------------------
# File associations
# --------------------------------------------------------------------------

def register_image_association(extensions: Optional[List[str]] = None) -> str:
    """Register a ProgID and offer PhotoSleuth in "Open with" for images.

    This deliberately adds PhotoSleuth to *OpenWithProgids* rather than seizing
    the default handler: hijacking the default viewer without asking is exactly
    the behaviour people hate.
    """
    _require_windows()
    import winreg

    extensions = [e.lower() for e in (extensions or ASSOCIATED_EXTENSIONS)]

    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{PROG_ID}") as key:
            winreg.SetValueEx(key, None, 0, winreg.REG_SZ, "Image (PhotoSleuth)")
        with winreg.CreateKey(
            winreg.HKEY_CURRENT_USER, rf"Software\Classes\{PROG_ID}\DefaultIcon"
        ) as key:
            winreg.SetValueEx(key, None, 0, winreg.REG_SZ, icon_path())
        with winreg.CreateKey(
            winreg.HKEY_CURRENT_USER, rf"Software\Classes\{PROG_ID}\shell\open\command"
        ) as key:
            winreg.SetValueEx(key, None, 0, winreg.REG_SZ, launcher_command())
    except OSError as exc:
        raise IntegrationError(f"Could not create the {PROG_ID} ProgID: {exc}") from exc

    registered = 0
    for extension in extensions:
        try:
            with winreg.CreateKey(
                winreg.HKEY_CURRENT_USER,
                rf"Software\Classes\{extension}\OpenWithProgids",
            ) as key:
                winreg.SetValueEx(key, PROG_ID, 0, winreg.REG_NONE, b"")
            registered += 1
        except OSError:
            continue

    _notify_shell()
    return (
        f"PhotoSleuth now appears in “Open with” for {registered} image type(s). "
        "Your default image viewer was left unchanged."
    )


def unregister_image_association(extensions: Optional[List[str]] = None) -> str:
    _require_windows()
    import winreg

    extensions = [e.lower() for e in (extensions or ASSOCIATED_EXTENSIONS)]
    removed = 0
    for extension in extensions:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                rf"Software\Classes\{extension}\OpenWithProgids",
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                winreg.DeleteValue(key, PROG_ID)
                removed += 1
        except OSError:
            continue

    _delete_tree(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{PROG_ID}")
    _notify_shell()
    return f"Removed PhotoSleuth from “Open with” for {removed} image type(s)."


def association_status() -> dict:
    """Report what is currently registered (used by the settings dialog)."""
    if not is_windows():
        return {"platform": "not-windows", "explorer_menu": False, "associations": 0}

    import winreg

    def exists(path: str) -> bool:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path):
                return True
        except OSError:
            return False

    associated = 0
    for extension in ASSOCIATED_EXTENSIONS:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, rf"Software\Classes\{extension}\OpenWithProgids"
            ) as key:
                winreg.QueryValueEx(key, PROG_ID)
                associated += 1
        except OSError:
            continue

    return {
        "platform": "windows",
        "explorer_menu": exists(rf"Software\Classes\*\shell\{MENU_KEY}"),
        "associations": associated,
    }


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _delete_tree(root, path: str) -> bool:
    """Recursively delete a registry key (winreg cannot do this directly)."""
    import winreg

    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_ALL_ACCESS) as key:
            while True:
                try:
                    child = winreg.EnumKey(key, 0)
                except OSError:
                    break
                _delete_tree(root, f"{path}\\{child}")
        winreg.DeleteKey(root, path)
        return True
    except OSError:
        return False


def _notify_shell() -> None:
    """Ask Explorer to reload its association cache."""
    try:
        import ctypes

        SHCNE_ASSOCCHANGED = 0x08000000
        SHCNF_IDLIST = 0x0000
        ctypes.windll.shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None)
    except Exception:
        pass
