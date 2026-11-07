"""Gold desktop design system: tokens, one stylesheet and small widget factories.

Tokens follow docs/02 §16.1. Status always carries words as well as colour; gold is an
accent for identity and READY research proposals, never for warnings or safety states.
Every page (Overview, Signals; Positions/Journal/Diagnostics later) builds from these.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

BG = "#0B111A"
SURFACE = "#121D2A"
RAISED = "#192838"
DIVIDER = "#2B3C50"
TEXT = "#E7EDF5"
TEXT_2 = "#A1B1C3"
GOLD = "#E6BA63"
BUY = "#33C6A1"
SELL = "#FF7D7D"
WARNING = "#F2BE60"
ERROR = "#FF6666"

SPACE = (4, 8, 12, 16, 24)  # the only spacing steps used in layouts
RADIUS = 12
FONT_STACK = "'Inter', 'Noto Sans', 'DejaVu Sans', sans-serif"

TONES = {  # tone -> (text colour, background, border)
    "neutral": (TEXT, RAISED, DIVIDER),
    "ready": (GOLD, "#2A2416", "#6F5A33"),
    "warning": (WARNING, "#2C2414", "#6D5527"),
    "error": (ERROR, "#2D1719", "#6E2E33"),
    "ok": (BUY, "#11281F", "#24584A"),
    "info": (TEXT_2, SURFACE, DIVIDER),
}

STYLESHEET = f"""
QMainWindow, QWidget#root {{ background: {BG}; color: {TEXT}; }}
QWidget {{ font-family: {FONT_STACK}; font-size: 14px; color: {TEXT}; }}
QToolTip {{ background: {RAISED}; color: {TEXT}; border: 1px solid {DIVIDER}; padding: 6px; }}
QFrame#sidebar {{ background: #0E1621; border-right: 1px solid {DIVIDER}; }}
QFrame#statusStrip {{ background: #0E1621; border-bottom: 1px solid {DIVIDER}; }}
QFrame#toolbar {{ background: #0E1621; border-top: 1px solid {DIVIDER}; }}
QFrame#card {{ background: {SURFACE}; border: 1px solid {DIVIDER}; border-radius: {RADIUS}px; }}
QFrame#metric {{ background: {SURFACE}; border: 1px solid {DIVIDER}; border-radius: {RADIUS}px; }}
QLabel {{ background: transparent; }}
QLabel#brand {{ font-size: 22px; font-weight: 800; color: {GOLD}; letter-spacing: 2px; }}
QLabel#brandSub {{ font-size: 11px; color: {TEXT_2}; }}
QLabel#pageTitle {{ font-size: 24px; font-weight: 700; color: {TEXT}; }}
QLabel#pagePurpose {{ font-size: 13px; color: {TEXT_2}; }}
QLabel#eyebrow {{ font-size: 11px; font-weight: 700; color: {TEXT_2}; letter-spacing: 1px; }}
QLabel#cardTitle {{ font-size: 15px; font-weight: 700; color: {TEXT}; }}
QLabel#body {{ font-size: 14px; color: #DCE4EE; }}
QLabel#meta {{ font-size: 12px; color: {TEXT_2}; }}
QLabel#mono {{ font-family: 'DejaVu Sans Mono', 'Noto Sans Mono', monospace; font-size: 12px;
    color: {TEXT_2}; }}
QLabel#quote {{ font-size: 28px; font-weight: 700; color: {TEXT}; }}
QLabel#metricValue {{ font-size: 17px; font-weight: 650; color: {TEXT}; }}
QLabel#headline {{ font-size: 23px; font-weight: 750; }}
QLabel#navCount {{ font-size: 11px; color: {TEXT_2}; }}
QPushButton {{ background: {RAISED}; color: {TEXT}; border: 1px solid #36495E;
    border-radius: 8px; padding: 8px 14px; font-weight: 600; }}
