from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from castelino.agents.base import LLMClient, get_llm_client
from castelino.agents.research.deep.chart_resolver import ChartResolver
from castelino.agents.research.deep.clarifier import ClarifierAgent
from castelino.agents.research.deep.lead import LeadAgent
from castelino.agents.research.deep.models import (
    ResearchRound,
    ResearchSession,
    ResearchStatus,
)
from castelino.agents.research.deep.sonar_client import (
    PerplexitySonarClient,
    SonarClient,
)
from castelino.agents.research.deep.store import ResearchStore
from castelino.agents.research.deep.sub_agent import SubAgent
from castelino.agents.research.deep.synthesizer import Synthesizer
from castelino.config import get_settings

log = logging.getLogger(__name__)


class DeepResearchOrchestrator:
    def __init__(
        self, *,
        llm: LLMClient | None = None,
        sonar: SonarClient | None = None,
        store: ResearchStore | None = None,
    ):
        self.llm = llm or get_llm_client()
        self.sonar = sonar or PerplexitySonarClient()
        self.store = store or ResearchStore()

    def _new_id(self) -> str:
        return uuid.uuid4().hex[:12]

    # ───────────────────────── start / clarify ─────────────────────────

    def start(self, query: str) -> ResearchSession:
        now = datetime.now(UTC)
        sess = ResearchSession(
            id=self._new_id(), original_query=query,
            created_at=now, updated_at=now,
        )
        clar = ClarifierAgent()(query=query)  # uses global llm client
        sess.reworded_query = clar.reworded_query
        sess.clarifying_questions = clar.clarifying_questions
        sess.status = ResearchStatus.AWAITING_ANSWERS
        sess.updated_at = datetime.now(UTC)
        self.store.save(sess)
        return sess

    # ───────────────────────── research fan-out ────────────────────────

    async def _research_subquestions(self, sub_qs, remaining_budget):
        """Fan out sub-agents under a concurrency semaphore. Caps at budget."""
        cfg = get_settings().deep_research
        to_run = sub_qs[: max(0, remaining_budget)]
        sem = asyncio.Semaphore(cfg.concurrency)
        sub_agent = SubAgent(llm=self.llm, sonar=self.sonar)

        async def _one(sub_q):
            async with sem:
                # SubAgent.run is sync (Sonar SDK + LLM are sync) — offload.
                return await asyncio.to_thread(sub_agent.run, sub_q)

        return list(await asyncio.gather(*[_one(q) for q in to_run]))

    def run_first_round(self, session_id: str, *, answers: dict) -> ResearchSession:
        sess = self.store.load(session_id)
        if sess is None:
            raise ValueError(f"unknown session {session_id}")
        sess.answers = answers or {}
        sess.status = ResearchStatus.RESEARCHING
        self.store.save(sess)

        cfg = get_settings().deep_research
        lead = LeadAgent()
        sub_qs = lead.decompose(
            reworded_query=sess.reworded_query,
            answers=sess.answers, round_num=1,
        )
        remaining = cfg.max_sonar_calls - sess.sonar_calls_used
        findings = asyncio.run(self._research_subquestions(sub_qs, remaining))
        sess.sonar_calls_used += len(findings)
        sess.rounds.append(ResearchRound(round=1, sub_questions=sub_qs, findings=findings))
        if findings and all(f.error for f in findings):
            sess.status = ResearchStatus.FAILED
            sess.error = "all sub-agents failed to gather research (Sonar unavailable?)"
        else:
            sess.status = ResearchStatus.SYNTHESIZING
        sess.updated_at = datetime.now(UTC)
        self.store.save(sess)
        return sess

    # ───────────────────── synthesize + reflection loop ────────────────

    def finish(self, session_id: str) -> ResearchSession:
        sess = self.store.load(session_id)
        if sess is None:
            raise ValueError(f"unknown session {session_id}")
        cfg = get_settings().deep_research
        syn = Synthesizer(llm=self.llm)

        all_findings = [f for r in sess.rounds for f in r.findings]
        report = syn.synthesize(reworded_query=sess.reworded_query, findings=all_findings)

        round_num = len(sess.rounds)
        while round_num < cfg.max_rounds and sess.sonar_calls_used < cfg.max_sonar_calls:
            refl = syn.reflect(
                reworded_query=sess.reworded_query, report=report, round_num=round_num,
            )
            sess.rounds[-1].reflection = refl
            self.store.save(sess)
            if refl.is_sufficient or not refl.new_sub_questions:
                break
            # bounded extra round over the gap sub-questions
            round_num += 1
            gap_qs = [q.model_copy(update={"round": round_num}) for q in refl.new_sub_questions]
            remaining = cfg.max_sonar_calls - sess.sonar_calls_used
            findings = asyncio.run(self._research_subquestions(gap_qs, remaining))
            sess.sonar_calls_used += len(findings)
            sess.rounds.append(ResearchRound(round=round_num, sub_questions=gap_qs, findings=findings))
            self.store.save(sess)
            all_findings = [f for r in sess.rounds for f in r.findings]
            report = syn.synthesize(reworded_query=sess.reworded_query, findings=all_findings)

        # note any unfilled gaps from the last reflection
        last_refl = sess.rounds[-1].reflection
        if last_refl and not last_refl.is_sufficient:
            report = report.model_copy(update={"gaps_remaining": last_refl.gaps})

        # Resolve thesis charts from the synthesizer's specs (deterministic,
        # OpenBB-backed). Never fails the report — bad charts are dropped.
        try:
            resolved = ChartResolver().resolve_all(report.chart_specs)
        except Exception as e:  # defensive: resolver already swallows per-chart
            log.warning("chart resolution failed wholesale: %s", e)
            resolved = []
        report = report.model_copy(update={"charts": resolved})

        sess.report = report
        sess.status = ResearchStatus.COMPLETE
        sess.updated_at = datetime.now(UTC)
        self.store.save(sess)
        return sess

    # ───────────────────────── convenience entry ───────────────────────

    def run_sync(self, query: str, *, answers: dict | None = None) -> ResearchSession:
        """Full pipeline without an interactive pause (CLI / --no-clarify)."""
        sess = self.start(query)
        sess = self.run_first_round(sess.id, answers=answers or {})
        if sess.status == ResearchStatus.FAILED:
            return sess
        return self.finish(sess.id)
