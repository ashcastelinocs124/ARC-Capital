"""Critic (gpt-6-sol): reads what every researcher found and decides whether it answers the question, or
names the gaps for one more round. Judges the findings, before anything is written."""

from __future__ import annotations

from datetime import date

from castelino.agents.research.deep import guard
from castelino.agents.research.deep.models import Critique, ResearchSession
from castelino.agents.trade import llm
from castelino.config import get_settings

SYSTEM = """You are a strict research critic. Given the research question and what each researcher found,
decide whether the findings answer the question well enough to write a report. If not, list at most {n}
specific gaps that would materially change the answer. Do not ask for perfection: done is true when the
remaining gaps are minor. A finding marked (newest data: <year>) or (undated) rests on older data: it is
a gap when a newer release likely exists, so name the newer release to find."""


def findings_text(s: ResearchSession, today: date | None = None) -> str:
    """Each finding, marked when its newest cited figure is older than guard.fresh_year."""
    today = today or date.today()
    by, fresh, lines = s.fact_map(), guard.fresh_year(today), []
    for a in s.agents:
        if a.error:
            lines.append(f"## {a.letter} · {a.brief.name}: failed ({a.error})")
            continue
        lines.append(f"## {a.letter} · {a.brief.name}\nAngle: {a.brief.angle}")
        for f in a.findings:
            y = guard.newest_year(f.fact_ids, by, today)
            mark = "" if y >= fresh else f" (newest data: {y})" if y else " (undated)"
            lines.append(f"- {f.claim}{mark}")
    return "\n".join(lines)


def review(s: ResearchSession, meter: llm.Meter) -> Critique:
    cfg = get_settings().deep_research
    msgs = [
        {"role": "system", "content": SYSTEM.format(n=cfg.max_gap_agents)},
        {
            "role": "user",
            "content": f"Today is {date.today()}.\nResearch question: {s.question}\n\n"
            f"Findings:\n{findings_text(s)}",
        },
    ]
    out = llm.structured("research_critic", cfg.critic_model, msgs, Critique, meter)
    return out.model_copy(update={"gaps": out.gaps[: cfg.max_gap_agents]})
