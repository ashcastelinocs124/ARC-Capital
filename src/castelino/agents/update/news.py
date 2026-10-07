"""News agent: one cited web search for the day's market-moving stories; gpt-6-luna picks."""

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
from castelino.config import get_settings
from castelino.data import web_search

SEARCH_SYSTEM = (
    "You are a markets news desk. Report only what reputable sources published; "
    "quote figures exactly."
)
SEARCH_USER = """Date: {day}.
Focus: {brief}
{ask}
List the 6 most market-moving stories of the last 24 hours for a US macro investor (rates,
inflation, the Fed, equities, oil, FX). One bullet per story, one line each: what happened, with the
exact figures the source reports, ending with its citation. No other text."""

SYSTEM = f"""You are the news analyst on ARC Research's morning desk.
You get today's top market stories, each a numbered fact with its source.
{PICKER_RULES}"""


class NewsAgent(StructuredAgent[FindingDrafts]):
    name = "news_agent"
    output_schema = FindingDrafts
    tier = "fast"

    def __init__(self) -> None:
        self.model = get_settings().update_agent.agent_model

    def system_prompt(self) -> str:
        return SYSTEM

    def user_prompt(
        self, *, facts: list[Fact], brief: str, ask: str | None = None, cap: int = 6
    ) -> str:
        return drafts_prompt(facts, brief, ask, cap)


def run(brief: str, ask: str | None = None, *, search=web_search.search_cited) -> AgentOutput:
    cfg = get_settings().update_agent
    user = SEARCH_USER.format(
        day=date.today().isoformat(), brief=brief, ask=f"Also answer: {ask}" if ask else ""
    )
    text, cites = search(SEARCH_SYSTEM, user, model=cfg.search_model)
    facts = facts_from_search("N", text, cites)
    if not facts:
        raise RuntimeError("news: no cited stories")
    cap = cfg.max_findings_per_agent
    drafts = NewsAgent()(facts=facts, brief=brief, ask=ask, cap=cap)
    return AgentOutput(facts=facts, findings=to_findings(drafts, facts, "news", cap))
