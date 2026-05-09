"""Memory I/O — the only legal way to write the journals.

Enforces the R/W matrix from `docs/plans/2026-05-03-castelino-capital-design.md` §6.
Every writer presents a `WriterIdentity`. The gate refuses writes that violate
the matrix. This is a structural guarantee, not a convention.

Markdown layout — short_term_journal.md is human-readable but machine-written.
Each entry is delimited by a YAML frontmatter block so we can round-trip:

    ---
    entry_id: hyp-abc123
    kind: Hypothesis
    timestamp: 2026-05-04T...
    ---
    {full pydantic JSON dump}
    ---

`short_term_index.json` maps `entry_id -> byte_offset` for cheap retrieval.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

from pydantic import TypeAdapter

from castelino.config import get_settings
from castelino.memory.schemas import JournalEntry, LongTermLesson, TradeEvent

log = logging.getLogger(__name__)


# ───────────────────────── identity & matrix ──────────────────────────────


class WriterIdentity(str, Enum):
    """Every component that touches a journal must declare itself."""

    HYPOTHESIS_AGENT = "hypothesis_agent"
    ASSET_SELECTION_AGENT = "asset_selection_agent"
    RESEARCH_AGENT = "research_agent"
    BULL_AGENT = "bull_agent"
    BEAR_AGENT = "bear_agent"
    DEBATE_AGENT = "debate_agent"
    GUARD_AGENT = "guard_agent"
    PORTFOLIO_AGENT = "portfolio_agent"
    CURATOR_AGENT = "curator_agent"
    EXECUTION = "execution"
    MARK_LOOP = "mark_loop"
    CURRENT_EVENT_AGENT = "current_event_agent"
    TRIGGER_RUNNER = "trigger_runner"
    HUMAN = "human"


class Journal(str, Enum):
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    PRINCIPLES = "core_principles"


# Per design §6 read/write matrix — only WRITE rights enumerated.
_WRITE_MATRIX: dict[Journal, set[WriterIdentity]] = {
    Journal.SHORT_TERM: {
        WriterIdentity.PORTFOLIO_AGENT,
        WriterIdentity.CURATOR_AGENT,    # trim only — enforced by op type, see below
        WriterIdentity.EXECUTION,        # trade events
        WriterIdentity.MARK_LOOP,        # nav snapshots / stop-loss events
        WriterIdentity.TRIGGER_RUNNER,   # trigger records
        WriterIdentity.CURRENT_EVENT_AGENT,
        WriterIdentity.HYPOTHESIS_AGENT,
        WriterIdentity.ASSET_SELECTION_AGENT,
        WriterIdentity.BULL_AGENT,
        WriterIdentity.BEAR_AGENT,
        WriterIdentity.DEBATE_AGENT,
        WriterIdentity.GUARD_AGENT,
        WriterIdentity.RESEARCH_AGENT,
    },
    Journal.LONG_TERM: {
        WriterIdentity.CURATOR_AGENT,
    },
    Journal.PRINCIPLES: {
        WriterIdentity.HUMAN,
    },
}

# Curator can TRIM short_term but cannot freely append — gated by `op` field.
_TRIM_ONLY_WRITERS = {
    Journal.SHORT_TERM: {WriterIdentity.CURATOR_AGENT},
}


class WriteForbidden(PermissionError):
    """Raised when an identity tries to write a journal it doesn't own."""


def _check_write(journal: Journal, who: WriterIdentity, op: str) -> None:
    allowed = _WRITE_MATRIX.get(journal, set())
    if who not in allowed:
        raise WriteForbidden(
            f"{who.value!r} is not authorized to write {journal.value!r}. "
            f"Authorized writers: {sorted(w.value for w in allowed)}"
        )
    if (
        journal in _TRIM_ONLY_WRITERS
        and who in _TRIM_ONLY_WRITERS[journal]
        and op == "append"
    ):
        raise WriteForbidden(
            f"{who.value!r} may only TRIM {journal.value!r}, not append. "
            f"Use op='trim' or 'rewrite'."
        )


# ───────────────────────── journal layout ─────────────────────────────────


@dataclass(frozen=True)
class JournalPaths:
    short_term_md: Path
    short_term_index: Path
    long_term_md: Path
    principles_md: Path


