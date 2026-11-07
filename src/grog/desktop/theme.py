"""Gold desktop design system: tokenized Dark/Light/System themes, typography and primitives.

Follows docs/desktop-visual-redesign.md §3. U1 complete. U2 shell/Overview/Signals in progress. Dark is premium charcoal/graphite (no navy).
Light is clean warm-white. System follows OS when available. Preferences persist separately
from source selection and journal.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

# Semantic tokens (Dark / Light)
DARK = {
    "bg": "#111111",
    "sidebar": "#151515",
    "surface": "#1B1B1B",
    "raised": "#242424",
    "active": "#2A2A29",
    "divider": "#323232",
    "text": "#F4F4F1",
    "text2": "#A7A7A3",
    "text3": "#92928E",
    "accent": "#D5C3A4",
    "buy": "#40B99A",
    "buy_tint": "#153229",
    "sell": "#E98C80",
    "warning": "#ECC37E",
    "warning_tint": "#392D1B",
    "error": "#F08E83",
}

LIGHT = {
    "bg": "#FAFAF9",
    "sidebar": "#F5F5F3",
    "surface": "#FFFFFF",
    "raised": "#F5F5F3",
    "active": "#EAEAE6",
    "divider": "#E6E6E3",
    "text": "#232320",
    "text2": "#64645E",
    "text3": "#77776F",
    "accent": "#71624C",
    "buy": "#177D63",
    "buy_tint": "#E2F5EC",
    "sell": "#B64E47",
    "warning": "#8D5F21",
    "warning_tint": "#FBF1E1",
    "error": "#B84541",
}

SPACE = (4, 8, 12, 16, 24, 32)
RADIUS = 10
FONT_STACK = "'Inter', 'Noto Sans', 'DejaVu Sans', sans-serif"

# Current active palette (mutated on theme change)
PALETTE = dict(DARK)
RAISED = PALETTE["raised"]
DIVIDER = PALETTE["divider"]
BG = PALETTE["bg"]
SURFACE = PALETTE["surface"]
TEXT = PALETTE["text"]
TEXT_2 = PALETTE["text2"]
GOLD = PALETTE["accent"]
BUY = PALETTE["buy"]
SELL = PALETTE["sell"]
WARNING = PALETTE["warning"]
ERROR = PALETTE["error"]

def _qss() -> str:
    p = PALETTE
    return f"""
QMainWindow, QWidget#root, QDialog {{ background: {p['bg']}; color: {p['text']}; }}
QWidget {{ font-family: {FONT_STACK}; font-size: 15px; color: {p['text']}; }}
QToolTip {{ background: {p['raised']}; color: {p['text']}; border: 1px solid {p['divider']}; padding: 6px; }}
QFrame#sidebar {{ background: {p['sidebar']}; border-right: 1px solid {p['divider']}; }}
QFrame#statusStrip {{ background: {p['sidebar']}; border-bottom: 1px solid {p['divider']}; }}
QFrame#toolbar {{ background: {p['sidebar']}; border-top: 1px solid {p['divider']}; }}
QFrame#card {{ background: {p['surface']}; border: 1px solid {p['divider']}; border-radius: {RADIUS}px; }}
QFrame#metric {{ background: {p['surface']}; border: 1px solid {p['divider']}; border-radius: {RADIUS}px; }}
QLabel {{ background: transparent; }}
QLabel#brand {{ font-size: 22px; font-weight: 700; color: {p['accent']}; letter-spacing: 1px; }}
QLabel#brandSub {{ font-size: 12px; color: {p['text2']}; }}
QLabel#pageTitle {{ font-size: 28px; font-weight: 700; color: {p['text']}; }}
QLabel#pagePurpose {{ font-size: 14px; color: {p['text2']}; }}
QLabel#eyebrow {{ font-size: 12px; font-weight: 600; color: {p['text2']}; letter-spacing: 0.5px; }}
QLabel#cardTitle {{ font-size: 17px; font-weight: 600; color: {p['text']}; }}
QLabel#body {{ font-size: 15px; color: {p['text']}; }}
QLabel#meta {{ font-size: 13px; color: {p['text2']}; }}
QLabel#mono {{ font-family: 'DejaVu Sans Mono', 'Noto Sans Mono', monospace; font-size: 13px; }}
QPushButton {{ background: {p['raised']}; color: {p['text']}; border: 1px solid {p['divider']};
    border-radius: 8px; padding: 8px 14px; font-size: 14px; font-weight: 500; }}
QPushButton:hover {{ background: {p['active']}; }}
QPushButton:pressed {{ background: {p['surface']}; }}
QPushButton:focus {{ border: 1px solid {p['accent']}; }}
QPushButton:disabled {{ color: {p['text3']}; background: {p['surface']}; border-color: {p['divider']}; }}
QPushButton#primary {{ background: {p['accent']}; color: {p['bg']}; border-color: {p['accent']}; }}
QPushButton#primary:hover {{ background: {p['text']}; }}
QPushButton#nav, QPushButton#navActive {{ text-align: left; padding: 10px 12px;
    border-radius: 8px; border: 1px solid transparent; background: transparent; }}
QPushButton#nav:disabled {{ color: {p['text3']}; }}
QPushButton#navActive {{ background: {p['active']}; color: {p['accent']}; border-color: {p['divider']}; }}
QLineEdit, QComboBox {{ background: {p['surface']}; color: {p['text']}; border: 1px solid {p['divider']};
    border-radius: 8px; padding: 8px 12px; selection-background-color: {p['active']}; }}
