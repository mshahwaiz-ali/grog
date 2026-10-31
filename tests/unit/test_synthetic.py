"""Synthetic generator: deterministic, canonical CSV v1, long enough for warm-up (M06)."""

from __future__ import annotations

from pathlib import Path

import pytest

from grog.market_data.import_csv import HEADER, parse_canonical_csv
from grog.replay import synthetic


def test_deterministic_and_seeded() -> None:
    a = synthetic.generate_csv(days=2, seed=7)
    assert a == synthetic.generate_csv(days=2, seed=7)
    assert a != synthetic.generate_csv(days=2, seed=8)
    assert a.splitlines()[0].decode() == ",".join(HEADER)


def test_default_stream_covers_full_h1_warmup_and_parses_strictly() -> None:
    data = synthetic.generate_csv()
    parsed = parse_canonical_csv(data, source_id="syn", origin="SYNTHETIC")
    q = parsed.quotes
    span_h1 = (q[-1].provider_time_ms - q[0].provider_time_ms) // 3_600_000
    assert span_h1 > synthetic.WARMUP_H1_BARS + 24  # warm-up plus a decision window
    assert all(x.ask > x.bid for x in q)
    assert all(a.received_time_ms <= b.received_time_ms for a, b in zip(q, q[1:], strict=False))


def test_cli_refuses_overwrite(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "s.csv"
    assert synthetic.main(["--out", str(out), "--days", "1"]) == 0
    before = out.read_bytes()
    assert synthetic.main(["--out", str(out), "--days", "1"]) != 0
    assert out.read_bytes() == before
    capsys.readouterr()
