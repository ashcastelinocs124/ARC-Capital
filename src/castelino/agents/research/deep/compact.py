"""After keep_full_days a session keeps a summary per agent instead of its full thread: transcripts,
uncited facts and the board are dropped; the report, the facts it cites and the edit log stay. Runs when an
old session is listed or opened (no scheduler: a report never reopened just stays full-size)."""

from __future__ import annotations

from datetime import datetime, timedelta

from castelino.agents.research.deep import store
from castelino.agents.research.deep.models import ResearchSession, Summary
from castelino.agents.trade import llm
from castelino.config import get_settings

SYSTEM = """Summarize what this researcher found, for a colleague who will answer questions about it later
without the notes: the angle, the main findings with their fact ids, and what stayed uncertain. At most
150 words."""


def due(s: ResearchSession, now: datetime | None = None) -> bool:
    if s.compacted_at or s.status != "complete":
        return False
    if (s.job and s.job.state in ("queued", "running")) or any(
        p.status == "running" for p in s.proposals
    ):
        return False
    age = (now or datetime.now()) - datetime.fromisoformat(s.created_at)
    return age > timedelta(days=get_settings().deep_research.keep_full_days)


def compact(sid: str, meter: llm.Meter) -> None:
    cfg = get_settings().deep_research
    s = store.load(sid)
    cited = {i for p in (s.report.points if s.report else []) for i in p.fact_ids}
    summaries: dict[str, str] = {}
    for a in s.agents:
        if a.summary:
            continue
        findings = "\n".join(f"- {f.claim} [{', '.join(f.fact_ids)}]" for f in a.findings)
        user = (
            f"Researcher {a.letter} · {a.brief.name}\nAngle: {a.brief.angle}\n"
            f"Findings:\n{findings or '(none)'}" + (f"\nError: {a.error}" if a.error else "")
        )
        msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
        out = llm.structured("research_compact", cfg.compact_model, msgs, Summary, meter)
        summaries[a.letter] = out.text
    with store.edit(sid) as x:
        for a in x.agents:
            a.summary = summaries.get(a.letter, a.summary)
            a.transcript = None
            a.facts = [f for f in a.facts if f.id in cited]
        x.board, x.board_facts, x.compacted_at = [], {}, store.now()
