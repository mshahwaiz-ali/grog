"""D05 source selection for the desktop launcher (pure, no Qt).

The launcher opens the desktop only on a source the operator chose on purpose:
explicit command-line arguments, or a selection the operator saved from the chooser
(``$XDG_CONFIG_HOME/grog/desktop-source.toml``). Nothing here imports data, creates or
migrates a state database, copies a ``/tmp`` database anywhere, opens a network
connection or starts MT5. State directories are inspected read-only.
"""

from __future__ import annotations

import os
import shlex
import tempfile
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from grog.domain.clock import SystemClock
from grog.settings import CONFIG_FILENAME, STATE_DB_FILENAME, _env_dir, resolve_state_dir

SELECTION_FILENAME = "desktop-source.toml"
SELECTION_KEYS = ("source_id", "state_dir", "config", "from_ts")


@dataclass(frozen=True, slots=True)
class Selection:
    source_id: str
    state_dir: str
    config: str | None = None
    from_ts: str | None = None


@dataclass(frozen=True, slots=True)
class SourceInfo:
    source_id: str
    origin: str  # SYNTHETIC / HISTORICAL / BACKFILL (as recorded at import)
    symbol: str
    batches: int
    quotes: int
    first_utc: str | None
    last_utc: str | None

    @property
    def caution(self) -> str:
        if self.origin == "SYNTHETIC":
            return "SYNTHETIC fixture prices — never current market data"
        return f"{self.origin} import — offline replay, SIMULATED fills only"


@dataclass(frozen=True, slots=True)
class StateInfo:
    state_dir: str
    database: str
    sources: tuple[SourceInfo, ...]
    problem: str | None  # None = readable catalog
    temporary: bool  # under the system temp directory: not durable

    @property
    def ok(self) -> bool:
        return self.problem is None