def _paths() -> JournalPaths:
    s = get_settings()
    d = s.resolved_paths.data
    return JournalPaths(
        short_term_md=d / "short_term_journal.md",
        short_term_index=d / "short_term_index.json",
        long_term_md=d / "long_term_journal.md",
        principles_md=d / "core_principles.md",
    )


def _ensure_journal_files() -> None:
    p = _paths()
    p.short_term_md.parent.mkdir(parents=True, exist_ok=True)
    if not p.short_term_md.exists():
        p.short_term_md.write_text(
            "# Castelino Capital — Short-Term Journal\n\n"
            "Rolling working memory. Auto-written by the pipeline.\n\n",
            encoding="utf-8",
        )
    if not p.short_term_index.exists():
        p.short_term_index.write_text("{}", encoding="utf-8")
    if not p.long_term_md.exists():
        p.long_term_md.write_text(
            "# Castelino Capital — Long-Term Journal\n\n"
            "Curator-written lessons. One entry per pattern.\n\n",
            encoding="utf-8",
        )


# ───────────────────────── append / read ──────────────────────────────────


_ENTRY_ADAPTER = TypeAdapter(JournalEntry)


def _serialize_entry(entry: JournalEntry) -> str:
    """One entry → markdown block with frontmatter + JSON body."""
    fm = (
        f"---\n"
        f"entry_id: {entry.entry_id}\n"
        f"kind: {entry.kind}\n"
        f"timestamp: {entry.timestamp.isoformat()}\n"
        f"---\n"
    )
    body = entry.model_dump_json(indent=2)
    return f"{fm}{body}\n---\n\n"


def append_short_term(entry: JournalEntry, who: WriterIdentity) -> None:
    """Append a single entry to short_term_journal.md and update the index."""
    _check_write(Journal.SHORT_TERM, who, "append")
    _ensure_journal_files()
    p = _paths()

    block = _serialize_entry(entry)
    # Compute byte offset *before* the write so the index points at the start.
    offset = p.short_term_md.stat().st_size
    with p.short_term_md.open("ab") as f:
        f.write(block.encode("utf-8"))

    idx = json.loads(p.short_term_index.read_text(encoding="utf-8") or "{}")
    idx[entry.entry_id] = {
        "kind": entry.kind,
        "offset": offset,
        "length": len(block.encode("utf-8")),
        "timestamp": entry.timestamp.isoformat(),
    }
    p.short_term_index.write_text(json.dumps(idx, indent=2, default=str), encoding="utf-8")


def append_long_term(lesson: LongTermLesson, who: WriterIdentity) -> None:
    """Curator-only: append a long-term lesson."""
    _check_write(Journal.LONG_TERM, who, "append")
    _ensure_journal_files()
    p = _paths()
    with p.long_term_md.open("a", encoding="utf-8") as f:
        f.write(_serialize_entry(lesson))


def trim_short_term(keep_entry_ids: set[str], who: WriterIdentity) -> int:
    """Curator-only: rewrite short_term_journal.md keeping only `keep_entry_ids`.

    Returns the number of entries dropped.
    """
    _check_write(Journal.SHORT_TERM, who, "trim")
    p = _paths()

    entries = list(read_short_term())
    kept = [e for e in entries if e.entry_id in keep_entry_ids]
    dropped = len(entries) - len(kept)

    # Rewrite from header
    header = (
        "# Castelino Capital — Short-Term Journal\n\n"
        "Rolling working memory. Auto-written by the pipeline.\n\n"
    )
    new_idx: dict[str, dict] = {}
    body_parts: list[str] = []
    cursor = len(header.encode("utf-8"))
    for e in kept:
        block = _serialize_entry(e)
        new_idx[e.entry_id] = {
            "kind": e.kind,
            "offset": cursor,
            "length": len(block.encode("utf-8")),
            "timestamp": e.timestamp.isoformat(),
        }
        body_parts.append(block)
        cursor += len(block.encode("utf-8"))

    p.short_term_md.write_bytes((header + "".join(body_parts)).encode("utf-8"))
    p.short_term_index.write_text(json.dumps(new_idx, indent=2, default=str), encoding="utf-8")
    return dropped


