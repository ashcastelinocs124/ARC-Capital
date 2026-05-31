from __future__ import annotations

from castelino.agents.base import StructuredAgent
from castelino.agents.research.deep.models import DecompositionResult, SubQuestion
from castelino.config import get_settings

SYSTEM = """\
You are the Lead Researcher. Decompose a research question into a small set of
INDEPENDENT sub-questions that can each be researched in isolation and whose
answers together fully cover the main question. Each sub-question gets a short
rationale. Prefer fewer, higher-leverage sub-questions over many shallow ones.
Do not overlap sub-questions.
"""


class LeadAgent(StructuredAgent[DecompositionResult]):
    name = "deep_lead"
    output_schema = DecompositionResult

    @property
    def tier(self) -> str:
        return get_settings().deep_research.reasoning_tier

    def system_prompt(self) -> str:
        return SYSTEM

    def user_prompt(self, *, reworded_query, answers, round_num, gaps=None) -> str:
        ans = "\n".join(f"- {k}: {v}" for k, v in (answers or {}).items()) or "- (none)"
        cap = get_settings().deep_research.max_sub_questions
        base = (
            f"Main question: {reworded_query}\n\n"
            f"Analyst clarifications:\n{ans}\n\n"
        )
        if gaps:
            g = "\n".join(f"- {x}" for x in gaps)
            base += f"This is round {round_num}. Cover ONLY these gaps:\n{g}\n\n"
        return base + f"Return at most {cap} sub-questions."

    def decompose(self, *, reworded_query, answers, round_num, gaps=None):
        cap = get_settings().deep_research.max_sub_questions
        result = self(
            reworded_query=reworded_query, answers=answers,
            round_num=round_num, gaps=gaps,
        )
        # Hard cap regardless of what the LLM returned; stamp the round.
        out: list[SubQuestion] = []
        for i, q in enumerate(result.sub_questions[:cap]):
            out.append(q.model_copy(update={
                "round": round_num,
                "id": q.id or f"r{round_num}q{i}",
            }))
        return out
