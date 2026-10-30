"""Stable deterministic identities and canonical serialization."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

_SOURCE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")


def is_valid_source_id(source_id: object) -> bool:
    """Source IDs are also local directory names, so only a safe character set is allowed."""
    return isinstance(source_id, str) and _SOURCE_ID_RE.fullmatch(source_id) is not None


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_event_key(file_sha256: str, row_ordinal: int) -> str:
    """``sha256(file_bytes) + "#" + row_ordinal`` (docs/09 Section 6)."""
    return f"{file_sha256}#{row_ordinal}"


def batch_id(source_id: str, file_sha256: str) -> str:
    """Deterministic batch identity: the same bytes for the same source always map to one batch."""
    return sha256_hex(f"{source_id}\x00{file_sha256}".encode())


def canonical_json(value: Any) -> str:
    """Versionable JSON with sorted keys and no insignificant whitespace."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
