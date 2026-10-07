"""Alt agent: Polymarket odds moves (code) + what financial X is saying (cited web search)."""

from __future__ import annotations

import logging
from datetime import date

from castelino.agents.base import StructuredAgent
from castelino.agents.update.facts import (
    PICKER_RULES,
    drafts_prompt,
    facts_from_search,
    to_findings,
)
from castelino.agents.update.models import AgentOutput, Fact, FindingDrafts
from castelino.agents.update.sources import polymarket
from castelino.config import get_settings
from castelino.data import web_search

log = logging.getLogger(__name__)

X_SYSTEM = (
    "You are a social media analyst for a macro fund. Report what was actually posted; cite posts."
)
X_USER = """Date: {day}.
Focus: {brief}
{ask}
What are financial X (Twitter) accounts — macro investors, economists, Fed watchers — saying in
the last 24 hours about the Fed, inflation, rates and markets? One bullet per distinct view, one
line each, ending with its citation. Include any figures exactly as posted. No other text."""

SYSTEM = f"""You are the alternative-data analyst on ARC Research's morning desk.
You get Polymarket prediction-market odds and their moves, and what financial X is saying, each as
a numbered fact. Highlight where the crowd moved or disagrees with consensus.
{PICKER_RULES}"""


class AltAgent(StructuredAgent[FindingDrafts]):
    name = "alt_agent"
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
    brief: str,
    ask: str | None = None,
    *,
    events_fn=polymarket.fetch_events,
    search=web_search.search_cited,
) -> AgentOutput:
    cfg = get_settings().update_agent
    facts: list[Fact] = []
    try:
        facts += polymarket.facts(events_fn())
    except Exception as exc:  # noqa: BLE001 — X can still carry the agent
        log.warning("alt: polymarket failed: %s", exc)
    try:
        user = X_USER.format(
            day=date.today().isoformat(), brief=brief, ask=f"Also answer: {ask}" if ask else ""
        )
        facts += facts_from_search("X", *search(X_SYSTEM, user, model=cfg.search_model))
    except Exception as exc:  # noqa: BLE001
        log.warning("alt: X search failed: %s", exc)
    if not facts:
        raise RuntimeError("alt: Polymarket and X both returned nothing")
    cap = cfg.max_findings_per_agent
    drafts = AltAgent()(facts=facts, brief=brief, ask=ask, cap=cap)
    return AgentOutput(facts=facts, findings=to_findings(drafts, facts, "alt", cap))
