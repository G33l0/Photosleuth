"""PySide6 desktop application for PhotoSleuth."""

__all__ = ["run"]


def run(argv=None) -> int:
    """Launch the desktop app (imported lazily so the CLI never loads Qt)."""
    from .app import run as _run

    return _run(argv)
