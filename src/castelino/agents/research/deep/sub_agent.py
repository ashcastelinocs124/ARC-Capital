from __future__ import annotations

from castelino.agents.base import LLMClient, get_llm_client
from castelino.agents.research.deep.models import SubFinding, SubQuestion
from castelino.agents.research.deep.sonar_client import SonarClient
from castelino.config import get_settings

SYSTEM = """\
You distill raw web-research text into a structured finding for ONE
sub-question. Use ONLY the provided research text — do not add outside facts.
Summarize faithfully, extract the key points, and rate your confidence (0-1)
in how well the text answers the sub-question.
"""


class SubAgent:
    """One parallel researcher. Not a StructuredAgent subclass because it
    composes a Sonar call + an LLM distillation; it takes injectable clients
    so tests stay deterministic."""

    def __init__(self, *, llm: LLMClient | None = None, sonar: SonarClient):
        self._llm = llm or get_llm_client()
        self._sonar = sonar

    def run(self, sub_q: SubQuestion) -> SubFinding:
        cfg = get_settings()
        res = self._sonar.search(sub_q.text)
        if not res.content.strip():
            return SubFinding(
                sub_question_id=sub_q.id,
                summary="",
                error="no research content returned (Sonar empty or unavailable)",
                confidence=0.0,
            )
        tier = cfg.deep_research.fast_tier
        model_id = getattr(cfg.models, tier)
        finding = self._llm.parse(
            model=model_id,
            system=SYSTEM,
            user=(
                f"Sub-question: {sub_q.text}\n\n"
                f"Research text:\n{res.content}\n\n"
                "Produce a SubFinding. Set sub_question_id exactly to: "
                f"{sub_q.id}"
            ),
            schema=SubFinding,
        )
        # Force the id (LLMs drift) and merge Sonar's real source URLs.
        merged = list(finding.citations) + list(res.sources)
        return finding.model_copy(update={
            "sub_question_id": sub_q.id,
            "citations": merged,
        })
