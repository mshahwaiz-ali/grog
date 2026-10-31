"""Reproducible R0 workstation screenshots (SVG via Textual export; PNG via headless
Chrome when available). Offline, SYNTHETIC replay, temporary journal; nothing is sent
anywhere. Usage:

    uv run python scripts/r0_screenshots.py --out /workspace/grog-screens/r0

The OPEN feed thresholds below are DEMO/TEST-ONLY declarations so the synthetic replay can
issue SIMULATED READY signals; they are not broker values or approved live settings.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import shutil
import subprocess
import tempfile
from decimal import Decimal
from pathlib import Path

# Real colours in the exported SVG even when the calling shell sets NO_COLOR / TERM=dumb.
for _var in ("NO_COLOR", "FORCE_COLOR"):
    os.environ.pop(_var, None)
os.environ["TERM"] = "xterm-256color"
os.environ["COLORTERM"] = "truecolor"

from grog.domain.clock import FixedClock  # noqa: E402
from grog.domain.enums import SignalEventKind  # noqa: E402
from grog.domain.models import DataHealthPolicy  # noqa: E402
from grog.journal.positions import EntryRequest, PlanRef, PositionJournal, new_action_id  # noqa: E402
from grog.journal.store import STATE_DB_FILENAME, Store  # noqa: E402
from grog.market_data.import_csv import parse_canonical_csv  # noqa: E402
from grog.replay import synthetic  # noqa: E402
from grog.replay.session import ReplaySession, SourceInfo  # noqa: E402
from grog.signals.engine import SignalPolicy  # noqa: E402
from grog.ui.app import GrogApp  # noqa: E402

DEMO_ONLY_POLICY = SignalPolicy(  # DEMO/TEST-ONLY thresholds (docs/11 keeps them OPEN)
    health=DataHealthPolicy(max_quote_age_ms=60_000, max_first_postclose_delay_ms=30_000),
    price_step=Decimal("0.01"),
)
INFO = SourceInfo(
    source_id="syn",
    origin="SYNTHETIC",
    raw_symbol="XAUUSD",
    batch_sha256s=("0" * 64,),
    batch_paths=("batches/syn.csv",),
    config_hash="demo-fixture-only",
    config_version=1,
    state_schema_version=4,
)
SIZES = {"wide": (120, 34), "normal": (80, 24), "small": (70, 18)}


def build_session() -> ReplaySession:
    quotes = parse_canonical_csv(
        synthetic.generate_csv(days=20), source_id="syn", origin="SYNTHETIC"
    ).quotes
    return ReplaySession(quotes, INFO, DEMO_ONLY_POLICY)


def step_until(s: ReplaySession, kind: SignalEventKind, nth: int = 1) -> str:
    events = s.pipeline.signals.events
    seen, start = 0, len(events)
    while s.step():
        for e in events[start:]:
            if e.kind is kind:
                seen += 1
                if seen == nth:
                    return e.signal_id or e.candidate_id
        start = len(events)
    raise RuntimeError(f"{kind} #{nth} not reached")


def record_demo_entry(journal: PositionJournal, s: ReplaySession, sid: str) -> None:
    snap = s.snapshot()
    r = next(v.record for v in snap.signals if v.record.signal_id == sid)
    q = snap.quote
    journal.record_entry(
        EntryRequest(
            action_id=new_action_id(),
            side=r.side,
            price=q.ask if r.side.value == "BUY" else q.bid,
            qty=Decimal("0.10"),  # demo fixture quantity, not a lot recommendation
            fill_ms=q.received_time_ms,
            source_id="syn",
            plan=PlanRef.from_record(r),
            signal_ready=True,
            stop=r.sl0,
        )
    )


async def shoot(app: GrogApp, size, keys, path: Path) -> None:
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        for k in keys:
            await pilot.press(k)
            await pilot.pause()
        app.save_screenshot(filename=path.name, path=str(path.parent))


def to_png(svg: Path) -> Path | None:
    chrome = shutil.which("google-chrome") or shutil.which("chromium")
    if chrome is None:
        return None
    png = svg.with_suffix(".png")
    text = svg.read_text()
    m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', text)
    w, h = (int(float(m.group(1))) + 1, int(float(m.group(2))) + 1) if m else (1600, 900)
    html = svg.with_suffix(".html")
    html.write_text(
        f"<html><body style='margin:0;background:#0B111A'>{text}</body></html>", "utf-8"
    )
    subprocess.run(
        [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--hide-scrollbars",
            f"--window-size={w},{h}",
            f"--screenshot={png}",
            html.as_uri(),
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    html.unlink()
    return png


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="grog-shots-"))

    def journal(name: str) -> PositionJournal:
        store = Store.open(tmp / name / STATE_DB_FILENAME, FixedClock(1_793_450_000_000))
        return PositionJournal(store)

    def ready_app() -> GrogApp:
        """READY issued, nothing recorded yet."""
        s = build_session()
        step_until(s, SignalEventKind.READY_ISSUED)
        return GrogApp(s, journal("j" + new_action_id()[:8]), autoplay_timer=False)

    def restarted_app() -> GrogApp:
        """READY entered locally, replay moved on, then a restart => RECONCILIATION_REQUIRED."""
        s = build_session()
        sid = step_until(s, SignalEventKind.READY_ISSUED)
        j = journal("j" + new_action_id()[:8])
        record_demo_entry(j, s, sid)
        for _ in range(120):
            s.step()
        j.restore_on_startup()
        return GrogApp(s, j, autoplay_timer=False)

    wide = SIZES["wide"]
    shots = []
    for tag, size in SIZES.items():
        shots += [
            (f"live-ready-{tag}", ready_app, size, []),
            (f"signals-ready-{tag}", ready_app, size, ["2"]),
            (f"modal-record-entry-{tag}", ready_app, size, ["2", "e"]),
            (f"positions-reconcile-{tag}", restarted_app, size, ["3"]),
            (f"live-position-{tag}", restarted_app, size, []),
        ]
    shots += [
        ("modal-signal-detail-wide", ready_app, wide, ["2", "enter"]),
        ("modal-skip-wide", ready_app, wide, ["2", "s"]),
        ("modal-position-detail-wide", restarted_app, wide, ["3", "enter"]),
        ("modal-partial-wide", restarted_app, wide, ["3", "p"]),
        ("modal-modify-wide", restarted_app, wide, ["3", "m"]),
        ("modal-close-wide", restarted_app, wide, ["3", "x"]),
        ("modal-unlinked-wide", restarted_app, wide, ["3", "n"]),
        ("journal-wide", restarted_app, wide, ["4"]),
        ("diagnostics-wide", restarted_app, wide, ["5"]),
        ("diagnostics-small", restarted_app, SIZES["small"], ["5"]),
        ("help-wide", restarted_app, wide, ["question_mark"]),
    ]

    for name, factory, size, keys in shots:
        if args.only and args.only not in name:
            continue
        svg = out / f"{name}-{size[0]}x{size[1]}.svg"
        asyncio.run(shoot(factory(), size, keys, svg))
        png = to_png(svg)
        print(png or svg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
