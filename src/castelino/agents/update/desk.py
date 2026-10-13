"""Admin Daily desk: question, re-run and rebuild one day's Morning Note agents.

Chat only reads the day's files. Re-run and rebuild change them, under the same lock as the
daily run, so they can't collide with the 17:00 refresh.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from pydantic import BaseModel

from castelino.agents.base import StructuredAgent
from castelino.agents.update.fsio import acquire_lock, atomic_write_text, release_lock
from castelino.agents.update.models import AgentOutput, Briefs, DailyRecordV2, Fact, Finding
from castelino.config import get_settings

AGENTS = ("macro", "news", "alt", "ai")
DESK = (*AGENTS, "editor")
PREFIXES = {"macro": ("M", "B"), "news": ("N",), "alt": ("P", "X"), "ai": ("I",)}
_LOCK_SECONDS = 30 * 60
_ID = re.compile(r"^(.*?)(\d+)$")


def _dirs() -> tuple[Path, Path]:
    cfg = get_settings()
    ua = cfg.update_agent
    return cfg.root / ua.data_dir, cfg.root / ua.updates_dir


def load_day(updates_dir: Path, day: str) -> tuple[DailyRecordV2, list[Fact]]:
    record = DailyRecordV2.model_validate_json((updates_dir / f"{day}.json").read_text())
    raw = updates_dir / "raw" / f"{day}.json"
    facts = [Fact(**f) for f in json.loads(raw.read_text())] if raw.exists() else []
    return record, facts


def _next(ids: list[str], stem: str) -> int:
    nums = [int(m.group(2)) for i in ids if (m := _ID.match(i)) and m.group(1) == stem]
    return max(nums, default=0) + 1


def merge_output(
    findings: list[Finding], facts: list[Fact], out: AgentOutput
) -> tuple[list[Finding], list[Fact], int]:
    """Add a re-run's findings to the day. New ids continue each prefix (M21 after M20, macro-7
    after macro-6); a fact whose text the day already has reuses that fact's id."""
    facts = list(facts)
    by_text = {f.text: f.id for f in facts}
    remap: dict[str, str] = {}
    for f in out.facts:
        if f.text in by_text:
            remap[f.id] = by_text[f.text]
            continue
        m = _ID.match(f.id)
        stem = m.group(1) if m else f.id
        new_id = f"{stem}{_next([x.id for x in facts], stem)}"
        remap[f.id] = by_text[f.text] = new_id
        facts.append(f.model_copy(update={"id": new_id}))

    findings = list(findings)
    for f in out.findings:
        stem = f"{f.agent}-"
        new_id = f"{stem}{_next([x.id for x in findings], stem)}"
        fact_ids = [remap.get(i, i) for i in f.fact_ids]
        findings.append(f.model_copy(update={"id": new_id, "fact_ids": fact_ids}))
    return findings, facts, len(out.findings)


def _run_fn(agent: str):
    from castelino.agents.update import ai, alt, macro, news

    return {"macro": macro.run, "news": news.run, "alt": alt.run, "ai": ai.run}[agent]


def rerun(day: str, agent: str, ask: str) -> str:
    if agent not in AGENTS:
        raise ValueError(f"unknown agent {agent!r}")
    data_dir, updates_dir = _dirs()
    if not acquire_lock(data_dir, _LOCK_SECONDS):
        raise RuntimeError("another run is using the day's files; try again in a few minutes")
    try:
        record, facts = load_day(updates_dir, day)
        briefs_path = updates_dir / "briefs" / f"{day}.json"
        brief = (
            getattr(Briefs.model_validate_json(briefs_path.read_text()), agent)
            if briefs_path.exists()
            else ""
        ) or f"Cover what matters for markets on {day}."
        d = date.fromisoformat(day)
        out = _run_fn(agent)(brief, ask, **({} if d == date.today() else {"day": d}))
        findings, facts, added = merge_output(record.findings, facts, out)
        atomic_write_text(
            updates_dir / "raw" / f"{day}.json",
            json.dumps([f.model_dump() for f in facts], indent=1),
        )
        atomic_write_text(
            updates_dir / f"{day}.json",
            record.model_copy(update={"findings": findings}).model_dump_json(indent=2),
        )
        return f"{agent} added {added} finding(s). Rebuild the note to use them."
    finally:
        release_lock(data_dir)


def rebuild(day: str) -> str:
    from castelino.agents.update.runner import build_default_runner

    data_dir, _ = _dirs()
    if not acquire_lock(data_dir, _LOCK_SECONDS):
        raise RuntimeError("another run is using the day's files; try again in a few minutes")
    try:
        return "Note rebuilt: " + build_default_runner().rebuild(day)
    finally:
        release_lock(data_dir)


# ── chat ───────────────────────────────────────────────────────────────────


class DeskReply(BaseModel):
    answer: str


SYSTEM = """You are one agent on ARC Research's morning desk, answering the editor's questions
about your own work on one day. You get your findings and the numbered facts behind them.
Answer only from those. Cite fact or finding ids in square brackets, e.g. [M3] or [macro-2].
If the facts don't cover the question, say so plainly and suggest asking for a re-run.
Keep answers short: a few sentences."""


class DeskChatAgent(StructuredAgent[DeskReply]):
    name = "desk_chat"
    output_schema = DeskReply
    tier = "fast"

    def __init__(self) -> None:
        cfg = get_settings().update_agent
        self.model = cfg.agent_model
        self.max_output_tokens = cfg.max_output_tokens  # luna reasons first

    def system_prompt(self) -> str:
        return SYSTEM

    def user_prompt(self, *, day: str, agent: str, context: str, history: list[dict]) -> str:
        talk = "\n".join(f"{m['role'].upper()}: {m['text']}" for m in history)
        return f"Day: {day}\nYou are the {agent} agent.\n\n{context}\n\nConversation:\n{talk}"


def chat_context(record: DailyRecordV2, facts: list[Fact], agent: str) -> str:
    if agent == "editor":
        note = record.note
        lines = [f"Your note's headline: {note.headline}", "Takeaways:"]
        lines += [f"- {t}" for t in note.takeaways]
        lines += [
            f"Item {i.rank}: {i.title} — {i.body} (findings {i.finding_ids})" for i in note.items
        ]
        mine = record.findings
    else:
        mine = [f for f in record.findings if f.agent == agent]
        lines = []
    cited = {i for f in mine for i in f.fact_ids}
    own = PREFIXES.get(agent)
    keep = [f for f in facts if f.id in cited or (own and f.id.startswith(own))]
    lines += ["Findings:"] + [f"[{f.id}] {f.claim} (facts {f.fact_ids})" for f in mine]
    lines += ["Facts:"] + [f"[{f.id}] {f.text} — {f.source_title}" for f in keep]
    return "\n".join(lines)


MAX_TURNS, MAX_CHARS = 20, 2000


def chat(day: str, agent: str, history: list[dict]) -> str:
    if agent not in DESK:
        raise ValueError(f"unknown agent {agent!r}")
    history = [
        {
            "role": "you" if m.get("role") == "user" else "agent",
            "text": str(m.get("text", ""))[:MAX_CHARS],
        }
        for m in history[-MAX_TURNS:]
    ]
    _, updates_dir = _dirs()
    record, facts = load_day(updates_dir, day)
    return DeskChatAgent()(
        day=day, agent=agent, context=chat_context(record, facts, agent), history=history
    ).answer
