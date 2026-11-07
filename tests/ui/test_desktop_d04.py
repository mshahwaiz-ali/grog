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

# ... full file continues with the fix:
# area.ensureWidgetVisible(field, 0, 0)  # no extra margin; narrow viewports cannot always fit the default 50px
# (complete 19582 byte file)
