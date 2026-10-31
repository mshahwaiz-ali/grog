"""R0 audit regressions F-09/F-10 (docs/14; docs/08 §2): replay run identity and window
boundaries. Fixture thresholds are test-only declarations (tests/ui_support.py)."""

from __future__ import annotations

import pytest

from grog import __version__
from grog.domain.enums import ExitOutcome
from grog.replay import runner
from grog.replay.runner import ReplayConfig, compute_run_id, engine_code_hash, run_replay
from ui_support import FIXTURE_POLICY, synthetic_quotes


def test_engine_hash_is_stable_and_in_identity() -> None:
    h = engine_code_hash()
    assert len(h) == 64 and h == engine_code_hash()
    run_id, key = compute_run_id(ReplayConfig(source_id="syn"), "x")
    assert key["engine_code_hash"] == h
    assert key["code_version"] == f"{__version__}+engine.{h[:12]}"
    assert run_id.startswith("RUN-")


def test_run_id_changes_when_engine_code_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = ReplayConfig(source_id="syn")
    before, _ = compute_run_id(cfg, "x")
    monkeypatch.setattr(runner, "engine_code_hash", lambda: "0" * 64)
    after, key = compute_run_id(cfg, "x")
    assert after != before and key["code_version"].endswith("+engine.000000000000")


def test_engine_hash_covers_engine_sources_only() -> None:
    assert set(runner.ENGINE_PACKAGES) >= {"signals", "strategies", "risk", "analysis"}
    assert "ui" not in runner.ENGINE_PACKAGES and "journal" not in runner.ENGINE_PACKAGES


@pytest.fixture(scope="module")
def full():
    quotes = synthetic_quotes()
    return quotes, run_replay(quotes, ReplayConfig("syn", FIXTURE_POLICY), data_sha="x")


def test_exit_after_to_is_open_end_of_data_unresolved(full) -> None:
    quotes, res = full
    closed = [
        o
        for o in res.outcomes
        if o.outcome in (ExitOutcome.TARGET, ExitOutcome.STOP) and o.exit_time_ms > o.fill_time_ms
    ]
    assert closed, "synthetic data must contain at least one resolved simulated plan"
    o = closed[0]
    to_ms = o.fill_time_ms + 1  # window ends after the fill, before the exit
    cut = run_replay(quotes, ReplayConfig("syn", FIXTURE_POLICY, to_ms=to_ms), data_sha="x")
    same = next(x for x in cut.outcomes if x.signal_id == o.signal_id)
    assert same.outcome is ExitOutcome.OPEN and "END_OF_DATA_UNRESOLVED" in same.reasons
    assert same.exit_time_ms is None and same.gross_r is None
    for x in cut.outcomes:  # nothing at or after --to is ever used
        assert x.exit_time_ms is None or x.exit_time_ms < to_ms
    assert cut.run_id != res.run_id


def test_window_membership_uses_provider_time_for_cutoff(full) -> None:
    quotes, _ = full
    t = quotes[len(quotes) // 2].provider_time_ms
    cut = run_replay(quotes, ReplayConfig("syn", FIXTURE_POLICY, to_ms=t), data_sha="x")
    assert cut.processed_quotes == sum(1 for q in quotes if q.provider_time_ms < t)
