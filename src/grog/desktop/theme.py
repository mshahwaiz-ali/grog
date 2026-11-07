"""Gold desktop presentation tokens and Qt widget factories (UI only).

The active Dark/Light palette is selected by the desktop display controller. Rendering
changes never modify the replay engine, source selection, local journal or Textual UI.
Semantic tones are stored on widgets so an already-open dialog can be recolored.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

SPACE = (4, 8, 12, 16, 24)
RADIUS = 12
FONT_STACK = "'Inter', 'Noto Sans', 'DejaVu Sans', sans-serif"


@dataclass(frozen=True, slots=True)
class Palette:
    bg: str
    chrome: str
    surface: str
    raised: str
    active: str
    divider: str
    text: str
    muted: str
    tertiary: str
    focus: str
    buy: str
    sell: str
    warning: str
    error: str
    positive_bg: str
    positive_border: str
    warning_bg: str
    warning_border: str
    error_bg: str
    error_border: str
    ready_bg: str
    ready_border: str
    disabled_text: str
    disabled_bg: str
    control_border: str
    primary_bg: str
    primary_text: str
    primary_hover: str
    table_alt: str


PALETTES = {
    "Dark": Palette(
        bg="#111111",
        chrome="#151515",
        surface="#1B1B1B",
        raised="#242424",
        active="#2A2A29",
        divider="#323232",
        text="#F4F4F1",
        muted="#A7A7A3",
        tertiary="#92928E",
        focus="#D5C3A4",
        buy="#40B99A",
        sell="#E98C80",
        warning="#ECC37E",
        error="#F08E83",
        positive_bg="#153229",
        positive_border="#285C4D",
        warning_bg="#392D1B",
        warning_border="#73582F",
        error_bg="#3C2424",
        error_border="#824844",
        ready_bg="#302A22",
        ready_border="#786348",
        disabled_text="#787872",
        disabled_bg="#202020",
        control_border="#4B4B49",
        primary_bg="#40372B",
        primary_text="#F7EAD5",
        primary_hover="#514537",
        table_alt="#202020",
    ),
    "Light": Palette(
        bg="#FAFAF9",
        chrome="#F5F5F3",
        surface="#FFFFFF",
        raised="#F5F5F3",
        active="#EAEAE6",
        divider="#E6E6E3",
        text="#232320",
        muted="#64645E",
        tertiary="#77776F",
        focus="#71624C",
        buy="#177D63",
        sell="#B64E47",
        warning="#8D5F21",
        error="#B84541",
        positive_bg="#E2F5EC",
        positive_border="#9BD9BF",
        warning_bg="#FBF1E1",
        warning_border="#E7C991",
        error_bg="#FBE8E6",
        error_border="#E4ACA9",
        ready_bg="#F3EDE3",
        ready_border="#D6C4A4",
        disabled_text="#999991",
        disabled_bg="#F2F2F0",
        control_border="#C6C6C0",
        primary_bg="#EAE2D6",
        primary_text="#3B3024",
        primary_hover="#DED0BE",
        table_alt="#F7F7F5",
    ),
}


def _stylesheet(palette: Palette) -> str:
    """One neutral Qt stylesheet for every existing page and future dialog."""
    sheet = """
    QMainWindow, QDialog, QWidget#root { background: @BG@; color: @TEXT@; }
    QWidget { font-family: @FONT_STACK@; font-size: 14px; color: @TEXT@; }
    QToolTip { background: @RAISED@; color: @TEXT@; border: 1px solid @DIVIDER@;
        padding: 6px; }
    QFrame#sidebar { background: @CHROME@; border-right: 1px solid @DIVIDER@; }
    QFrame#statusStrip { background: @CHROME@; border-bottom: 1px solid @DIVIDER@; }
    QFrame#toolbar { background: @CHROME@; border-top: 1px solid @DIVIDER@; }
    QFrame#card, QFrame#metric { background: @SURFACE@;
        border: 1px solid @DIVIDER@; border-radius: 12px; }
    QFrame#metric[grogRaised="true"] { background: @RAISED@; }
    QLabel { background: transparent; }
    QLabel#brand { font-size: 22px; font-weight: 800; color: @FOCUS@;
        letter-spacing: 2px; }
    QLabel#brandSub { font-size: 11px; color: @MUTED@; }
    QLabel#pageTitle { font-size: 24px; font-weight: 700; color: @TEXT@; }
    QLabel#pagePurpose { font-size: 13px; color: @MUTED@; }
    QLabel#eyebrow { font-size: 11px; font-weight: 700; color: @MUTED@;
        letter-spacing: 1px; }
    QLabel#cardTitle { font-size: 15px; font-weight: 700; color: @TEXT@; }
    QLabel#body { font-size: 14px; color: @TEXT@; }
    QLabel#meta { font-size: 12px; color: @MUTED@; }
    QLabel#mono { font-family: 'DejaVu Sans Mono', 'Noto Sans Mono', monospace;
        font-size: 12px; color: @MUTED@; }
    QLabel#quote { font-size: 28px; font-weight: 700; color: @TEXT@; }
    QLabel#metricValue { font-size: 17px; font-weight: 650; color: @TEXT@; }
    QLabel#headline { font-size: 23px; font-weight: 750; color: @TEXT@; }
    QLabel#overviewHeadline { font-size: 28px; font-weight: 750; color: @TEXT@; }
    QLabel#overviewSummary { font-size: 16px; font-weight: 650; color: @TEXT@; }
    QLabel#overviewConditionText { font-size: 15px; color: @TEXT@; }
    QFrame#overviewCondition { background: @RAISED@; border: 1px solid @DIVIDER@;
        border-radius: 10px; }
    QPushButton#overviewAction { background: transparent; color: @FOCUS@;
        border: 1px solid @DIVIDER@; border-radius: 8px; text-align: left;
        padding: 7px 12px; font-size: 13px; font-weight: 600; }
    QPushButton#overviewAction:hover { background: @RAISED@; }
    QPushButton#overviewAction:focus { border: 1px solid @FOCUS@; }
    QLabel#navCount { font-size: 11px; color: @MUTED@; }
    QPushButton { background: @RAISED@; color: @TEXT@;
        border: 1px solid @CONTROL_BORDER@; border-radius: 8px;
        padding: 8px 14px; font-weight: 600; }
    QPushButton:hover { background: @ACTIVE@; }
    QPushButton:pressed { background: @ACTIVE@; }
    QPushButton:focus { border: 1px solid @FOCUS@; }
    QPushButton:disabled { color: @DISABLED_TEXT@; background: @DISABLED_BG@;
        border-color: @DIVIDER@; }
    QPushButton#primary { background: @PRIMARY_BG@; color: @PRIMARY_TEXT@;
        border-color: @READY_BORDER@; }
    QPushButton#primary:hover { background: @PRIMARY_HOVER@; }
    QPushButton#primary:disabled { color: @DISABLED_TEXT@;
        background: @DISABLED_BG@; border-color: @DIVIDER@; }
    QPushButton#nav, QPushButton#navActive { text-align: left; padding: 10px 12px;
        border-radius: 8px; border: 1px solid transparent; background: transparent; }
    QPushButton#nav:disabled { color: @DISABLED_TEXT@; }
    QPushButton#navActive { background: @ACTIVE@; color: @TEXT@;
        border-color: @DIVIDER@; }
    QPushButton#settingsNavActive { background: @ACTIVE@; color: @TEXT@;
        border-color: @DIVIDER@; text-align: left; }
    QLineEdit, QComboBox { background: @SURFACE@; color: @TEXT@;
        border: 1px solid @CONTROL_BORDER@; border-radius: 8px;
        padding: 6px 10px; selection-background-color: @ACTIVE@;
        selection-color: @TEXT@; }
    QLineEdit:focus, QComboBox:focus { border: 1px solid @FOCUS@; }
    QComboBox QAbstractItemView, QMenu, QListView { background: @SURFACE@;
        color: @TEXT@; border: 1px solid @DIVIDER@;
        selection-background-color: @ACTIVE@; selection-color: @TEXT@; }
    QRadioButton { color: @TEXT@; spacing: 8px; padding: 6px; }
    QRadioButton:focus { border: 1px solid @FOCUS@; border-radius: 6px; }
    QTabWidget::pane { border: 1px solid @DIVIDER@; border-radius: 8px;
        top: -1px; background: @SURFACE@; }
    QTabBar::tab { background: transparent; color: @MUTED@; padding: 8px 14px;
        border: 1px solid transparent; border-bottom: none; font-weight: 600; }
    QTabBar::tab:selected { color: @TEXT@; background: @SURFACE@;
        border-color: @DIVIDER@; border-top-left-radius: 8px;
        border-top-right-radius: 8px; }
    QTabBar::tab:focus { color: @FOCUS@; }
    QTableView { background: @SURFACE@; alternate-background-color: @TABLE_ALT@;
        color: @TEXT@; gridline-color: @DIVIDER@; border: none;
        selection-background-color: @ACTIVE@; selection-color: @TEXT@;
        font-size: 13px; }
    QTableView:focus { border: 1px solid @FOCUS@; }
    QHeaderView::section { background: @CHROME@; color: @MUTED@; border: none;
        border-bottom: 1px solid @DIVIDER@; padding: 6px 8px;
        font-size: 12px; font-weight: 700; }
    QScrollArea { border: none; background: @BG@; }
    QScrollArea > QWidget > QWidget { background: @BG@; }
    QScrollBar:horizontal { background: @BG@; height: 10px; }
    QScrollBar:vertical { background: @BG@; width: 10px; }
    QScrollBar::handle:horizontal { background: @DIVIDER@; border-radius: 5px;
        min-width: 30px; }
    QScrollBar::handle:vertical { background: @DIVIDER@; border-radius: 5px;
        min-height: 30px; }
    QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
    """
    for token in fields(Palette):
        key = f"@{token.name.upper()}@"
        sheet = sheet.replace(key, getattr(palette, token.name))
    return sheet.replace("@FONT_STACK@", FONT_STACK)


def _tones(palette: Palette) -> dict[str, tuple[str, str, str]]:
    return {
        "neutral": (palette.text, palette.raised, palette.divider),
        "ready": (palette.focus, palette.ready_bg, palette.ready_border),
        "warning": (palette.warning, palette.warning_bg, palette.warning_border),
        "error": (palette.error, palette.error_bg, palette.error_border),
        "ok": (palette.buy, palette.positive_bg, palette.positive_border),
        "info": (palette.muted, palette.surface, palette.divider),
    }


def activate(name: str) -> None:
    """Set this application's presentation colors; no OS-wide palette mutation."""
    if name not in PALETTES:
        raise ValueError(f"Unknown desktop theme: {name!r}")
    global BG, SURFACE, RAISED, DIVIDER, TEXT, TEXT_2, GOLD, BUY, SELL, WARNING, ERROR
    global TONES, STYLESHEET, ACTIVE_NAME
    palette = PALETTES[name]
    ACTIVE_NAME = name
    BG, SURFACE, RAISED, DIVIDER = (
        palette.bg,
        palette.surface,
        palette.raised,
        palette.divider,
    )
    TEXT, TEXT_2, GOLD = palette.text, palette.muted, palette.focus
    BUY, SELL, WARNING, ERROR = (
        palette.buy,
        palette.sell,
        palette.warning,
        palette.error,
    )
    TONES = _tones(palette)
    STYLESHEET = _stylesheet(palette)


def apply_to(root: QWidget) -> None:
    """Reapply the current palette and every inline semantic tone recursively."""
    widgets = [root, *root.findChildren(QWidget)]
    for widget in widgets:
        if isinstance(widget, QDialog) and widget.objectName() in ("chooser", "manualForm"):
            role = widget.objectName()
            widget.setStyleSheet(STYLESHEET + f"QDialog#{role} {{ background: {BG}; }}")
        elif widget is root:
            widget.setStyleSheet(STYLESHEET)
        tone = widget.property("_grog_tone")
        if isinstance(tone, str):
            set_tone(widget, tone, pill=bool(widget.property("_grog_pill")))
        accent = widget.property("_grog_accent")
        if isinstance(widget, Card) and isinstance(accent, str):
            widget.set_accent(accent)


activate("Dark")


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
    """Retain semantic state so existing widgets recolor on a theme switch."""
    widget.setProperty("_grog_tone", tone)
    widget.setProperty("_grog_pill", pill)
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
        self.setProperty("_grog_accent", tone)
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
