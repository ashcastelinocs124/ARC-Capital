"""Memory Curator — weekly cron.

Reads recent ST entries and aged-out entries, distills patterns into
`LongTermLesson`s, and trims ST per capacity rules.

Two modes:
- `consolidate()` — full pass: trim ST, generate LT lessons.
- `prune_only()` — deterministic trim, no LLM call (for cheap maintenance).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import List

from pydantic import BaseModel, Field

from castelino.agents.base import StructuredAgent
from castelino.config import get_settings
from castelino.memory import io as memio
from castelino.memory.io import WriterIdentity
from castelino.memory.schemas import (
    Hypothesis,
    JournalEntry,
    LongTermLesson,
    PrincipleWarning,
    TradeEvent,
    Verdict,
)

log = logging.getLogger(__name__)


class CurationOutput(BaseModel):
    lessons: List[LongTermLesson] = Field(default_factory=list)
    keep_entry_ids: List[str] = Field(default_factory=list)
    rationale: str = ""


SYSTEM = """\
You are the Memory Curator at a multi-asset macro fund. Your job is to look
across recent trades, hypotheses, and warnings, find genuine PATTERNS, and
distill them into 0–5 LongTermLessons.

Quality bar (very high):
- A lesson must be supported by ≥ 3 observations.
- State the statistical backing (e.g. "5 of 7 disinflation-thesis bond trades
  closed positive over 21d").
- Lessons must be actionable for FUTURE agents — not retrospective commentary.
- Categories: regime_pattern | vehicle_preference | recurring_bias | category_hit_rate.

Output also includes the entry_ids you want to KEEP in short-term memory
(everything else gets trimmed). Do NOT keep all entries — the point is to
compress. Keep:
  • All open-position trade events
  • The most recent 20 closed trades
  • Hypotheses from the last 30 days
  • Principle warnings from the last 90 days
"""


class CuratorAgent(StructuredAgent[CurationOutput]):
    name = "curator"
    output_schema = CurationOutput
    tier = "reasoning"

    def system_prompt(self) -> str:
        return SYSTEM

    def user_prompt(self, *, recent_entries: list[JournalEntry], existing_lt: list[LongTermLesson]) -> str:
        def _fmt(e: JournalEntry) -> str:
            if isinstance(e, Hypothesis):
                return f"[Hypothesis {e.entry_id}] regime={e.regime.value} conv={e.conviction.value}: {e.thesis}"
            if isinstance(e, Verdict):
                return f"[Verdict {e.entry_id}] {e.decision} — {e.decisive_factor}"
            if isinstance(e, TradeEvent):
                return (
                    f"[Trade {e.entry_id}] {e.event_type} {e.instrument_id} "
                    f"qty={e.quantity:+.2f} pnl={e.realized_pnl:.2f}"
                )
            if isinstance(e, PrincipleWarning):
                return f"[Warn {e.entry_id}] {e.rule_id} {e.severity}: {e.description}"
            return f"[{e.kind} {e.entry_id}]"

        recent = "\n".join(_fmt(e) for e in recent_entries[-200:]) or "- (none)"
        existing = "\n".join(f"- {l.title}: {l.body}" for l in existing_lt[-15:]) or "- (none)"
        return (
            "Existing long-term lessons (DO NOT duplicate; supersede only if "
            "new evidence overturns them):\n"
            f"{existing}\n\n"
            "Recent short-term entries (chronological):\n"
            f"{recent}\n\n"
            "Produce 0–5 NEW lessons + the keep_entry_ids list."
        )


# ───────────────────────── public entry points ────────────────────────────


def _capacity_filter(entries: list[JournalEntry]) -> set[str]:
    """Deterministic-ish keep set used by `prune_only` and as a sanity floor.

    Keeps everything that matches the design's capacity bands.
    """
    cfg = get_settings().curator
    keep: set[str] = set()
    now = datetime.now(UTC)

    closed_trades = [
        e for e in entries
        if isinstance(e, TradeEvent) and e.event_type in ("close", "stop_loss")
    ]
    closed_trades.sort(key=lambda e: e.timestamp, reverse=True)
    for e in closed_trades[: cfg.st_max_closed_trades]:
        keep.add(e.entry_id)

    # All open events (we'll later assume open == not closed yet — keep all opens)
    for e in entries:
        if isinstance(e, TradeEvent) and e.event_type == "open":
            keep.add(e.entry_id)

    # Hypotheses within window
    cutoff_h = now - timedelta(days=cfg.st_max_hypothesis_days)
    for e in entries:
        if isinstance(e, Hypothesis) and e.timestamp >= cutoff_h:
            keep.add(e.entry_id)

    # Trigger records within window — we use TriggerRecord by kind
    cutoff_t = now - timedelta(days=cfg.st_max_trigger_days)
    for e in entries:
        if e.kind == "TriggerRecord" and e.timestamp >= cutoff_t:
            keep.add(e.entry_id)

    # Principle warnings within window
    cutoff_w = now - timedelta(days=cfg.st_max_warning_days)
    for e in entries:
        if isinstance(e, PrincipleWarning) and e.timestamp >= cutoff_w:
            keep.add(e.entry_id)

    return keep


def consolidate() -> dict:
    """Full curator pass: LLM lessons + ST trim. Returns a summary dict."""
    entries = memio.read_short_term()
    existing_lt = memio.read_long_term()
    out = CuratorAgent()(recent_entries=entries, existing_lt=existing_lt)

    # Floor the keep set with the capacity filter so the LLM can't accidentally
    # nuke open positions.
    keep = set(out.keep_entry_ids) | _capacity_filter(entries)
    dropped = memio.trim_short_term(keep, WriterIdentity.CURATOR_AGENT)

    for lesson in out.lessons:
        memio.append_long_term(lesson, WriterIdentity.CURATOR_AGENT)

    log.info("curator: %d lessons added, %d entries trimmed", len(out.lessons), dropped)
    return {
        "n_lessons": len(out.lessons),
        "n_entries_trimmed": dropped,
        "rationale": out.rationale,
    }


def prune_only() -> dict:
    """Cheap deterministic trim — no LLM call."""
    entries = memio.read_short_term()
    keep = _capacity_filter(entries)
    dropped = memio.trim_short_term(keep, WriterIdentity.CURATOR_AGENT)
    return {"n_entries_trimmed": dropped}