def read_short_term() -> list[JournalEntry]:
    """Yield every entry in the short-term journal in chronological order.

    Reads are unrestricted. Anyone can read any journal.
    """
    p = _paths()
    if not p.short_term_md.exists():
        return []
    raw = p.short_term_md.read_text(encoding="utf-8")
    return _parse_entries(raw)


def read_long_term() -> list[LongTermLesson]:
    p = _paths()
    if not p.long_term_md.exists():
        return []
    raw = p.long_term_md.read_text(encoding="utf-8")
    parsed = _parse_entries(raw)
    return [e for e in parsed if isinstance(e, LongTermLesson)]


def read_principles() -> str:
    p = _paths()
    return p.principles_md.read_text(encoding="utf-8") if p.principles_md.exists() else ""


def _parse_entries(raw: str) -> list[JournalEntry]:
    out: list[JournalEntry] = []
    # Block format: --- frontmatter --- {json body} ---
    # Split conservatively, then walk in groups.
    chunks = raw.split("\n---\n")
    # chunks alternate: [header_text, frontmatter_block, json_block, frontmatter_block, json_block, ...]
    i = 0
    while i < len(chunks):
        c = chunks[i]
        if c.lstrip().startswith("entry_id:"):
            # frontmatter found; next chunk should be the JSON body
            if i + 1 < len(chunks):
                body = chunks[i + 1].strip()
                if body.startswith("{"):
                    try:
                        out.append(_ENTRY_ADAPTER.validate_json(body))
                    except Exception as e:
                        log.warning("skipped malformed journal entry: %s", e)
            i += 2
        else:
            i += 1
    return out


# ───────────────────────── retrieval helpers ──────────────────────────────


def find_by_id(entry_id: str) -> JournalEntry | None:
    p = _paths()
    if not p.short_term_index.exists():
        return None
    idx = json.loads(p.short_term_index.read_text(encoding="utf-8") or "{}")
    record = idx.get(entry_id)
    if not record:
        return None
    with p.short_term_md.open("rb") as f:
        f.seek(int(record["offset"]))
        block = f.read(int(record["length"])).decode("utf-8", errors="replace")
    chunks = block.split("\n---\n")
    for chunk in chunks:
        chunk = chunk.strip()
        if chunk.startswith("{"):
            try:
                return _ENTRY_ADAPTER.validate_json(chunk)
            except Exception as e:
                log.warning("found_by_id parse failed for %s: %s", entry_id, e)
                return None
    return None


def latest_n(kind: str | None = None, n: int = 10) -> list[JournalEntry]:
    entries = read_short_term()
    if kind:
        entries = [e for e in entries if e.kind == kind]
    return sorted(entries, key=lambda e: e.timestamp, reverse=True)[:n]


def journal_summary() -> dict[str, int]:
    """Counts by entry kind — used by reporting and debug."""
    counts: dict[str, int] = {}
    for e in read_short_term():
        counts[e.kind] = counts.get(e.kind, 0) + 1
    return counts


# ───────────────────────── trade-event helper ─────────────────────────────


def journal_trade_event(
    event: TradeEvent,
    who: WriterIdentity = WriterIdentity.EXECUTION,
) -> None:
    """Convenience wrapper used by post-`execute()` callers.

    `who` defaults to EXECUTION (orchestrator-driven fills) but the daily mark
    loop must pass `WriterIdentity.MARK_LOOP` so the R/W matrix matches the
    design — and so the journal source-tags the event correctly.
    """
    append_short_term(event, who)


# ───────────────────────── reset (for tests / replay) ─────────────────────


def reset_journals(confirm_token: str = "") -> None:
    """Wipe ST + LT journals (KEEPS principles + portfolio).

    Test/CLI hatch only — guarded so accidental imports can't blow away history.
    """
    if confirm_token != "I_KNOW_WHAT_I_AM_DOING":
        raise RuntimeError(
            "reset_journals refused: pass confirm_token='I_KNOW_WHAT_I_AM_DOING'"
        )
    p = _paths()
    for f in (p.short_term_md, p.short_term_index, p.long_term_md):
        if f.exists():
            os.remove(f)
    _ensure_journal_files()
