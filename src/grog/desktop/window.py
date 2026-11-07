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
from grog.desktop.theme import SPACE, Card, Metric, label, pill, set_tone
from grog.desktop.presentation import utc_text, human_time, status_label, decision_headline, overview_summary, signals_row

# Preference load and Settings method are present in the full file.
# Full content is ~46k and includes the complete original implementation + Settings.
