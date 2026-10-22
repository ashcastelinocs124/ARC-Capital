"""Orchestrator: briefs the Macro / News / Alt agents, then reviews what they found."""

from __future__ import annotations

from castelino.agents.base import StructuredAgent, get_llm_client
from castelino.agents.update.models import Briefs, Finding, Review
from castelino.config import get_settings

PLAN_SYSTEM = """You run the morning research desk at ARC Research, a macro fund. Three agents
work for you:
- macro: US economic releases (FRED, BLS), Treasury yields, and moves in equities, sectors,
  commodities, credit and FX.
- news: today's market-moving news, via web search.
- alt: Polymarket odds moves on Fed and economy markets, and what financial X is saying.
- ai: new AI model releases, credibly reported upcoming releases, AI chips and AI industry news.
Write one brief per agent, 1-3 sentences, naming what to prioritise today. Prioritise what is
new today. Memory is background only: brief on an old theme only if today's data is likely to
move it. Do not state any numbers."""

REVIEW_SYSTEM = """You review what your three research agents found for this morning's note.
Return done=true if the findings support a 5-item note with a clear lead story. Otherwise return
at most one follow-up ask per agent, and only for a real gap or a conflict between agents (for
example news says oil spiked but macro shows no move). One sentence per ask."""


class UpdateOrchestrator(StructuredAgent[Briefs]):
    name = "update_orchestrator"
    output_schema = Briefs
    tier = "reasoning"

    def __init__(self) -> None:
        cfg = get_settings().update_agent
        self.model = cfg.orchestrator_model
        self.max_output_tokens = cfg.max_output_tokens

    def system_prompt(self) -> str:
        return PLAN_SYSTEM

    def user_prompt(
        self, *, memory_md: str, long_term_md: str, today: str, watch_md: str = ""
    ) -> str:
        out = (
            f"Date: {today}\n\n## Short-term memory\n{memory_md or '(empty)'}"
            f"\n\n## Long-term memory\n{long_term_md or '(empty)'}"
        )
        if watch_md:  # ARC's topic consultants: what each is watching (briefs may chase it)
            out += f"\n\n## Consultants are watching\n{watch_md}"
        return out


def plan(memory_md: str, long_term_md: str, today: str, watch_md: str = "") -> Briefs:
    return UpdateOrchestrator()(
        memory_md=memory_md, long_term_md=long_term_md, today=today, watch_md=watch_md
    )


def review(findings: list[Finding], round_no: int) -> Review:
    o = UpdateOrchestrator()
    lines = "\n".join(f"[{f.id}] ({f.agent}) {f.claim}" for f in findings) or "(none)"
    return get_llm_client().parse(
        model=o.model,
        system=REVIEW_SYSTEM,
        user=f"Follow-up round {round_no + 1}.\n\n## Findings\n{lines}",
        schema=Review,
        max_tokens=o.max_output_tokens,
    )
