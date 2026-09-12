"""Light and dark themes.

Colours live in one palette dict per theme so widgets can ask for a role
(``palette()["accent"]``) instead of hard-coding hex values.
"""

from __future__ import annotations

from typing import Dict

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette

DARK: Dict[str, str] = {
    "window": "#141b26",
    "surface": "#1b2430",
    "surface_alt": "#212c3a",
    "border": "#2c3949",
    "text": "#e6edf5",
    "text_muted": "#93a3b8",
    "accent": "#38d6e0",
    "accent_text": "#062027",
    "selection": "#1d5e6b",
    "icon": "#c3d0e0",
    "danger": "#ff6b6b",
    "warning": "#ffb03e",
    "success": "#4fd18b",
    "grid": "#26313f",
}

LIGHT: Dict[str, str] = {
    "window": "#f4f6f9",
    "surface": "#ffffff",
    "surface_alt": "#eef2f7",
    "border": "#d3dbe5",
    "text": "#16202e",
    "text_muted": "#5f6f83",
    "accent": "#0e7f96",
    "accent_text": "#ffffff",
    "selection": "#bfe6ee",
    "icon": "#41526a",
    "danger": "#c0392b",
    "warning": "#b9770e",
    "success": "#1e8449",
    "grid": "#e3e9f0",
}

_current = "dark"


def resolve(name: str) -> str:
    """Turn 'system' into a concrete theme name."""
    if name in ("light", "dark"):
        return name
    try:
        from PySide6.QtGui import QGuiApplication

        hints = QGuiApplication.styleHints()
        scheme = getattr(hints, "colorScheme", None)
        if scheme is not None:
            return "light" if scheme() == Qt.ColorScheme.Light else "dark"
    except Exception:
        pass
    return "dark"


def palette(name: str = None) -> Dict[str, str]:
    return LIGHT if (name or _current) == "light" else DARK


def current() -> str:
    return _current


