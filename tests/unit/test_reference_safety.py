"""M09-A safety: no order/position/account mutation API anywhere; prices never journal.

Behavioral checks first (import graph, journal untouched by a live session), then a source scan
of every Python module and the MQL5 exporter as a complement.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

from grog.live.session import ReferenceSession
from reference_support import HB_AGE, POLICY, SRC, T0, StepClock
from ui_support import open_journal

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "reference"
FORBIDDEN = re.compile(
    r"\b(OrderSend|OrderSendAsync|OrderModify|OrderClose|OrderDelete|OrderCheck|"
    r"PositionOpen|PositionClose|PositionModify|PositionCloseBy|CTrade|MqlTradeRequest|"
    r"TRADE_ACTION_\w+|order_send|order_check|positions_get|MetaTrader5)\b|Trade\.mqh"
)


def test_reference_runtime_does_not_import_journal_or_broker_code() -> None:
    code = (
        "import sys, grog.live.session, grog.adapters.mt5_reference.feed;"
        "print(sorted(m for m in sys.modules if m.startswith('grog.journal') or "
        "m.lower().startswith('metatrader')))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert out == "[]"


def test_live_prices_never_create_journal_records(tmp_path: Path) -> None:
    state, exporter = tmp_path / "state", tmp_path / "exp"
    shutil.copytree(FIXTURES, exporter)
    store, journal = open_journal(tmp_path)  # journal DB lives in <tmp>/state

    def journal_files() -> dict[str, str]:
        return {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in state.glob("state.sqlite3*")
        }

    before = journal_files()
    assert before
    s = ReferenceSession(exporter, SRC, POLICY, StepClock(T0 + 1_000), HB_AGE, state_dir=state)
    st = s.poll()
    assert st.last_quote is not None  # prices were processed ...
    assert journal.positions() == [] and journal.events() == []  # ... and nothing journaled
    assert journal_files() == before
    public = {n for n in dir(s) if not n.startswith("_")}
    assert not {n for n in public if re.search(r"order|trade|buy|sell|send|close", n)}
    store.close()


def test_source_scan_python_and_mql5_has_no_trade_api() -> None:
    files = [*sorted((ROOT / "src").rglob("*.py")), *sorted((ROOT / "mql5").glob("*.mq5"))]
    assert any(f.suffix == ".mq5" for f in files)
    hits = [
        f"{f.relative_to(ROOT)}:{n}: {line.strip()}"
        for f in files
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1)
        if FORBIDDEN.search(line)
    ]
    assert hits == []


def test_exporter_is_labeled_uncompiled_and_untested() -> None:
    text = (ROOT / "mql5" / "GrogReferenceExporter.mq5").read_text(encoding="utf-8")
    assert "NEVER COMPILED, NEVER RUN IN MT5" in text
    assert "MQL5_EXPORTER" in text and "GROG-MT5-REF/1" in text
    assert "CopyTicksRange" in text and "EventSetMillisecondTimer" in text
