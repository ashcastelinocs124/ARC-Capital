from __future__ import annotations

from castelino.agents.base import LLMClient, get_llm_client
from castelino.agents.research.deep.models import (
    DeepResearchReport,
    ReflectionResult,
    SubFinding,
)
from castelino.config import get_settings

SYNTH_SYSTEM = """\
You are the Synthesizer. You receive findings (each answering a sub-question,
with citations) and the main research question. Write a single coherent report:
- exec_summary: a clear, well-structured explanation for the analyst that
  directly answers the main question, integrating the findings. This is the
  human-facing answer; make it genuinely explanatory, not a list.
- sources: the deduplicated union of all citations across findings.
- confidence: your overall confidence (0-1).
- caveats: important limitations.
Only use the supplied findings. Do not invent facts or sources.
"""

REFLECT_SYSTEM = """\
You are a research critic. Given the main question and the draft report,
decide whether the research SUFFICIENTLY answers the question. If not, list
the specific gaps and propose new, targeted sub-questions to fill them. Be
strict but not perfectionist — only flag gaps that materially affect the
answer.
"""


def _dedup_sources(findings):
    seen, out = set(), []
    for f in findings:
        for c in f.citations:
            key = (c.url or c.title).strip().lower()
            if key and key not in seen:
                seen.add(key)
                out.append(c)
    return out


class Synthesizer:
    def __init__(self, *, llm: LLMClient | None = None):
        self._llm = llm or get_llm_client()

    def _model(self) -> str:
        cfg = get_settings()
        return getattr(cfg.models, cfg.deep_research.reasoning_tier)

    def synthesize(self, *, reworded_query: str, findings: list[SubFinding]) -> DeepResearchReport:
        joined = "\n\n".join(
            f"[{f.sub_question_id}] (conf={f.confidence})\n{f.summary}\n"
            + "\n".join(f"  • {p}" for p in f.key_points)
            for f in findings
        ) or "(no findings)"
        report = self._llm.parse(
            model=self._model(),
            system=SYNTH_SYSTEM,
            user=f"Main question: {reworded_query}\n\nFindings:\n{joined}",
            schema=DeepResearchReport,
            max_tokens=2500,
        )
        # Attach findings + ensure deduped sources even if the LLM skipped some.
        return report.model_copy(update={
            "findings": findings,
            "sources": report.sources or _dedup_sources(findings),
        })

    def reflect(self, *, reworded_query: str, report: DeepResearchReport, round_num: int) -> ReflectionResult:
        return self._llm.parse(
            model=self._model(),
            system=REFLECT_SYSTEM,
            user=(
                f"Main question: {reworded_query}\n\n"
                f"Round {round_num} draft summary:\n{report.exec_summary}\n\n"
                f"Caveats: {report.caveats}\n\n"
                "Is this sufficient? If not, list gaps and new sub-questions."
            ),
            schema=ReflectionResult,
            max_tokens=1200,
        )
