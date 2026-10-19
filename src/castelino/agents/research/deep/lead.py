"""Lead (gpt-6-sol): invents the angles for this topic, one brief per research agent; after the Critic,
plans agents for the gaps only."""

from __future__ import annotations

from castelino.agents.research.deep.models import Brief, Plan, ResearchSession, StepError
from castelino.agents.trade import llm
from castelino.config import get_settings

SYSTEM = """You lead a research team. Split the research question into angles that together answer it
fully: each angle is one question a single researcher can answer alone, with no overlap between angles.
Prefer fewer, higher-leverage angles. For each give name (2 to 4 words), angle (the question it answers)
and brief (what to find and where to look first). The researchers' tools: cited web search, X posts from
the last 7 days, FRED, Yahoo Finance, BLS and Polymarket. Where a clarifying question is unanswered,
choose a sensible assumption and state it in the briefs."""


def _context(s: ResearchSession) -> str:
    asked = "\n".join(
        f"- {q.question} → {s.answers.get(q.question, '(unanswered)')}"
        for q in s.clarifying_questions
    )
    return (
        f"Research question: {s.question}\nAs typed: {s.topic}\n\n"
        f"Clarifying questions and answers:\n{asked or '- (none)'}\n\n"
    )


def _ask(s: ResearchSession, ask: str, meter: llm.Meter) -> list[Brief]:
    cfg = get_settings().deep_research
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": _context(s) + ask}]
    return llm.structured("research_lead", cfg.lead_model, msgs, Plan, meter).briefs


def plan(s: ResearchSession, meter: llm.Meter) -> list[Brief]:
    cap = get_settings().deep_research.max_agents
    briefs = _ask(s, f"Return at most {cap} angles.", meter)[:cap]
    if not briefs:
        raise StepError("The Lead planned no research angles.")
    return briefs


def plan_gaps(s: ResearchSession, gaps: list[str], meter: llm.Meter) -> list[Brief]:
    cap = get_settings().deep_research.max_gap_agents
    done = "\n".join(f"- {a.letter} · {a.brief.name}: {a.brief.angle}" for a in s.agents)
    g = "\n".join(f"- {x}" for x in gaps)
    ask = (
        f"Angles already researched:\n{done}\n\nThe critic found these gaps:\n{g}\n\n"
        f"Plan angles for ONLY these gaps, at most {cap}."
    )
    return _ask(s, ask, meter)[:cap]
