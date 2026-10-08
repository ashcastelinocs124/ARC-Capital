"""AI analyst: one cited web search for the day's AI models and chips; gpt-6-luna picks."""

from __future__ import annotations

from datetime import date

from castelino.agents.base import StructuredAgent
from castelino.agents.update.facts import (
    PICKER_RULES,
    drafts_prompt,
    facts_from_search,
    to_findings,
)
from castelino.agents.update.models import AgentOutput, Fact, FindingDrafts
from castelino.agents.update.news import window_for
from castelino.config import get_settings
from castelino.data import web_search

SEARCH_SYSTEM = (
    "You are an AI-industry desk. Report only what companies announced or reputable outlets "
    "published; no anonymous social-media rumours. Quote figures exactly."
)
SEARCH_USER = """Date: {day}.
Focus: {brief}
{ask}
List the 6 most important AI-industry stories of {window} for a markets reader: new AI model
releases, credible reports of upcoming model releases (say who reported it), new AI chips or
accelerators, and major AI deals or spending news. One bullet per story, one line each: what
happened, with the exact figures the source reports, ending with its citation. No other text."""

SYSTEM = f"""You are the AI analyst on ARC Research's morning desk.
You get today's AI model, chip and industry stories, each a numbered fact with its source.
Prefer what matters for markets: launches, chips, capex and the companies behind them.
{PICKER_RULES}"""


class AiAgent(StructuredAgent[FindingDrafts]):
    name = "ai_agent"
    output_schema = FindingDrafts
    tier = "fast"

    def __init__(self) -> None:
        cfg = get_settings().update_agent
        self.model = cfg.agent_model
        self.max_output_tokens = cfg.max_output_tokens  # luna reasons first

    def system_prompt(self) -> str:
        return SYSTEM

    def user_prompt(
        self, *, facts: list[Fact], brief: str, ask: str | None = None, cap: int = 6
    ) -> str:
        return drafts_prompt(facts, brief, ask, cap)


def run(
    brief: str, ask: str | None = None, *, search=web_search.search_cited, day: date | None = None
) -> AgentOutput:
    cfg = get_settings().update_agent
    user = SEARCH_USER.format(
        day=(day or date.today()).isoformat(),
        window=window_for(day),
        brief=brief,
        ask=f"Also answer: {ask}" if ask else "",
    )
    text, cites = search(SEARCH_SYSTEM, user, model=cfg.search_model)
    facts = facts_from_search("I", text, cites)
    if not facts:
        raise RuntimeError("ai: no cited stories")
    cap = cfg.max_findings_per_agent
    drafts = AiAgent()(facts=facts, brief=brief, ask=ask, cap=cap)
    return AgentOutput(facts=facts, findings=to_findings(drafts, facts, "ai", cap))
