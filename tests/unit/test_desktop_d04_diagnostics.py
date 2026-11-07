"""D04 Diagnostics read model (GUI-52/53): R0 verdicts regrouped without new logic,
read-only reference status, journal group from the detached snapshot."""

from __future__ import annotations

from grog.desktop.diagnostics_model import (
    VERDICTS,
    DiagGroup,
    DiagRow,
    journal_group,
    overall,
    source_diagnostics,
)
from grog.desktop.journal_model import JournalMode, JournalSnapshot
from grog.ui.panels import diagnostics_lines
from ui_support import session


def test_gui52_groups_carry_every_r0_check_and_add_engine_and_reference():
    s = session()
    for _ in range(500):
        s.step()
    snap = s.snapshot()
    facts = source_diagnostics(snap, strategy_version="v0.2-proposal", cursor=s.cursor)
    titles = [g.title for g in facts.groups]
    assert titles[-2:] == ["ENGINE / ELIGIBILITY", "REFERENCE ADAPTER (READ-ONLY)"]
    r0 = ["".join(t for t, _ in line) for line in diagnostics_lines(snap)]
    text = facts.text()
    for line in r0[3:]:  # every R0 evidence string survives (same source of truth)
        evidence = line.split("]", 1)[-1].strip()
        # the only intended difference: the config sha256 is shown in full, not 16 hex
        evidence = evidence.replace(
            snap.source.config_hash[:16] + " ", snap.source.config_hash + " "
        )
        assert evidence in text
    assert (
        len(snap.source.config_hash) == 64 and f"Config sha256: {snap.source.config_hash} " in text
    )
    assert snap.source.config_hash[:16] + " " not in text.replace(snap.source.config_hash, "")
    assert all(r.verdict in VERDICTS or r.verdict == "" for g in facts.groups for r in g.rows)
    assert f"{s.cursor:,}" in text and "v0.2-proposal" in text


def test_gui53_reference_status_is_read_only_not_configured_in_replay():
    s = session()
    s.step()
    facts = source_diagnostics(s.snapshot(), strategy_version="v", cursor=s.cursor)
    ref = facts.groups[-1]
    assert ref.worst == "NOT CONFIGURED"
    assert "NO_REFERENCE_CONFIG" in ref.rows[0].text and "LIVE" not in ref.rows[
        0
    ].text.upper().replace("LIVE VALIDATION", "")


def test_journal_group_modes_never_claim_ok_without_a_writable_readable_journal():
    assert journal_group(None).worst == "UNKNOWN"
    base = dict(generation=1, sequence=1, source_id="syn", positions=(), events=(),
                decisions=(), claims=())  # fmt: skip
    for mode, worst in ((JournalMode.WRITABLE, "OK"), (JournalMode.READ_ONLY, "DEGRADED"),
                        (JournalMode.UNAVAILABLE, "ERROR")):  # fmt: skip
        g = journal_group(JournalSnapshot(mode=mode, reason="r", **base))
        assert g.worst == worst, (mode, g)


def test_overall_verdict_covers_every_group_and_never_says_ok_with_a_bad_journal():
    """The page verdict aggregates ALL groups (journal included); the R0 summary only
    covers replay source checks and is never used as overall health."""
    s = session()
    for _ in range(500):
        s.step()
    facts = source_diagnostics(s.snapshot(), strategy_version="v", cursor=s.cursor)
    assert facts.summary == "Summary: all checks OK"  # R0 scope: replay source checks
    base = dict(generation=1, sequence=1, source_id="syn", positions=(), events=(),
                decisions=(), claims=())  # fmt: skip

    def verdict(mode, stale=False):
        snap = None if mode is None else JournalSnapshot(mode=mode, reason="r", **base)
        return overall((*facts.groups, journal_group(snap)), stale=stale)

    tone, text = verdict(JournalMode.WRITABLE)
    assert tone == "ok" and "no problems found in any group" in text
    assert "reference adapter NOT CONFIGURED (expected in REPLAY" in text
    assert "all checks OK" not in text
    tone, text = verdict(JournalMode.READ_ONLY)
    assert tone == "warning" and "NEEDS ATTENTION — LOCAL JOURNAL / ERRORS DEGRADED" in text
    tone, text = verdict(JournalMode.UNAVAILABLE)
    assert tone == "error" and "LOCAL JOURNAL / ERRORS ERROR" in text
    tone, text = verdict(None)  # journal not opened: unknown, not OK
    assert tone == "warning" and "LOCAL JOURNAL / ERRORS UNKNOWN" in text
    tone, text = verdict(JournalMode.WRITABLE, stale=True)
    assert tone == "warning" and text.startswith("Overall (STALE")
    bad_source = DiagGroup("FEED HEALTH", (DiagRow("UNKNOWN", "Feed health: UNKNOWN"),))
    tone, text = overall((bad_source, *facts.groups[1:]))
    assert tone == "warning" and "FEED HEALTH UNKNOWN" in text
    unexpected = DiagGroup("FEED HEALTH", (DiagRow("NOT CONFIGURED", "threshold unset"),))
    assert "FEED HEALTH NOT CONFIGURED" in overall((unexpected, *facts.groups[1:]))[1]
    ok_journal = journal_group(JournalSnapshot(mode=JournalMode.WRITABLE, reason="r", **base))
    assert overall((ok_journal,)) == (
        "warning",
        "Overall: INCOMPLETE — no replay source diagnostics",
    )  # never OK from the journal card alone
