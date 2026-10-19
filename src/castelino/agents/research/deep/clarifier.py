"""Clarifier (gpt-6-sol): rewords the topic into one research question and asks up to 3 clarifying
questions, each with why it matters. Runs in the request, before anything is spent on research."""

from __future__ import annotations

from castelino.agents.research.deep.models import Clarification
from castelino.agents.trade import llm
from castelino.config import get_settings

SYSTEM = """You are the Clarifier of a research team. Given a topic or question someone typed:
1. question: reword it as one precise, self-contained research question.
2. questions: up to {cap} short clarifying questions whose answers would change the research most (scope,
   time window, geography, angle), each with a one-line why. Ask nothing the topic already answers; return
   none if it is fully specified."""


def clarify(topic: str, meter: llm.Meter) -> Clarification:
    cfg = get_settings().deep_research
    msgs = [
        {"role": "system", "content": SYSTEM.format(cap=cfg.clarify_max_questions)},
        {"role": "user", "content": f"Topic: {topic.strip()}"},
    ]
    out = llm.structured("research_clarifier", cfg.clarifier_model, msgs, Clarification, meter)
    return out.model_copy(update={"questions": out.questions[: cfg.clarify_max_questions]})
