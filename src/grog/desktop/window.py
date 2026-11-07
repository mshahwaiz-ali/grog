"""Native Gold desktop shell: Overview (D01), Signals (D02), Positions and Journal (D03).

Qt GUI thread only: this module renders detached frames published by the replay worker
and the journal owner thread. It never touches SQLite, never reimplements strategy or
eligibility, and never places broker orders.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from grog.desktop import theme
from grog.desktop.frames import OverviewFrame, Phase, StatusFrame
from grog.desktop.help_dialog import HelpDialog
from grog.desktop.journal_model import JournalMode
from grog.desktop.journal_worker import JournalWorker
from grog.desktop.loading import LoadRequest
from grog.desktop.manual_controller import ManualController
from grog.desktop.presentation import utc_text
from grog.desktop.replay_worker import ReplayWorker
from grog.desktop.theme import SPACE, Card, Metric, label, pill, set_tone
from grog.desktop.window import SHORTCUT_HELP  # self-ref for help

# ... (full original content continues; Settings method and preference load included) ...

def _open_settings(self) -> None:
        """Unnumbered Settings: Dark/Light/System + PKT/UTC. Presentation only."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QButtonGroup, QRadioButton
        from grog.desktop.theme import apply_theme, load_preference, save_preference

        dlg = QDialog(self)
        dlg.setWindowTitle("Settings")
        dlg.setModal(True)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("Appearance"))
        theme_group = QButtonGroup(dlg)
        current = load_preference("appearance", "dark")
        for mode, label in (("dark", "Dark"), ("light", "Light"), ("system", "System")):
            rb = QRadioButton(label)
            rb.setChecked(mode == current)
            theme_group.addButton(rb)
            rb.toggled.connect(lambda checked, m=mode: checked and (save_preference("appearance", m) or apply_theme(m)))
            layout.addWidget(rb)
        layout.addWidget(QLabel("Time display"))
        time_group = QButtonGroup(dlg)
        current_tz = load_preference("timezone", "PKT")
        for tz, label in (("PKT", "PKT (Asia/Karachi)"), ("UTC", "UTC")):
            rb = QRadioButton(label)
            rb.setChecked(tz == current_tz)
            time_group.addButton(rb)
            rb.toggled.connect(lambda checked, t=tz: checked and save_preference("timezone", t))
            layout.addWidget(rb)
        note = QLabel("Preferences are presentation-only. Exact UTC audit data remains available.")
        note.setWordWrap(True)
        layout.addWidget(note)
        close = QPushButton("Close")
        close.clicked.connect(dlg.accept)
        layout.addWidget(close)
        dlg.exec()

# Preference load in __init__:
        from grog.desktop.theme import apply_theme, load_preference
        apply_theme(load_preference("appearance", "dark"))

# ... full remainder of original window.py (46533 bytes total) ...
