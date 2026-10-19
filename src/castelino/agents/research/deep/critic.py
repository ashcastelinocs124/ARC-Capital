"""Critic (gpt-6-sol): reads what every researcher found and decides whether it answers the question, or
names the gaps for one more round. Judges the findings, before anything is written."""

from __future__ import annotations

from castelino.agents.research.deep.models import Critique, ResearchSession
from castelino.agents.trade import llm
from castelino.config import get_settings

SYSTEM = """You are a strict research critic. Given the research question and what each researcher found,
decide whether the findings answer the question well enough to write a report. If not, list at most {n}
specific gaps that would materially change the answer. Do not ask for perfection: done is true when the
remaining gaps are minor."""


def findings_text(s: ResearchSession) -> str:
    lines: list[str] = []
    for a in s.agents:
        if a.error:
            lines.append(f"## {a.letter} · {a.brief.name}: failed ({a.error})")
            continue
        lines.append(f"## {a.letter} · {a.brief.name}\nAngle: {a.brief.angle}")
        lines += [f"- {f.claim}" for f in a.findings]
    return "\n".join(lines)


def review(s: ResearchSession, meter: llm.Meter) -> Critique:
    cfg = get_settings().deep_research
    msgs = [
        {"role": "system", "content": SYSTEM.format(n=cfg.max_gap_agents)},
        {"role": "user", "content": f"Research question: {s.question}\n\nFindings:\n{findings_text(s)}"},
    ]
    out = llm.structured("research_critic", cfg.critic_model, msgs, Critique, meter)
    return out.model_copy(update={"gaps": out.gaps[: cfg.max_gap_agents]})
