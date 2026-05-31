from __future__ import annotations

from castelino.agents.base import StructuredAgent
from castelino.agents.research.deep.models import ClarifierResult
from castelino.config import get_settings

SYSTEM = """\
You are the Clarifier in a deep-research system. Given a user's raw research
query you do TWO things:
1. Reword it into a single precise, self-contained research question.
2. Produce a SHORT list of clarifying questions (each with a one-line `why`)
   whose answers would most sharpen the research. Ask only what materially
   changes the research — scope, timeframe, geography, the user's intent.
If the query is already fully specified, return an empty question list and put
any reasonable assumptions in `assumptions`.
"""


class ClarifierAgent(StructuredAgent[ClarifierResult]):
    name = "deep_clarifier"
    output_schema = ClarifierResult

    @property
    def tier(self) -> str:  # resolved from config, not hardcoded
        return get_settings().deep_research.reasoning_tier

    def system_prompt(self) -> str:
        return SYSTEM

    def user_prompt(self, *, query: str) -> str:
        cap = get_settings().deep_research.clarify_max_questions
        return (
            f"Raw query: {query}\n\n"
            f"Return at most {cap} clarifying questions."
        )
