"""Application bootstrap: QApplication, theme, language, first window."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from .. import __version__, config as config_module
from ..i18n import is_rtl, set_language
from ..utils import IMAGE_EXTENSIONS, find_images

ORGANISATION = "PhotoSleuth"
APPLICATION = "PhotoSleuth"


def _expand(arguments: List[str]) -> List[str]:
    """Turn command-line arguments into a list of image files."""
    images: List[str] = []
    for argument in arguments:
        if argument.startswith("-"):
            continue
        path = Path(argument)
        if path.is_dir():
            images.extend(str(item) for item in find_images(path, recursive=True))
        elif path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            images.append(str(path))
    return images


def create_application(argv: Optional[List[str]] = None) -> QApplication:
    """Build (or reuse) the QApplication with PhotoSleuth's identity applied."""
    existing = QApplication.instance()
    if existing is not None:
        return existing

    # Without an explicit AppUserModelID, Windows groups the window under the
    # Python launcher and shows its icon in the taskbar instead of ours.
    if sys.platform.startswith("win"):
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                f"IamG2.PhotoSleuth.{__version__}"
            )
        except Exception:
            pass

    QApplication.setAttribute(Qt.AA_DontUseNativeMenuBar, False)
    application = QApplication(argv if argv is not None else sys.argv)
    application.setApplicationName(APPLICATION)
    application.setApplicationDisplayName("PhotoSleuth")
    application.setOrganizationName(ORGANISATION)
    application.setApplicationVersion(__version__)

    from .resources import app_icon

    application.setWindowIcon(app_icon())
    return application


def run(argv: Optional[List[str]] = None) -> int:
    """Launch the desktop application. Returns the process exit code."""
    arguments = list(argv if argv is not None else sys.argv[1:])

    application = create_application([sys.argv[0]] + arguments)

    config = config_module.load_config()
    ui = config.get("ui", {})

    from . import theme

    theme.apply(application, ui.get("theme", "system"))

    language = set_language(ui.get("language", "system"))
    application.setLayoutDirection(Qt.RightToLeft if is_rtl(language) else Qt.LeftToRight)

    from .main_window import MainWindow

    window = MainWindow()
    window.show()

    images = _expand(arguments)
    if images:
        window.add_paths(images)

    return application.exec()


def main() -> int:  # pragma: no cover - console entry point
    return run()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(run())
