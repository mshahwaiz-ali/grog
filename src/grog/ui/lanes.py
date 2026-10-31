"""Pure lane/exposure read model for the workstation (docs/02 §1, §5; docs/14 F-01..03, F-08).

A signal has two independent facts that must never be merged into one label:

* the **engine** lane — the immutable issuance (always READY at ``first_ready_ms``) and the
  current overlay (READY, EXECUTION BLOCKED) or a terminal state (EXPIRED, INVALIDATED),
  which is never resurrected;
* the **operator** lane — the first local journal action on that signal (ENTERED or
  USER_SKIPPED), read from :meth:`PositionJournal.signal_actions`. It is an overlay only:
  the signal record is never changed.

Exposure warnings are factual counts of locally recorded open positions. They never block
an action and never invent a position limit: the overlap/exposure policy is OPEN
(docs/11 §6.3). No Textual import.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from grog.domain.enums import Side, SignalState
from grog.journal.positions import ManualPosition
from grog.replay.session import SignalView

OperatorOverlay = Mapping[str, tuple[str, str | None]]  # signal_id -> (action, position_id)

OPERATOR_LABEL = {"ENTERED": "ENTERED", "USER_SKIPPED": "USER_SKIPPED"}


@dataclass(frozen=True, slots=True)
class SignalLane:
    signal_id: str
    side: Side
    issued_ms: int
    current: str  # READY | EXECUTION BLOCKED | EXPIRED | INVALIDATED
    terminal: bool
    blocked: bool
    pre_roll: bool
    operator: str | None  # ENTERED | USER_SKIPPED | None
    position_id: str | None

    @property
    def label(self) -> str:
        """Short combined label: operator lane first, engine lane always kept."""
        if self.operator is None:
            return self.current
        return f"{OPERATOR_LABEL[self.operator]} · {self.current}"

    @property
    def can_record(self) -> bool:
        """``e``/``s`` allowed: still READY (blocked => recorded OFF_PLAN), no prior action."""
        return not self.terminal and self.operator is None

    @property
    def fresh_opportunity(self) -> bool:
        """Belongs in the Live *actionable* lane: READY, unblocked, unused, in-window."""
        return self.can_record and not self.blocked and not self.pre_roll

    @property
    def why_not_actionable(self) -> str | None:
        if self.operator == "ENTERED":
            return f"already ENTERED locally ({self.position_id}) — not a new opportunity"
        if self.operator == "USER_SKIPPED":
            return "already USER_SKIPPED locally — not a new opportunity"
        if self.terminal:
            return f"{self.current} — terminal, never resurrected"
        if self.blocked:
            return "EXECUTION BLOCKED now — a fill would be recorded OFF_PLAN"
        if self.pre_roll:
            return "PRE-ROLL history — not a new alert"
        return None


def signal_lane(view: SignalView, overlay: OperatorOverlay | None = None) -> SignalLane:
    st = view.status
    r = view.record
    terminal = st.state is not SignalState.READY
    current = st.state.value if terminal else ("EXECUTION BLOCKED" if st.blocked else "READY")
    action, pos = (overlay or {}).get(r.signal_id, (None, None))
    return SignalLane(
        signal_id=r.signal_id,
        side=r.side,
        issued_ms=r.first_ready_ms,
        current=current,
        terminal=terminal,
        blocked=st.blocked and not terminal,
        pre_roll=view.pre_roll,
        operator=action,
        position_id=pos,
    )


@dataclass(frozen=True, slots=True)
class Exposure:
    open_count: int
    same_side: int
    opposite_side: int
    same_qty: Decimal
    unverified: int

    def warnings(self) -> list[str]:
        if not self.open_count:
            return []
        out = []
        if self.same_side:
            out.append(
                f"EXPOSURE: {self.same_side} open local position(s) on the SAME side "
                f"(remaining {_q(self.same_qty)}) — a new entry adds overlapping risk"
            )
        if self.opposite_side:
            out.append(
                f"EXPOSURE: {self.opposite_side} open local position(s) on the OPPOSITE side"
            )
        if self.unverified:
            out.append(f"{self.unverified} position(s) need broker reconciliation first")
        out.append("Overlap/exposure policy is OPEN: Grog shows this, it applies no limit.")
        return out


def exposure(positions: Sequence[ManualPosition], side: Side | None) -> Exposure:
    open_ = [p for p in positions if p.is_open]
    same = [p for p in open_ if side is not None and p.side is side]
    total = Decimal(0)
    for p in same:
        total += p.remaining_qty
    return Exposure(
        open_count=len(open_),
        same_side=len(same),
        opposite_side=sum(1 for p in open_ if side is not None and p.side is not side),
        same_qty=total,
        unverified=sum(1 for p in open_ if p.state.value == "RECONCILIATION_REQUIRED"),
    )


def _q(v: Decimal) -> str:
    return format(v.normalize(), "f") if v else "0"