def selection_path(env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    return _env_dir(env, "XDG_CONFIG_HOME", (".config",)) / "grog" / SELECTION_FILENAME


def default_config(env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    return _env_dir(env, "XDG_CONFIG_HOME", (".config",)) / "grog" / CONFIG_FILENAME


def is_temporary(path: str | os.PathLike[str]) -> bool:
    p = Path(path).expanduser().resolve()
    roots = {Path(tempfile.gettempdir()).resolve(), Path("/tmp").resolve()}  # noqa: S108
    return any(p == r or r in p.parents for r in roots)


def read_selection(env: Mapping[str, str] | None = None) -> tuple[Selection | None, str | None]:
    """The saved selection, or ``(None, reason)``; a broken file is reported, not repaired."""
    path = selection_path(env)
    if not path.is_file():
        return None, f"No saved desktop source ({path})"
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        return None, f"Saved desktop source {path} is unreadable: {exc}"
    unknown = sorted(set(data) - set(SELECTION_KEYS))
    if unknown:
        return None, f"Saved desktop source {path} has unknown keys: {', '.join(unknown)}"
    values = {k: data.get(k) for k in SELECTION_KEYS}
    if not all(isinstance(v, str) and v for v in (values["source_id"], values["state_dir"])):
        return None, f"Saved desktop source {path} needs source_id and state_dir strings"
    for key in ("config", "from_ts"):
        if values[key] is not None and not isinstance(values[key], str):
            return None, f"Saved desktop source {path}: {key} must be a string"
    return Selection(**values), None


def _toml_str(value: str) -> str:
    """TOML basic string: backslash, quote and every control character escaped."""
    out = []
    for ch in value:
        if ch in ('"', "\\"):
            out.append("\\" + ch)
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append(f"\\u{ord(ch):04X}")
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def write_selection(sel: Selection, env: Mapping[str, str] | None = None) -> Path:
    """Explicit operator action only: atomically writes the small selection file (the
    config directory may be created; the state directory never is)."""
    path = selection_path(env)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Gold desktop launcher source, saved from the source chooser (no data copy)"]
    for key in SELECTION_KEYS:
        value = getattr(sel, key)
        if value is not None:
            lines.append(f"{key} = {_toml_str(value)}")
    fd, tmp = tempfile.mkstemp(prefix=".desktop-source.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path


def _utc(ms: int | None) -> str | None:
    if ms is None:
        return None
    from grog.ui.format import iso_utc

    return iso_utc(ms)


def inspect_state(state_dir: str | None, env: Mapping[str, str] | None = None) -> StateInfo:
    """Read-only catalog of a state directory: never created, migrated or written."""
    from grog.journal.store import Store

    env = os.environ if env is None else env
    try:
        resolved, _origin = resolve_state_dir(state_dir or None, env)
    except Exception as exc:  # noqa: BLE001 - reported, never assumed
        return StateInfo(str(state_dir), "", (), f"State directory invalid: {exc}", False)
    db = resolved / STATE_DB_FILENAME
    temporary = is_temporary(resolved)
    if not db.is_file():
        return StateInfo(
            str(resolved), str(db), (), f"No imported state database at {db}", temporary
        )
    try:
        store = Store.open_read_only(db, SystemClock())
    except Exception as exc:  # noqa: BLE001
        return StateInfo(str(resolved), str(db), (), f"Cannot open {db}: {exc}", temporary)
    try:
        infos = []
        for src in store.list_sources():
            batches = store.list_batches(src.source_id)
            infos.append(
                SourceInfo(
                    src.source_id,
                    str(src.kind),
                    src.symbol,
                    len(batches),
                    sum(b.quote_count for b in batches),
                    _utc(min((b.min_provider_ms for b in batches), default=None)),
                    _utc(max((b.max_provider_ms for b in batches), default=None)),
                )
            )
    except Exception as exc:  # noqa: BLE001 - empty/corrupt/foreign database
        return StateInfo(str(resolved), str(db), (), f"Not a readable Grog state: {exc}", temporary)
    finally:
        store.close()
    problem = None if infos else f"{db} has no imported quote source yet"
    return StateInfo(str(resolved), str(db), tuple(infos), problem, temporary)


def import_guidance(state_dir: str) -> str:
    """The existing CLI import, spelled out; the desktop never imports by itself."""
    return (
        "Import an existing canonical BID/ASK CSV v1 file with the existing CLI "
        "(nothing is downloaded or imported automatically):\n"
        f"  uv run grog import-ticks --file /path/to/quotes.csv --source-id MY_SOURCE "
        f"--origin HISTORICAL --state-dir {shlex.quote(state_dir)}\n"
        "Then reopen the chooser (or press Inspect) and select the source."
    )


@dataclass(frozen=True, slots=True)
class LaunchPlan:
    selection: Selection | None  # None -> show the chooser
    reason: str  # why (shown in the chooser / printed)
    origin: str  # "arguments" | "saved" | "chooser"


def plan_launch(
    source_id: str | None,
    state_dir: str | None,
    config: str | None,
    from_ts: str | None,
    *,
    choose: bool = False,
    env: Mapping[str, str] | None = None,
) -> LaunchPlan:
    """Explicit arguments win; else a saved selection whose source still exists; else the
    chooser. A saved selection is verified read-only before it is trusted."""
    if choose:
        return LaunchPlan(None, "Source chooser requested (--choose)", "chooser")
    if source_id:
        return LaunchPlan(Selection(source_id, state_dir or "", config, from_ts), "", "arguments")
    saved, problem = read_selection(env)
    if saved is None:
        return LaunchPlan(None, problem or "No saved desktop source", "chooser")
    info = inspect_state(saved.state_dir, env)
    if not info.ok:
        return LaunchPlan(None, f"Saved desktop source unusable: {info.problem}", "chooser")
    if saved.source_id not in {s.source_id for s in info.sources}:
        return LaunchPlan(
            None,
            f"Saved source '{saved.source_id}' is not in {info.database} any more",
            "chooser",
        )
    if saved.config and not Path(saved.config).expanduser().is_file():
        return LaunchPlan(None, f"Saved config {saved.config} does not exist", "chooser")
    return LaunchPlan(saved, "", "saved")
