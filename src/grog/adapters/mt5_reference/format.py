"""Transport records of the read-only MT5 reference exporter (docs/09 §5.1, ``GROG-MT5-REF/1``).

One text line -> one typed record, or :class:`RecordError` with a stable code. Pure: no I/O,
no clock. Prices are parsed from text into ``Decimal`` (never via float).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from grog.domain.ids import is_valid_source_id

FORMAT = "GROG-MT5-REF/1"
PRODUCERS = ("MQL5_EXPORTER", "FIXTURE")
SESSIONS = ("OPEN", "CLOSED", "UNKNOWN")
TICK_FLAG_BID = 2  # MQL5 TICK_FLAG_BID
TICK_FLAG_ASK = 4  # MQL5 TICK_FLAG_ASK
MAX_DIGITS = 8
_INT = re.compile(r"-?[0-9]+")
_PRICE = re.compile(r"[0-9]+(\.[0-9]+)?")
FILE_NAME = re.compile(
    r"(?P<source>[A-Za-z0-9_.-]+?)__(?P<session>[0-9]{8}T[0-9]{6}Z)__(?P<part>[0-9]{6})\.grogref"
)


class RecordError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        super().__init__(f"{code}: {detail}" if detail else code)


@dataclass(frozen=True, slots=True)
class MetaRecord:
    seq: int
    producer: str
    source_id: str
    server: str
    raw_symbol: str
    digits: int
    server_offset_s: int
    exporter_version: str


@dataclass(frozen=True, slots=True)
class TickRecord:
    seq: int
    mode: str  # "L" live poll | "B" catch-up (CopyTicksRange)
    time_msc: int  # trade-server clock, ms, exactly as MT5 reports
    bid: Decimal | None  # None = empty/0 (unchanged side, to carry forward)
    ask: Decimal | None
    flags: int

    @property
    def bid_changed(self) -> bool:
        return bool(self.flags & TICK_FLAG_BID)

    @property
    def ask_changed(self) -> bool:
        return bool(self.flags & TICK_FLAG_ASK)


@dataclass(frozen=True, slots=True)
class HeartbeatRecord:
    seq: int
    server_time_msc: int
    connected: bool
    session: str
    server_offset_s: int


@dataclass(frozen=True, slots=True)
class CatchUpBegin:
    seq: int
    from_msc: int


@dataclass(frozen=True, slots=True)
class CatchUpEnd:
    seq: int
    to_msc: int
    count: int


@dataclass(frozen=True, slots=True)
class GapRecord:
    """An irrecoverable source gap the exporter could not read after its retries."""

    seq: int
    from_msc: int
    to_msc: int
    error: int


@dataclass(frozen=True, slots=True)
class EndOfFile:
    seq: int
    next_file: str | None


Record = (
    MetaRecord | TickRecord | HeartbeatRecord | CatchUpBegin | CatchUpEnd | GapRecord | EndOfFile
)

_ARITY = {"M": 10, "T": 7, "H": 6, "B": 3, "E": 4, "G": 5, "Z": 3}


def _int(text: str, name: str, minimum: int | None = None) -> int:
    if not _INT.fullmatch(text):
        raise RecordError("BAD_INT", f"{name}={text!r}")
    value = int(text)
    if minimum is not None and value < minimum:
        raise RecordError("BAD_INT", f"{name}={value} < {minimum}")
    return value


def parse_price(text: str, digits: int | None) -> Decimal | None:
    """``""`` or a zero value means "side not supplied" (MT5 leaves unchanged sides 0)."""
    if text == "":
        return None
    if not _PRICE.fullmatch(text):
        raise RecordError("BAD_PRICE", repr(text))
    try:
        value = Decimal(text)
    except InvalidOperation as exc:  # pragma: no cover - regex already guards
        raise RecordError("BAD_PRICE", repr(text)) from exc
    if value == 0:
        return None
    if digits is not None and "." in text and len(text.split(".")[1]) > digits:
        raise RecordError("PRICE_PRECISION", f"{text} has more than {digits} decimals")
    return value


def parse_line(line: str, digits: int | None = None) -> Record:
    """Parse one complete line (without its ``\\n``). ``digits`` comes from the file's META."""
    if line.endswith("\r"):
        raise RecordError("BAD_LINE_END", "CRLF not allowed")
    fields = line.split(",")
    kind = fields[0]
    if kind not in _ARITY:
        raise RecordError("UNKNOWN_RECORD", repr(kind))
    if len(fields) != _ARITY[kind]:
        raise RecordError("BAD_ARITY", f"{kind} has {len(fields)} fields, expected {_ARITY[kind]}")
    seq = _int(fields[1], "seq", 1)
    if kind == "M":
        _, _, fmt, producer, source_id, server, raw_symbol, dg, off, version = fields
        if fmt != FORMAT:
            raise RecordError("BAD_FORMAT", repr(fmt))
        if producer not in PRODUCERS:
            raise RecordError("BAD_PRODUCER", repr(producer))
        if not is_valid_source_id(source_id):
            raise RecordError("BAD_SOURCE_ID", repr(source_id))
        if not server or not raw_symbol or not version:
            raise RecordError("BAD_META", "server/symbol/version required")
        d = _int(dg, "digits", 0)
        if d > MAX_DIGITS:
            raise RecordError("BAD_META", f"digits={d}")
        return MetaRecord(
            seq, producer, source_id, server, raw_symbol, d, _int(off, "offset"), version
        )
    if kind == "T":
        _, _, mode, tmsc, bid, ask, flags = fields
        if mode not in ("L", "B"):
            raise RecordError("BAD_MODE", repr(mode))
        return TickRecord(
            seq,
            mode,
            _int(tmsc, "time_msc", 1),
            parse_price(bid, digits),
            parse_price(ask, digits),
            _int(flags, "flags", 0),
        )
    if kind == "H":
        _, _, smsc, conn, session, off = fields
        if conn not in ("0", "1"):
            raise RecordError("BAD_HEARTBEAT", f"connected={conn!r}")
        if session not in SESSIONS:
            raise RecordError("BAD_HEARTBEAT", f"session={session!r}")
        return HeartbeatRecord(
            seq, _int(smsc, "server_time_msc", 0), conn == "1", session, _int(off, "offset")
        )
    if kind == "B":
        return CatchUpBegin(seq, _int(fields[2], "from_msc", 0))
    if kind == "E":
        return CatchUpEnd(seq, _int(fields[2], "to_msc", 0), _int(fields[3], "count", 0))
    if kind == "G":
        return GapRecord(
            seq,
            _int(fields[2], "from_msc", 0),
            _int(fields[3], "to_msc", 0),
            _int(fields[4], "error"),
        )
    nxt = fields[2]
    return EndOfFile(seq, None if nxt == "-" else nxt)


def format_tick(seq: int, mode: str, time_msc: int, bid: str, ask: str, flags: int) -> str:
    """Inverse of :func:`parse_line` for ``T`` records (fixtures and tests)."""
    return f"T,{seq},{mode},{time_msc},{bid},{ask},{flags}"


__all__ = [
    "FILE_NAME",
    "FORMAT",
    "CatchUpBegin",
    "CatchUpEnd",
    "EndOfFile",
    "GapRecord",
    "HeartbeatRecord",
    "MetaRecord",
    "Record",
    "RecordError",
    "TICK_FLAG_ASK",
    "TICK_FLAG_BID",
    "TickRecord",
    "format_tick",
    "parse_line",
    "parse_price",
]
