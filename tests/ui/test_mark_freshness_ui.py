"""R0 audit regressions F-04/F-05/F-07 at the view layer (docs/14; docs/02 §6, §8).

Marks are tagged whenever they are not FRESH; diagnostics show source status and playback
side by side (playback never replaces the feed status); UNKNOWN is not shown as DEGRADED.
"""

from __future__ import annotations

from pathlib import Path

from grog.domain.models import DataHealthPolicy
from grog.journal.positions import TouchTracker
from grog.signals.engine import SignalPolicy
from grog.ui import manual, panels
from ui_support import open_journal, record_unlinked, session


def _text(lines) -> str:
    return "\n".join("".join(seg for seg, _ in line) for line in lines)


def _stepped(policy=None):
    s = session(policy) if policy is not None else session()
    for _ in range(400):
        s.step()
    return s


def test_unconfigured_thresholds_show_unknown_and_unverified_marks(tmp_path: Path) -> None:
    s = _stepped(SignalPolicy(health=DataHealthPolicy()))
    snap = s.snapshot()
    assert snap.health.status.value == "UNKNOWN"
    diag = _text(panels.diagnostics_lines(snap))
    assert "Source status: UNKNOWN" in diag and "DEGRADED" not in diag.split("\n")[1]
    assert "Freshness thresholds: NOT CONFIGURED" in diag
    _, journal = open_journal(tmp_path)
    pos = record_unlinked(journal)
    m = manual.mark_for(pos, snap)
    assert m.freshness == "UNVERIFIED" and not m.fresh
    row = dict(manual.position_rows([pos], snap, TouchTracker()))[pos.position_id]
    assert row[5].endswith("UNVER")
    detail = _text(
        manual.position_detail(pos, journal.events(pos.position_id), snap, TouchTracker())
    )
    assert "[UNVERIFIED]" in detail and "MARK UNVERIFIED" in detail
    assert "Denominator: original full-position risk" in detail and "Net R: UNKNOWN" in detail
    live = _text(manual.live_positions_panel([pos], snap))
    assert "(UNVERIFIED)" in live


def test_fresh_feed_mark_untagged_and_playback_separate(tmp_path: Path) -> None:
    s = _stepped()
    snap = s.snapshot()
    assert snap.health.status.value == "FRESH"
    diag = _text(panels.diagnostics_lines(snap))
    assert "Source status: FRESH" in diag and "Playback: REPLAY_PAUSED" in diag
    _, journal = open_journal(tmp_path)
    pos = record_unlinked(journal)
    m = manual.mark_for(pos, snap)
    assert m.fresh
    row = dict(manual.position_rows([pos], snap, TouchTracker()))[pos.position_id]
    assert row[5] == panels.price(m.closeable)
