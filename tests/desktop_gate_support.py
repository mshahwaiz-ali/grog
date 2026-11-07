"""Real-engine fixtures for the D01 desktop gate (GUI-21): no hand-written signal values.

The synthetic engine run issues nine distinct READY signals, but each expires before the
next one is issued, so it never holds two READYs at the same instant (checked over 20 and
40 synthetic days). To test the multi-READY decision lane, a real snapshot is given a
``signals`` tuple of *real* engine ``SignalView`` objects captured at their own READY or
EXECUTION BLOCKED moments (status copied at capture, because the engine's status overlay is
mutable). Same technique as ``dataclasses.replace(snap, ...)`` in test_workstation.
"""

from __future__ import annotations

import copy
import dataclasses
from types import SimpleNamespace

from grog.domain.enums import SignalState
from ui_support import session


def captured_views():
    """Run the real engine to its end.

    Returns (ended session, READY views, blocked views, a PAUSED fresh snapshot taken at the
    last READY capture) with views keyed by signal id in engine issue order.
    """
    s = session()
    events = s.pipeline.signals.events
    seen, ready, blocked, live = 0, {}, {}, None
    while s.step():
        if len(events) == seen:
            continue
        seen = len(events)
        snap = s.snapshot()
        for v in snap.signals:
            if v.status.state is SignalState.READY and not v.pre_roll:
                bucket = blocked if v.status.blocked else ready
                if v.record.signal_id not in bucket:
                    bucket[v.record.signal_id] = dataclasses.replace(v, status=copy.copy(v.status))
                    if bucket is ready:
                        live = snap
    return s, ready, blocked, live


def composite(real_session, views, *, snap=None):
    """A session-like owner whose snapshot carries the given real signal views."""
    base = real_session.snapshot() if snap is None else snap
    composed = dataclasses.replace(base, signals=tuple(views))
    return SimpleNamespace(snapshot=lambda: composed, pipeline=real_session.pipeline)
