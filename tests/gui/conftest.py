"""Qt fixtures. Every GUI test runs on the offscreen platform."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6", reason="the desktop app needs PySide6")

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    """One QApplication for the whole session: Qt allows only one."""
    application = QApplication.instance() or QApplication(["photosleuth-tests"])
    yield application


@pytest.fixture
def themed(qapp):
    from photosleuth.gui import theme

    theme.apply(qapp, "dark")
    return qapp


@pytest.fixture
def pump(qapp):
    """Process pending events, e.g. after changing a widget's state."""

    def _pump(rounds: int = 4):
        for _ in range(rounds):
            qapp.processEvents()

    return _pump


@pytest.fixture
def wait_for_idle(qapp):
    """Block until every background worker has finished."""

    def _wait(runner, timeout_ms: int = 45000):
        loop = QEventLoop()

        def tick():
            if runner.busy:
                QTimer.singleShot(40, tick)
            else:
                loop.quit()

        QTimer.singleShot(40, tick)
        guard = QTimer()
        guard.setSingleShot(True)
        guard.timeout.connect(loop.quit)
        guard.start(timeout_ms)
        loop.exec()
        qapp.processEvents()
        return not runner.busy

    return _wait


@pytest.fixture
def strict_slots(monkeypatch):
    """Fail a test if an exception escapes a Qt slot instead of being swallowed."""
    escaped = []

    import sys

    original = sys.excepthook

    def hook(kind, value, tb):
        escaped.append(f"{kind.__name__}: {value}")
        original(kind, value, tb)

    monkeypatch.setattr(sys, "excepthook", hook)
    yield escaped
