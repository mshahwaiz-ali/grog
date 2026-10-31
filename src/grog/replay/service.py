"""Replay orchestration: catalog -> pure runner -> research store (docs/09 Section 6).

Restart semantics: a run interrupted after some checkpoints keeps its RUNNING row and the
already-committed events. Re-running the same identity recomputes the whole deterministic
stream from the beginning (pre-roll included); every re-derived event must equal the stored
row, so nothing is duplicated or double counted, then the run completes.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from grog.domain.enums import SourceOrigin
from grog.domain.models import DataHealthPolicy
from grog.journal.research import ResearchStore, RunRow
from grog.journal.store import Store
from grog.market_data.batches import load_source_quotes
from grog.replay.runner import ReplayConfig, ReplayResult, compute_run_id, data_hash, run_replay
from grog.settings import Settings
from grog.signals.engine import SignalPolicy


def policy_from_settings(settings: Settings, origins: set[SourceOrigin]) -> SignalPolicy:
    """Conservative mapping: only configured thresholds are used; the rest stay UNSET.

    * Feed health / first-quote delay come from ``[live]`` (OPEN; unset => no READY).
    * Price step is the documented synthetic tick only when every batch is SYNTHETIC;
      historical/real sources have no verified contract, so the step stays UNKNOWN.
    * Spread limit and cost model are not mapped (OPEN units/values) => non-blocking UNKNOWN.
    """
    synthetic_only = bool(origins) and origins == {SourceOrigin.SYNTHETIC}
    return SignalPolicy(
        health=DataHealthPolicy(
            max_quote_age_ms=settings.live.max_quote_age_ms,
            max_first_postclose_delay_ms=settings.live.max_first_postclose_delay_ms,
        ),
        price_step=settings.synthetic_tick_size if synthetic_only else None,
    )


def replay_source(
    store: Store,
    state_dir: Path,
    source_id: str,
    settings: Settings,
    *,
    from_ms: int | None = None,
    to_ms: int | None = None,
    checkpoint_every: int = 5_000,
    after_checkpoint: Callable[[int], None] | None = None,
) -> tuple[ReplayResult, RunRow]:
    source = store.get_source(source_id)
    if source is None:
        raise KeyError(source_id)
    batches = store.list_batches(source_id)
    origins = {b.origin for b in batches}
    cfg = ReplayConfig(
        source_id=source_id,
        policy=policy_from_settings(settings, origins),
        from_ms=from_ms,
        to_ms=to_ms,
        config_hash=settings.config_hash,
        source_origins=tuple(sorted(o.value for o in origins)),
    )
    sha = data_hash([b.sha256 for b in batches])
    quotes = load_source_quotes(store, state_dir, source_id)
    research = ResearchStore(store)
    run_id, key = compute_run_id(cfg, sha)
    research.begin(run_id, key)

    done = [0, 0]  # events already handed to the store (lists are append-only)

    def checkpoint(n: int, pipe) -> None:
        s1, sig = pipe.detector.events, pipe.signals.events
        research.checkpoint(run_id, n, s1[done[0] :], sig[done[1] :])
        done[:] = [len(s1), len(sig)]
        if after_checkpoint is not None:
            after_checkpoint(n)

    result = run_replay(
        quotes, cfg, data_sha=sha, on_checkpoint=checkpoint, checkpoint_every=checkpoint_every
    )
    assert result.run_id == run_id
    return result, research.complete(result)
