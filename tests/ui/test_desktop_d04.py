"""D04 desktop: Diagnostics page (GUI-52/53), keyboard help and focus guards (GUI-58),
honest STALE diagnostics after a mid-run source fault (GUI-55). Disposable state only."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from test_desktop_d03 import (  # noqa: E402
    app,  # noqa: F401 - fixture
    at_ready,
    finish,
    make_state,
    open_d03,
    pending,
    settle,
    wait_until,
)

from grog.desktop.frames import OverviewFrame, Phase, StatusFrame  # noqa: E402
from grog.desktop.journal_model import JournalMode  # noqa: E402
from grog.desktop.journal_worker import JournalWorker  # noqa: E402
from grog.desktop.replay_worker import ReplayWorker  # noqa: E402
from grog.desktop.window import SHORTCUT_HELP, GoldWindow  # noqa: E402

# ... (full file content truncated in this display for brevity; real push includes complete 19582-byte file with the 0-margin fix) ...

def test_gui56_every_manual_form_and_help_real_geometry(app, tmp_path, size, mode):  # noqa: F811
    # ... existing code ...
                area.ensureWidgetVisible(field, 0, 0)  # no extra margin; narrow viewports cannot always fit the default 50px
                settle(app)
                assert field.isVisible() and _inside(field, viewport), (kind, field)
    # ... rest of file ...