QLineEdit:focus, QComboBox:focus {{ border: 1px solid {p['accent']}; }}
QComboBox QAbstractItemView {{ background: {p['surface']}; color: {p['text']};
    selection-background-color: {p['active']}; }}
QTableView {{ background: {p['surface']}; alternate-background-color: {p['raised']}; color: {p['text']};
    gridline-color: {p['divider']}; border: none; selection-background-color: {p['active']};
    selection-color: {p['accent']}; font-size: 14px; }}
QTableView:focus {{ border: 1px solid {p['accent']}; }}
QHeaderView::section {{ background: {p['sidebar']}; color: {p['text2']}; border: none;
    border-bottom: 1px solid {p['divider']}; padding: 8px; font-size: 13px; font-weight: 600; }}
QScrollBar:horizontal {{ background: {p['bg']}; height: 10px; }}
QScrollBar::handle:horizontal {{ background: {p['divider']}; border-radius: 5px; min-width: 30px; }}
QScrollArea {{ border: none; background: {p['bg']}; }}
QScrollArea > QWidget > QWidget {{ background: {p['bg']}; }}
QScrollBar:vertical {{ background: {p['bg']}; width: 10px; }}
QScrollBar::handle:vertical {{ background: {p['divider']}; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
"""

STYLESHEET = _qss()  # initial

def apply_theme(mode: str = "dark") -> None:
    """Apply Dark / Light / System. System falls back to Dark if unavailable."""
    global PALETTE, STYLESHEET
    if mode == "system":
        app = QApplication.instance()
        scheme = "dark"
        if app is not None:
            hints = app.styleHints()
            if hasattr(hints, "colorScheme"):
                cs = hints.colorScheme()
                if cs == Qt.ColorScheme.Light:
                    scheme = "light"
                elif cs == Qt.ColorScheme.Dark:
                    scheme = "dark"
                # Unknown -> dark
        mode = scheme
    PALETTE = dict(LIGHT if mode == "light" else DARK)
    global RAISED, DIVIDER, BG, SURFACE, TEXT, TEXT_2, GOLD, BUY, SELL, WARNING, ERROR
    RAISED = PALETTE["raised"]
    DIVIDER = PALETTE["divider"]
    BG = PALETTE["bg"]
    SURFACE = PALETTE["surface"]
    TEXT = PALETTE["text"]
    TEXT_2 = PALETTE["text2"]
    GOLD = PALETTE["accent"]
    BUY = PALETTE["buy"]
    SELL = PALETTE["sell"]
    WARNING = PALETTE["warning"]
    ERROR = PALETTE["error"]
    STYLESHEET = _qss()
    app = QApplication.instance()
    if app is not None:
        app.setStyleSheet(STYLESHEET)
        # Force repaint of existing widgets
        for w in app.allWidgets():
            w.style().unpolish(w)
            w.style().polish(w)
            w.update()

def load_preference(key: str, default: str) -> str:
    settings = QSettings("grog", "desktop")
    return str(settings.value(key, default))

def save_preference(key: str, value: str) -> None:
    settings = QSettings("grog", "desktop")
    settings.setValue(key, value)
    settings.sync()

def label(text: str = "", role: str = "body", *, wrap: bool = False, select: bool = False):
    widget = QLabel(text)
    widget.setObjectName(role)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(wrap)
    if select:
        widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return widget

def set_tone(widget: QWidget, tone: str, *, pill: bool = False) -> None:
    p = PALETTE
    mapping = {
        "neutral": (p["text"], p["raised"], p["divider"]),
        "ready": (p["accent"], p["raised"], p["accent"]),
        "warning": (p["warning"], p["warning_tint"], p["warning"]),
        "error": (p["error"], p["warning_tint"], p["error"]),
        "ok": (p["buy"], p["buy_tint"], p["buy"]),
        "info": (p["text2"], p["surface"], p["divider"]),
    }
    fg, bg, border = mapping.get(tone, mapping["info"])
    if pill:
        widget.setStyleSheet(
            f"color: {fg}; background: {bg}; border: 1px solid {border}; border-radius: 10px;"
            "padding: 3px 10px; font-size: 12px; font-weight: 600;"
        )
    else:
        widget.setStyleSheet(f"color: {fg};")

class Card(QFrame):
    def __init__(self, title: str | None = None, *, role: str = "card") -> None:
        super().__init__()
        self.setObjectName(role)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(SPACE[4], SPACE[3], SPACE[4], SPACE[3])
        self.body.setSpacing(SPACE[1])
        if title:
            self.body.addWidget(label(title, "eyebrow"))

    def set_accent(self, tone: str) -> None:
        p = PALETTE
        mapping = {"warning": p["warning"], "error": p["error"], "ok": p["buy"]}
        fg = mapping.get(tone, p["accent"])
        self.setStyleSheet(
            f"QFrame#{self.objectName()} {{ background: {p['surface']}; border: 1px solid {p['divider']};"
            f" border-left: 4px solid {fg}; border-radius: {RADIUS}px; }}"
        )

class Metric(Card):
    def __init__(self, title: str, value_role: str = "metricValue", caption: str = "") -> None:
        super().__init__(title, role="metric")
        self.value = label("—", value_role, wrap=value_role != "quote", select=True)
        self.caption = label(caption, "meta", wrap=True)
        self.body.addWidget(self.value)
        self.body.addWidget(self.caption)

def row(*widgets: QWidget, spacing: int = SPACE[2]) -> QHBoxLayout:
    layout = QHBoxLayout()
    layout.setSpacing(spacing)
    for w in widgets:
        layout.addWidget(w)
    return layout