QPushButton:hover {{ background: #22344A; }}
QPushButton:pressed {{ background: #15212F; }}
QPushButton:focus {{ border: 1px solid {GOLD}; }}
QPushButton:disabled {{ color: #5F6F82; background: #111B27; border-color: #223144; }}
QPushButton#primary {{ background: #3A2F1B; color: #F4D597; border-color: #7A6236; }}
QPushButton#primary:hover {{ background: #4A3C22; }}
QPushButton#primary:disabled {{ color: #5F6F82; background: #111B27; border-color: #223144; }}
QPushButton#nav, QPushButton#navActive {{ text-align: left; padding: 10px 12px;
    border-radius: 8px; border: 1px solid transparent; background: transparent; }}
QPushButton#nav:disabled {{ color: #5F6F82; }}
QPushButton#navActive {{ background: #2A2416; color: #F4D597; border-color: #5E4C2C; }}
QLineEdit, QComboBox {{ background: {SURFACE}; color: {TEXT}; border: 1px solid #36495E;
    border-radius: 8px; padding: 6px 10px; selection-background-color: #3A2F1B; }}
QLineEdit:focus, QComboBox:focus {{ border: 1px solid {GOLD}; }}
QComboBox QAbstractItemView {{ background: {SURFACE}; color: {TEXT};
    selection-background-color: #2A2416; }}
QTabWidget::pane {{ border: 1px solid {DIVIDER}; border-radius: 8px; top: -1px;
    background: {SURFACE}; }}
QTabBar::tab {{ background: transparent; color: {TEXT_2}; padding: 8px 14px;
    border: 1px solid transparent; border-bottom: none; font-weight: 600; }}
QTabBar::tab:selected {{ color: #F4D597; background: {SURFACE}; border-color: {DIVIDER};
    border-top-left-radius: 8px; border-top-right-radius: 8px; }}
QTabBar::tab:focus {{ color: {GOLD}; }}
QTableView {{ background: {SURFACE}; alternate-background-color: #15212F; color: {TEXT};
    gridline-color: {DIVIDER}; border: none; selection-background-color: #2A2416;
    selection-color: #F4D597; font-size: 13px; }}
QTableView:focus {{ border: 1px solid {GOLD}; }}
QHeaderView::section {{ background: #0E1621; color: {TEXT_2}; border: none;
    border-bottom: 1px solid {DIVIDER}; padding: 6px 8px; font-size: 12px; font-weight: 700; }}
QScrollBar:horizontal {{ background: {BG}; height: 10px; }}
QScrollBar::handle:horizontal {{ background: {DIVIDER}; border-radius: 5px; min-width: 30px; }}
QScrollArea {{ border: none; background: {BG}; }}
QScrollArea > QWidget > QWidget {{ background: {BG}; }}
QScrollBar:vertical {{ background: {BG}; width: 10px; }}
QScrollBar::handle:vertical {{ background: {DIVIDER}; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
"""


def label(text: str = "", role: str = "body", *, wrap: bool = False, select: bool = False):
    widget = QLabel(text)
    widget.setObjectName(role)
    widget.setTextFormat(Qt.TextFormat.PlainText)  # engine text is never parsed as markup
    widget.setWordWrap(wrap)
    if select:
        widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return widget


def pill(text: str = "", tone: str = "info") -> QLabel:
    widget = label(text, "pill")
    set_tone(widget, tone, pill=True)
    widget.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    return widget


def set_tone(widget: QWidget, tone: str, *, pill: bool = False) -> None:
    fg, bg, border = TONES.get(tone, TONES["info"])
    if pill:
        widget.setStyleSheet(
            f"color: {fg}; background: {bg}; border: 1px solid {border}; border-radius: 10px;"
            "padding: 3px 10px; font-size: 11px; font-weight: 700;"
        )
    else:
        widget.setStyleSheet(f"color: {fg};")


class Card(QFrame):
    """Rounded surface with an optional eyebrow title; content goes in ``body``."""

    def __init__(self, title: str | None = None, *, role: str = "card") -> None:
        super().__init__()
        self.setObjectName(role)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(SPACE[4] - 4, SPACE[3] + 2, SPACE[4] - 4, SPACE[3] + 2)
        self.body.setSpacing(SPACE[1])
        if title:
            self.body.addWidget(label(title.upper(), "eyebrow"))

    def set_accent(self, tone: str) -> None:
        fg, bg, border = TONES.get(tone, TONES["neutral"])
        self.setStyleSheet(
            f"QFrame#{self.objectName()} {{ background: {bg}; border: 1px solid {border};"
            f" border-left: 4px solid {fg}; border-radius: {RADIUS}px; }}"
        )


class Metric(Card):
    """A titled value with a caption, e.g. BID / ASK / spread or an H1/M15/M5 state."""

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