def stylesheet(name: str) -> str:
    c = palette(name)
    return f"""
    QWidget {{
        background: {c['window']};
        color: {c['text']};
        font-size: 13px;
    }}
    QMainWindow::separator {{ background: {c['border']}; width: 1px; height: 1px; }}

    QMenuBar {{ background: {c['surface']}; border-bottom: 1px solid {c['border']}; padding: 2px; }}
    QMenuBar::item {{ padding: 6px 11px; border-radius: 4px; background: transparent; }}
    QMenuBar::item:selected {{ background: {c['surface_alt']}; }}
    QMenu {{ background: {c['surface']}; border: 1px solid {c['border']}; padding: 5px; }}
    QMenu::item {{ padding: 6px 26px 6px 22px; border-radius: 4px; }}
    QMenu::item:selected {{ background: {c['selection']}; }}
    QMenu::item:disabled {{ color: {c['text_muted']}; }}
    QMenu::separator {{ height: 1px; background: {c['border']}; margin: 5px 8px; }}

    QToolBar {{ background: {c['surface']}; border-bottom: 1px solid {c['border']}; spacing: 3px; padding: 5px; }}
    QToolBar QToolButton {{ padding: 6px 9px; border-radius: 5px; color: {c['text']}; }}
    QToolBar QToolButton:hover {{ background: {c['surface_alt']}; }}
    QToolBar QToolButton:pressed, QToolBar QToolButton:checked {{ background: {c['selection']}; }}
    QToolBar QToolButton:disabled {{ color: {c['text_muted']}; }}

    QStatusBar {{ background: {c['surface']}; border-top: 1px solid {c['border']}; }}
    QStatusBar::item {{ border: none; }}

    QTabWidget::pane {{ border: 1px solid {c['border']}; background: {c['surface']}; border-radius: 6px; }}
    QTabBar::tab {{ background: transparent; color: {c['text_muted']}; padding: 8px 15px;
                    border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; }}
    QTabBar::tab:selected {{ background: {c['surface']}; color: {c['text']};
                             border: 1px solid {c['border']}; border-bottom: none; }}
    QTabBar::tab:hover:!selected {{ color: {c['text']}; }}

    QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background: {c['surface']}; border: 1px solid {c['border']};
        border-radius: 5px; padding: 6px 9px; selection-background-color: {c['selection']};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus,
    QDoubleSpinBox:focus, QComboBox:focus {{ border-color: {c['accent']}; }}
    QComboBox::drop-down {{ border: none; width: 20px; }}
    QComboBox QAbstractItemView {{ background: {c['surface']}; border: 1px solid {c['border']};
                                   selection-background-color: {c['selection']}; }}

    QPushButton {{
        background: {c['surface_alt']}; border: 1px solid {c['border']};
        border-radius: 5px; padding: 7px 15px; color: {c['text']};
    }}
    QPushButton:hover {{ border-color: {c['accent']}; }}
    QPushButton:pressed {{ background: {c['selection']}; }}
    QPushButton:disabled {{ color: {c['text_muted']}; border-color: {c['border']}; }}
    QPushButton[accent="true"] {{
        background: {c['accent']}; color: {c['accent_text']}; border: none; font-weight: 600;
    }}
    QPushButton[accent="true"]:hover {{ background: {c['accent']}; }}
    QPushButton[accent="true"]:disabled {{ background: {c['surface_alt']}; color: {c['text_muted']}; }}

    QTreeView, QTableView, QListView {{
        background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 6px;
        alternate-background-color: {c['surface_alt']};
        selection-background-color: {c['selection']}; selection-color: {c['text']};
        gridline-color: {c['grid']}; outline: none;
    }}
    QTreeView::item, QTableView::item, QListView::item {{ padding: 4px; }}
    QHeaderView::section {{
        background: {c['surface_alt']}; color: {c['text_muted']};
        padding: 6px 8px; border: none; border-right: 1px solid {c['border']};
        border-bottom: 1px solid {c['border']}; font-weight: 600;
    }}

    QScrollBar:vertical {{ background: transparent; width: 11px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 5px; min-height: 30px; }}
    QScrollBar::handle:vertical:hover {{ background: {c['text_muted']}; }}
    QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 0; }}
    QScrollBar::handle:horizontal {{ background: {c['border']}; border-radius: 5px; min-width: 30px; }}
    QScrollBar::handle:horizontal:hover {{ background: {c['text_muted']}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

    QProgressBar {{
        background: {c['surface_alt']}; border: none; border-radius: 4px;
        height: 8px; text-align: center; color: transparent;
    }}
    QProgressBar::chunk {{ background: {c['accent']}; border-radius: 4px; }}

    QGroupBox {{
        border: 1px solid {c['border']}; border-radius: 6px; margin-top: 13px; padding-top: 10px;
    }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 11px; padding: 0 5px; color: {c['text_muted']}; }}

    QSplitter::handle {{ background: {c['border']}; }}
    QSplitter::handle:horizontal {{ width: 1px; }}
    QSplitter::handle:vertical {{ height: 1px; }}

    QToolTip {{ background: {c['surface_alt']}; color: {c['text']};
                border: 1px solid {c['border']}; padding: 5px; }}
    QCheckBox::indicator, QRadioButton::indicator {{ width: 15px; height: 15px; }}
    QCheckBox::indicator:unchecked {{ border: 1px solid {c['border']};
                                      border-radius: 3px; background: {c['surface']}; }}
    QCheckBox::indicator:checked {{ border: 1px solid {c['accent']};
                                    border-radius: 3px; background: {c['accent']}; }}
    QSlider::groove:horizontal {{ height: 4px; background: {c['border']}; border-radius: 2px; }}
    QSlider::handle:horizontal {{ background: {c['accent']}; width: 14px;
                                  margin: -5px 0; border-radius: 7px; }}
    """


def apply(app, name: str) -> str:
    """Apply a theme to the QApplication. Returns the resolved theme name."""
    global _current
    resolved = resolve(name)
    _current = resolved
    c = palette(resolved)

    qpalette = QPalette()
    qpalette.setColor(QPalette.Window, QColor(c["window"]))
    qpalette.setColor(QPalette.WindowText, QColor(c["text"]))
    qpalette.setColor(QPalette.Base, QColor(c["surface"]))
    qpalette.setColor(QPalette.AlternateBase, QColor(c["surface_alt"]))
    qpalette.setColor(QPalette.Text, QColor(c["text"]))
    qpalette.setColor(QPalette.Button, QColor(c["surface_alt"]))
    qpalette.setColor(QPalette.ButtonText, QColor(c["text"]))
    qpalette.setColor(QPalette.Highlight, QColor(c["selection"]))
    qpalette.setColor(QPalette.HighlightedText, QColor(c["text"]))
    qpalette.setColor(QPalette.ToolTipBase, QColor(c["surface_alt"]))
    qpalette.setColor(QPalette.ToolTipText, QColor(c["text"]))
    qpalette.setColor(QPalette.PlaceholderText, QColor(c["text_muted"]))
    app.setPalette(qpalette)
    app.setStyleSheet(stylesheet(resolved))
    return resolved
