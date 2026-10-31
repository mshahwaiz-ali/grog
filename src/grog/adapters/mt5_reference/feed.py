"""Read-only MT5 reference feed: normalizer and durable file reader (docs/09 §5.1).

``ReferenceNormalizer`` turns transport records into :class:`NormalizedQuote` (UTC conversion
from the exporter-reported server offset, explicit side carry-forward, content+occurrence
dedup that keeps distinct same-millisecond ticks, causal ordering, LIVE vs BACKFILL tagging).
``ReferenceReader`` reads rotated append-only files, consumes complete lines only and persists
an atomic JSON cursor. Neither writes to the journal or talks to any broker/network.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from grog.adapters.mt5_reference.format import (
    FILE_NAME,
    CatchUpBegin,
    CatchUpEnd,
    EndOfFile,
    GapRecord,
    HeartbeatRecord,
    MetaRecord,
    Record,
    RecordError,
    TickRecord,
    parse_line,
)
from grog.domain.clock import Clock
from grog.domain.enums import SourceOrigin
from grog.domain.models import CANONICAL_SYMBOL, NormalizedQuote

RECENT_KEYS = 20_000  # bounded dedup memory (re-delivery overlap is milliseconds to minutes)
CURSOR_VERSION = 1
LIVE, BACKFILL, FIXTURE = "LIVE", "BACKFILL", "FIXTURE"
FUTURE_TIME, OFFSET_ASSUMED = "FUTURE_TIME", "OFFSET_ASSUMED"


@dataclass(frozen=True, slots=True)
class Heartbeat:
    received_ms: int  # Grog clock when the line was read
    server_time_msc: int
    utc_ms: int  # server_time_msc converted with the reported offset
    connected: bool
    session: str


@dataclass(frozen=True, slots=True)
class FeedEvent:
    """One consumed transport line, in file order."""

    kind: str  # QUOTE | REJECT | HEARTBEAT | META | CATCHUP_BEGIN | CATCHUP_END | EOF
    file: str
    seq: int
    quote: NormalizedQuote | None = None
    live: bool = False
    code: str | None = None
    heartbeat: Heartbeat | None = None


@dataclass
class NormalizerState:
    source_id: str
    producer: str | None = None
    fixture: bool = False
    server: str | None = None
    raw_symbol: str | None = None
    digits: int | None = None
    offset_s: int | None = None
    last_bid: Decimal | None = None
    last_ask: Decimal | None = None
    last_provider_ms: int | None = None
    last_received_ms: int = 0
    ingest_order: int = 0
    in_catchup: bool = False
    seg_ms: int | None = None
    seg_counts: dict[str, int] = field(default_factory=dict)
    recent: deque[str] = field(default_factory=lambda: deque(maxlen=RECENT_KEYS))
    counters: dict[str, int] = field(default_factory=dict)
    heartbeat: Heartbeat | None = None
    records: int = 0
    # Latched integrity faults: code -> [file, line seq] of the first occurrence (docs/09 §5.1).
    faults: dict[str, list] = field(default_factory=dict)
    # Per-file transport state (reset when the reader enters a new file).
    file_meta_ok: bool = False
    file_closed: bool = False
    file_head: str | None = None  # fingerprint of the file's first line
    file_flags: list[str] = field(default_factory=list)
    catchup_ticks: int = 0

    def to_json(self) -> dict:
        hb = self.heartbeat
        return {
            "source_id": self.source_id,
            "producer": self.producer,
            "fixture": self.fixture,
            "server": self.server,
            "raw_symbol": self.raw_symbol,
            "digits": self.digits,
            "offset_s": self.offset_s,
            "last_bid": None if self.last_bid is None else str(self.last_bid),
            "last_ask": None if self.last_ask is None else str(self.last_ask),
            "last_provider_ms": self.last_provider_ms,
            "last_received_ms": self.last_received_ms,
            "ingest_order": self.ingest_order,
            "in_catchup": self.in_catchup,
            "seg_ms": self.seg_ms,
            "seg_counts": dict(self.seg_counts),
            "recent": list(self.recent),
            "counters": dict(self.counters),
            "heartbeat": None
            if hb is None
            else [hb.received_ms, hb.server_time_msc, hb.utc_ms, hb.connected, hb.session],
            "records": self.records,
            "faults": {k: list(v) for k, v in self.faults.items()},
            "file_meta_ok": self.file_meta_ok,
            "file_closed": self.file_closed,
            "file_head": self.file_head,
            "file_flags": list(self.file_flags),
            "catchup_ticks": self.catchup_ticks,
        }

    @classmethod
    def from_json(cls, d: dict) -> NormalizerState:
        st = cls(d["source_id"])
        for k in (
            "producer",
            "fixture",
            "server",
            "raw_symbol",
            "digits",
            "offset_s",
            "last_provider_ms",
            "last_received_ms",
            "ingest_order",
            "in_catchup",
            "seg_ms",
            "records",
        ):
            setattr(st, k, d[k])
        st.last_bid = None if d["last_bid"] is None else Decimal(d["last_bid"])
        st.last_ask = None if d["last_ask"] is None else Decimal(d["last_ask"])
        st.seg_counts = dict(d["seg_counts"])
        st.recent = deque(d["recent"], maxlen=RECENT_KEYS)
        st.counters = dict(d["counters"])
        st.faults = {k: list(v) for k, v in d.get("faults", {}).items()}
        st.file_meta_ok = bool(d.get("file_meta_ok", st.offset_s is not None))
        st.file_closed = bool(d.get("file_closed", False))
        st.file_head = d.get("file_head")
        st.file_flags = list(d.get("file_flags", []))
        st.catchup_ticks = int(d.get("catchup_ticks", 0))
        hb = d["heartbeat"]
        st.heartbeat = None if hb is None else Heartbeat(hb[0], hb[1], hb[2], bool(hb[3]), hb[4])
        return st


class ReferenceNormalizer:
    """Stateful record -> quote conversion for one source (pure; time is passed in)."""

    def __init__(
        self,
        source_id: str,
        max_quote_age_ms: int | None,
        state: NormalizerState | None = None,
        max_future_skew_ms: int | None = None,
    ) -> None:
        self.state = state or NormalizerState(source_id)
        if self.state.source_id != source_id:
            raise ValueError("cursor belongs to another source")
        self.max_quote_age_ms = max_quote_age_ms
        self.max_future_skew_ms = max_future_skew_ms  # OPEN policy: unset by default
        self._recent_set = set(self.state.recent)

    def count(self, code: str) -> None:
        self.state.counters[code] = self.state.counters.get(code, 0) + 1

    def fault(self, code: str, file: str | None, seq: int) -> None:
        """Count and latch an integrity fault (never cleared automatically)."""
        self.count(code)
        self.state.faults.setdefault(code, [file, seq])

    def begin_file(self) -> None:
        """Metadata is per file: a new file is unusable until its own valid META."""
        st = self.state
        st.file_meta_ok, st.file_closed, st.file_head, st.file_flags = False, False, None, []

    def file_fault(self, code: str, file: str, seq: int) -> None:
        """Latch a per-file condition once (repeated polls do not re-count it)."""
        if code not in self.state.file_flags:
            self.state.file_flags.append(code)
            self.fault(code, file, seq)

    def _offset(self, offset_s: int, file: str, seq: int) -> None:
        st = self.state
        if st.offset_s is not None and offset_s != st.offset_s:
            self.fault("OFFSET_CHANGED", file, seq)  # history across two offsets: no READY
        st.offset_s = offset_s

    def apply(self, record: Record, received_ms: int, file: str) -> FeedEvent:
        st = self.state
        st.records += 1
        if isinstance(record, MetaRecord):
            st.file_meta_ok = False
            if record.seq != 1:
                return self._fault_reject("META_INVALID", file, record.seq)
            if record.source_id != st.source_id:
                return self._fault_reject("SOURCE_MISMATCH", file, record.seq)
            identity = (record.producer, record.server, record.raw_symbol, record.digits)
            if st.producer is not None and identity != (
                st.producer,
                st.server,
                st.raw_symbol,
                st.digits,
            ):  # a source switch needs its own source_id (MD-14)
                return self._fault_reject("META_CHANGED", file, record.seq)
            st.file_meta_ok = True
            st.producer, st.server, st.raw_symbol = (
                record.producer,
                record.server,
                record.raw_symbol,
            )
            st.digits = record.digits
            self._offset(record.server_offset_s, file, record.seq)
            st.fixture = st.fixture or record.producer == "FIXTURE"
            return FeedEvent("META", file, record.seq)
        if isinstance(record, EndOfFile):
            st.file_closed = True
            return FeedEvent("EOF", file, record.seq)
        if not st.file_meta_ok:  # never inherit an earlier file's metadata
            return self._reject("NO_META", file, record.seq)
        if isinstance(record, HeartbeatRecord):
            self._offset(record.server_offset_s, file, record.seq)
            hb = Heartbeat(
                max(received_ms, st.last_received_ms),
                record.server_time_msc,
                record.server_time_msc - record.server_offset_s * 1000,
                record.connected,
                record.session,
            )
            st.heartbeat = hb
            return FeedEvent("HEARTBEAT", file, record.seq, heartbeat=hb)
        if isinstance(record, CatchUpBegin):
            if st.in_catchup:
                self.fault("CATCHUP_SEQUENCE", file, record.seq)
            st.in_catchup, st.seg_ms, st.seg_counts, st.catchup_ticks = True, None, {}, 0
            return FeedEvent("CATCHUP_BEGIN", file, record.seq)
        if isinstance(record, CatchUpEnd):
            if not st.in_catchup:
                self.fault("CATCHUP_SEQUENCE", file, record.seq)
            elif record.count != st.catchup_ticks:  # failed/partial window or lost lines
                self.fault("CATCHUP_COUNT_MISMATCH", file, record.seq)
            st.in_catchup, st.seg_ms, st.seg_counts, st.catchup_ticks = False, None, {}, 0
            return FeedEvent("CATCHUP_END", file, record.seq)
        if isinstance(record, GapRecord):
            self.fault("SOURCE_GAP", file, record.seq)
            return FeedEvent("GAP", file, record.seq, code="SOURCE_GAP")
        if st.in_catchup:
            st.catchup_ticks += 1
        return self._tick(record, received_ms, file)

    def _reject(self, code: str, file: str, seq: int) -> FeedEvent:
        self.count(code)
        return FeedEvent("REJECT", file, seq, code=code)

    def _fault_reject(self, code: str, file: str, seq: int) -> FeedEvent:
        self.fault(code, file, seq)
        return FeedEvent("REJECT", file, seq, code=code)

    def _tick(self, t: TickRecord, received_ms: int, file: str) -> FeedEvent:
        st = self.state
        if st.offset_s is None or st.raw_symbol is None:  # pragma: no cover - file_meta_ok
            return self._reject("NO_META", file, t.seq)
        if not (t.bid_changed or t.ask_changed):
            return self._reject("NON_QUOTE", file, t.seq)
        if (t.bid_changed and t.bid is None) or (t.ask_changed and t.ask is None):
            return self._fault_reject("INVALID_PRICE", file, t.seq)
        flags = {"BID_CHANGED"} if t.bid_changed else set()
        if t.ask_changed:
            flags.add("ASK_CHANGED")
        bid, ask = t.bid, t.ask
        if bid is None:
            bid = st.last_bid
            flags.add("BID_CARRIED")
        if ask is None:
            ask = st.last_ask
            flags.add("ASK_CARRIED")
        if bid is None or ask is None:
            return self._reject("SIDE_UNKNOWN", file, t.seq)
        if ask < bid:
            return self._reject("CROSSED", file, t.seq)

        content = f"{t.time_msc}:{bid}:{ask}:{t.flags}"
        if st.seg_ms != t.time_msc:
            st.seg_ms, st.seg_counts = t.time_msc, {}
        n = st.seg_counts.get(content, 0)
        st.seg_counts[content] = n + 1
        key = f"{st.source_id}:{content}:{n}"
        if key in self._recent_set:
            return self._reject("DUPLICATE", file, t.seq)
        provider = t.time_msc - st.offset_s * 1000
        if provider < 0:
            return self._fault_reject("BAD_TIME", file, t.seq)
        if st.last_provider_ms is not None and provider < st.last_provider_ms:
            if t.mode == "L":  # the live stream never goes back: a transport fault
                return self._fault_reject("OUT_OF_ORDER", file, t.seq)
            return self._reject("OUT_OF_ORDER", file, t.seq)  # re-delivered history

        received = max(received_ms, st.last_received_ms)
        ahead = provider - received
        if ahead > 0:
            flags.add(FUTURE_TIME)  # provider clock ahead of receipt: never LIVE
            if self.max_future_skew_ms is not None and ahead > self.max_future_skew_ms:
                self.fault("FUTURE_TIME", file, t.seq)
                return FeedEvent("REJECT", file, t.seq, code="FUTURE_TIME")
        if t.mode == "B":
            flags.add(OFFSET_ASSUMED)  # history converted with an offset observed later
        live = (
            ahead <= 0
            and t.mode == "L"
            and not st.in_catchup
            and self.max_quote_age_ms is not None
            and received - provider <= self.max_quote_age_ms
        )
        flags.add(LIVE if live else BACKFILL)
        if st.fixture:
            flags.add(FIXTURE)
        st.ingest_order += 1
        quote = NormalizedQuote(
            source_id=st.source_id,
            canonical_symbol=CANONICAL_SYMBOL,
            raw_symbol=st.raw_symbol,
            provider_time_ms=provider,
            received_time_ms=received,
            ingest_order=st.ingest_order,
            bid=bid,
            ask=ask,
            source_origin=SourceOrigin.REFERENCE_LIVE,
            source_event_key=key,
            flags=frozenset(flags),
        )
        st.last_bid, st.last_ask = bid, ask
        st.last_provider_ms, st.last_received_ms = provider, received
        if len(st.recent) == st.recent.maxlen:
            self._recent_set.discard(st.recent[0])
        st.recent.append(key)
        self._recent_set.add(key)
        self.count("ACCEPTED_LIVE" if live else "ACCEPTED_BACKFILL")
        return FeedEvent("QUOTE", file, t.seq, quote=quote, live=live)


@dataclass(frozen=True, slots=True)
class CursorPosition:
    file: str | None
    offset: int
    next_seq: int


class ReferenceReader:
    """Durable reader of ``<source_id>__<session>__<part>.grogref`` files (complete lines only)."""

    def __init__(
        self,
        directory: Path,
        source_id: str,
        clock: Clock,
        max_quote_age_ms: int | None,
        cursor_path: Path | None = None,
        max_future_skew_ms: int | None = None,
    ) -> None:
        self.directory = Path(directory)
        self.source_id = source_id
        self.clock = clock
        self.cursor_path = cursor_path
        state = None
        self.position = CursorPosition(None, 0, 1)
        if cursor_path is not None and cursor_path.exists():
            data = json.loads(cursor_path.read_text(encoding="utf-8"))
            if data.get("version") != CURSOR_VERSION:
                raise ValueError(f"unsupported cursor version in {cursor_path}")
            p = data["position"]
            self.position = CursorPosition(p["file"], p["offset"], p["next_seq"])
            state = NormalizerState.from_json(data["normalizer"])
        self.normalizer = ReferenceNormalizer(
            source_id, max_quote_age_ms, state, max_future_skew_ms
        )

    @property
    def state(self) -> NormalizerState:
        return self.normalizer.state

    def files(self) -> list[str]:
        if not self.directory.is_dir():
            return []
        names = []
        for p in self.directory.iterdir():
            m = FILE_NAME.fullmatch(p.name)
            if m and m.group("source") == self.source_id and p.is_file():
                names.append(p.name)
        return sorted(names)

    def poll(self, stop_at: CursorPosition | None = None) -> list[FeedEvent]:
        """Consume every complete new line (optionally only up to ``stop_at``)."""
        events: list[FeedEvent] = []
        files = self.files()
        pos = self.position
        norm = self.normalizer
        if pos.file is None:
            if not files:
                return events
            pos = CursorPosition(files[0], 0, 1)
            norm.begin_file()
        while True:
            if stop_at is not None and (pos.file, pos.offset) >= (stop_at.file, stop_at.offset):
                break
            path = self.directory / pos.file
            data = b""
            if not path.exists():
                if not norm.state.file_closed:  # unread tail unknowable: never silent
                    norm.file_fault("CURSOR_FILE_MISSING", pos.file, pos.next_seq)
            else:
                with path.open("rb") as fh:
                    head = fh.readline()
                    if pos.offset > 0 and norm.state.file_head is not None:
                        if _fingerprint(head) != norm.state.file_head:
                            norm.file_fault("FILE_REPLACED", pos.file, pos.next_seq)
                    size = os.fstat(fh.fileno()).st_size
                    if size < pos.offset:
                        norm.file_fault("FILE_TRUNCATED", pos.file, pos.next_seq)
                    else:
                        fh.seek(pos.offset)
                        data = fh.read()
            end = data.rfind(b"\n")
            if stop_at is not None and stop_at.file == pos.file:
                end = min(end, stop_at.offset - pos.offset - 1)
            consumed = data[: end + 1] if end >= 0 else b""
            offset = pos.offset
            seq = pos.next_seq
            for raw in consumed.split(b"\n")[:-1]:
                if offset == 0:
                    norm.state.file_head = _fingerprint(raw + b"\n")
                offset += len(raw) + 1
                ev = self._line(raw, pos.file, seq)
                if ev.seq != seq:
                    norm.fault("TRANSPORT_SEQ_GAP", pos.file, ev.seq)
                seq = ev.seq + 1
                events.append(ev)
            pos = CursorPosition(pos.file, offset, seq)
            later = [f for f in files if f > pos.file]
            if not later or (stop_at is not None and stop_at.file == pos.file):
                break
            if len(data) > len(consumed):
                norm.fault("PARTIAL_LINE_DISCARDED", pos.file, seq)
            if (
                not norm.state.file_closed
                and offset > 0
                and "CURSOR_FILE_MISSING" not in (norm.state.file_flags)
            ):
                norm.fault("FILE_ENDED_WITHOUT_Z", pos.file, seq)
            pos = CursorPosition(later[0], 0, 1)
            norm.begin_file()
        self.position = pos
        return events

    def _line(self, raw: bytes, file: str, seq: int) -> FeedEvent:
        received = self.clock.now_ms()
        try:
            text = raw.decode("utf-8")
            record = parse_line(text, self.normalizer.state.digits)
        except (UnicodeDecodeError, RecordError) as exc:
            code = exc.code if isinstance(exc, RecordError) else "BAD_ENCODING"
            self.normalizer.fault(code, file, seq)  # transport corruption is never healthy
            if seq == 1:
                self.normalizer.fault("META_INVALID", file, seq)
            return FeedEvent("REJECT", file, seq, code=code)
        if seq == 1 and not isinstance(record, MetaRecord):
            self.normalizer.count("MISSING_META")
            self.normalizer.fault("META_INVALID", file, seq)
        return self.normalizer.apply(record, received, file)

    def commit(self) -> None:
        """Atomically persist position + normalizer state (temp file, fsync, rename)."""
        if self.cursor_path is None:
            return
        self.cursor_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": CURSOR_VERSION,
            "position": {
                "file": self.position.file,
                "offset": self.position.offset,
                "next_seq": self.position.next_seq,
            },
            "normalizer": self.normalizer.state.to_json(),
        }
        tmp = self.cursor_path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.cursor_path)


def _fingerprint(first_line: bytes) -> str:
    return hashlib.sha256(first_line).hexdigest()[:16]


def cursor_path_for(state_dir: Path, source_id: str) -> Path:
    return Path(state_dir) / "reference" / f"{source_id}.cursor.json"


__all__ = [
    "BACKFILL",
    "FIXTURE",
    "FUTURE_TIME",
    "OFFSET_ASSUMED",
    "LIVE",
    "CursorPosition",
    "FeedEvent",
    "Heartbeat",
    "NormalizerState",
    "ReferenceNormalizer",
    "ReferenceReader",
    "cursor_path_for",
]
