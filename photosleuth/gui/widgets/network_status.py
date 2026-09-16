"""Status-bar indicator for the network state.

The point is that offline is never a surprise: the state is always on screen,
switching to offline is one click away, and the tooltip explains what still
works rather than only what does not.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor
from PySide6.QtWidgets import QMenu, QToolButton

from ... import connectivity as net
from .. import theme

# How often to re-probe in the background while the window is open.
POLL_SECONDS = 45


class NetworkStatusButton(QToolButton):
    """Shows Online / Offline / Working offline, and lets the user choose."""

    stateChanged = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAutoRaise(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setPopupMode(QToolButton.InstantPopup)
        self.setToolButtonStyle(Qt.ToolButtonTextOnly)

        self._menu = QMenu(self)
        self._group = QActionGroup(self)
        self._group.setExclusive(True)

        self.act_automatic = QAction("Use the internet when available", self, checkable=True)
        self.act_automatic.triggered.connect(lambda: self._set_mode(net.NetworkMode.AUTOMATIC))
        self.act_offline = QAction("Work offline (nothing leaves this machine)", self,
                                   checkable=True)
        self.act_offline.triggered.connect(lambda: self._set_mode(net.NetworkMode.OFFLINE))
        for action in (self.act_automatic, self.act_offline):
            self._group.addAction(action)
            self._menu.addAction(action)

        self._menu.addSeparator()
        self.act_check = QAction("Check connection now", self)
        self.act_check.triggered.connect(self.check_now)
        self._menu.addAction(self.act_check)
        self.setMenu(self._menu)

        net.monitor().add_listener(self._on_state)

        self._timer = QTimer(self)
        self._timer.setInterval(POLL_SECONDS * 1000)
        self._timer.timeout.connect(self._poll)
        self._timer.start()

        self.refresh()
        # The first probe runs off the UI thread so startup is never blocked.
        QTimer.singleShot(400, self.check_now)

    # -- state ---------------------------------------------------------
    def _poll(self) -> None:
        if net.monitor().mode() is not net.NetworkMode.OFFLINE:
            net.monitor().refresh_async()

    def check_now(self) -> None:
        if net.monitor().mode() is net.NetworkMode.OFFLINE:
            self.refresh()
            return
        net.monitor().refresh_async()
        QTimer.singleShot(2500, self.refresh)

    def _set_mode(self, mode) -> None:
        net.set_mode(mode)
        self.refresh()
        if mode is not net.NetworkMode.OFFLINE:
            self.check_now()

    def _on_state(self, state) -> None:
        # Listener fires on a worker thread; hop back to the UI thread.
        QTimer.singleShot(0, self.refresh)

    def refresh(self) -> None:
        state = net.state()
        colours = theme.palette()

        if state.blocked_by_choice:
            glyph, colour = "◆", colours["warning"]
        elif state.online:
            glyph, colour = "●", colours["success"]
        else:
            glyph, colour = "○", colours["danger"]

        self.setText(f"{glyph}  {state.label}")
        self.setStyleSheet(
            f"QToolButton {{ color: {colour}; padding: 2px 8px; border: none; }}"
            f"QToolButton::menu-indicator {{ image: none; }}"
        )
        self.setToolTip(state.detail)

        self.act_automatic.setChecked(not state.blocked_by_choice)
        self.act_offline.setChecked(state.blocked_by_choice)
        self.act_check.setEnabled(not state.blocked_by_choice)

        self.stateChanged.emit(state)

    def closeEvent(self, event) -> None:
        net.monitor().remove_listener(self._on_state)
        self._timer.stop()
        super().closeEvent(event)
