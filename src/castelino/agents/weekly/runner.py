"""Weekly Deep Dive runner: Lead → desks (parallel, shared board) → Editor grill (≤N rounds) →
write → guard (≤1 retry) → charts → data/deep/<week>.json, written last as the done-marker."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from castelino.agents.update.fsio import acquire_lock, atomic_write_text, release_lock
from castelino.agents.update.guard import count_figures
from castelino.agents.update.models import Fact
from castelino.agents.weekly.board import Board
from castelino.agents.weekly.editor import answers_brief, desk_brief
from castelino.agents.weekly.guard import check_report, report_texts
from castelino.agents.weekly.inputs import due_week, load_week, week_markdown
from castelino.agents.weekly.models import AgentRun, GrillExchange, RunCounts, WeeklyRecord

log = logging.getLogger(__name__)
PREFIXES = "ABCD"
_STALE_LOCK_SECONDS = 2 * 60 * 60
ET = ZoneInfo("America/New_York")


def _today_et() -> date:
    return datetime.now(ET).date()


class WeeklyRunner:
    def __init__(
        self,
        *,
        deep_dir: Path,
        updates_dir: Path,
        memory_md_fn: Callable[[], str],
        plan_fn,
        session_fn,
        editor_fn,
        chart_fn,
        scorecard_fn,
        regime_fn,
        min_notes: int,
        max_grill_rounds: int,
        max_guard_retries: int,
        models: dict[str, str],
        today_fn: Callable[[], date] = _today_et,
    ):
        self.deep_dir, self.updates_dir = Path(deep_dir), Path(updates_dir)
        self.memory_md_fn, self.plan_fn, self.session_fn = memory_md_fn, plan_fn, session_fn
        self.editor_fn, self.chart_fn = editor_fn, chart_fn
        self.scorecard_fn, self.regime_fn, self.today_fn = scorecard_fn, regime_fn, today_fn
        self.min_notes, self.max_grill_rounds = min_notes, max_grill_rounds
        self.max_guard_retries, self.models = max_guard_retries, models
        self._week = ""
        self._gaps: list[str] = []

    def _set(self, stage: str, error: str | None = None) -> None:
        atomic_write_text(
            self.deep_dir / "status.json",
            json.dumps({"stage": stage, "week": self._week, "error": error}),
        )

    def run_if_due(self) -> str:
        week = due_week(self.today_fn(), self.deep_dir)
        return "skipped" if week is None else self.run_week(week)

    def run_week(self, week: str) -> str:
        self._week = week
        if not acquire_lock(self.deep_dir, _STALE_LOCK_SECONDS):
            return "locked"
        try:
            self._run(week)
            self._set("done")
            return "done"
        except Exception as exc:  # noqa: BLE001 — a failed run leaves no record, only status
            log.exception("weekly deep dive failed")
            self._set("failed", error=str(exc)[:300])
            return "failed"
        finally:
            release_lock(self.deep_dir)

    def _gather(self, jobs: dict[str, Callable]) -> dict:
        async def one(name, fn):
            try:
                return await asyncio.to_thread(fn)
            except Exception as exc:  # noqa: BLE001 — one desk must not sink the report
                log.warning("%s failed", name, exc_info=True)
                self._gaps.append(f"{name} agent failed: {str(exc)[:120]}")
                return None

        async def main():
            return await asyncio.gather(*(one(n, f) for n, f in jobs.items()))

        results = asyncio.run(main())
        return {n: r for n, r in zip(jobs, results, strict=True) if r is not None}

    @staticmethod
    def _facts(sessions: dict) -> list[Fact]:
        by: dict[str, Fact] = {}
        for s in sessions.values():
            for f in s.toolbox.facts:
                by.setdefault(f.id, f)
        return list(by.values())

    def _run(self, week: str) -> None:
        self._gaps = []
        self._set("planning")
        inp = load_week(self.updates_dir, week, self.min_notes)
        self._gaps += inp.gaps
        week_md = week_markdown(inp)
        plan = self.plan_fn(week, week_md, self.memory_md_fn())

        self._set("researching")
        board = Board()
        sessions = {
            spec.name: self.session_fn(spec, PREFIXES[i], board, inp.end)
            for i, spec in enumerate(plan.agents[: len(PREFIXES)])
        }
        brief = f"This week's Morning Notes, for context:\n\n{week_md}"
        runs: dict[str, AgentRun] = self._gather(
            {n: (lambda s=s: s.run(brief)) for n, s in sessions.items()}
        )
        if len(runs) < 2:
            raise RuntimeError(f"only {len(runs)} desk(s) returned findings; need 2")
        live = {n: sessions[n] for n in runs}

        self._set("grilling")
        editor = self.editor_fn()
        grill_log: list[GrillExchange] = []
        rounds = 0
        try:
            grill = editor.open(desk_brief(week, plan, list(runs.values()), board.posts))
            while not grill.done and grill.questions and rounds < self.max_grill_rounds:
                qs = [q for q in grill.questions if q.agent in live]
                if not qs:
                    break
                rounds += 1
                by_agent: dict[str, list] = {}
                for q in qs:
                    by_agent.setdefault(q.agent, []).append(q)
                answered = self._gather(
                    {
                        a: (lambda a=a, g=g: [live[a].answer(q) for q in g])
                        for a, g in by_agent.items()
                    }
                )
                answers = [
                    x.model_copy(update={"round": rounds}) for g in answered.values() for x in g
                ]
                grill_log += answers
                facts_now = {f.id: f for f in self._facts(live)}
                last = rounds >= self.max_grill_rounds
                grill = editor.followup(answers_brief(answers, facts_now), last=last)
        except Exception as exc:  # noqa: BLE001 — a broken grill round goes straight to writing
            log.warning("grill stopped", exc_info=True)
            self._gaps.append(f"grill stopped early: {str(exc)[:120]}")

        facts = self._facts(live)
        errors: list[str] | None = None
        for _ in range(self.max_guard_retries + 1):
            self._set("writing")
            report = editor.write(errors)
            self._set("guarding")
            errors = check_report(report, facts)
            if not errors:
                break
        if errors:
            raise RuntimeError(f"guard failed: {errors}")

        self._set("charting")
        exhibits = self.chart_fn(report, facts, self.deep_dir / "charts" / week)
        counts = RunCounts(
            notes=len(inp.records),
            agents=len(runs),
            data_pulls=sum(r.tool_calls for r in runs.values()),
            board_posts=len(board.posts),
            grill_rounds=rounds,
            figures_checked=count_figures(report_texts(report)),
            exhibits=len(exhibits),
        )
        atomic_write_text(
            self.deep_dir / "raw" / f"{week}.json",
            json.dumps([f.model_dump() for f in facts], indent=1),
        )
        record = WeeklyRecord(
            week=week,
            start=inp.start.isoformat(),
            end=inp.end.isoformat(),
            generated_at=datetime.now().isoformat(timespec="seconds"),
            plan=plan,
            findings=[f for r in runs.values() for f in r.findings],
            facts=facts,
            board=list(board.posts),
            grill_log=grill_log,
            report=report,
            exhibits=exhibits,
            scorecard=self.scorecard_fn(inp.end),
            regime=self.regime_fn(),
            counts=counts,
            data_gaps=self._gaps,
            models=self.models,
        )
        # written last: its existence is what marks the week done
        atomic_write_text(self.deep_dir / f"{week}.json", record.model_dump_json(indent=2))


# ── production wiring ──────────────────────────────────────────────────────


def build_default_runner() -> WeeklyRunner:
    from openai import OpenAI

    from castelino.agents.update.registry import ModelRegistry
    from castelino.agents.weekly import charts, lead, scorecard
    from castelino.agents.weekly.editor import AnthropicEditorClient, DeepEditor
    from castelino.agents.weekly.subagent import AgentSession
    from castelino.agents.weekly.tools import ToolBox
    from castelino.config import get_settings

    cfg = get_settings()
    dd, ua = cfg.deep_dive, cfg.update_agent
    client = OpenAI(api_key=cfg.openai_api_key, timeout=180)

    def session_fn(spec, prefix, board, end):
        box = ToolBox(
            agent=spec.name,
            prefix=prefix,
            allowed=list(spec.tools),
            board=board,
            end=end,
            max_calls=dd.max_tool_calls,
            search_model=dd.search_model,
        )
        return AgentSession(
            spec,
            box,
            client=client,
            model=dd.agent_model,
            start=end - timedelta(days=4),
            end=end,
            answer_calls=dd.max_answer_tool_calls,
            cap=dd.max_findings_per_agent,
        )

    def editor_fn():
        client = AnthropicEditorClient(dd.editor_model, dd.editor_effort, dd.editor_max_tokens)
        return DeepEditor(client)

    memory = cfg.root / ua.data_dir / "memory" / "MEMORY.md"
    registry = ModelRegistry(cfg.root / ua.data_dir / "models")
    return WeeklyRunner(
        deep_dir=cfg.root / dd.data_dir,
        updates_dir=cfg.root / ua.updates_dir,
        memory_md_fn=lambda: memory.read_text() if memory.exists() else "",
        plan_fn=lead.plan,
        session_fn=session_fn,
        editor_fn=editor_fn,
        chart_fn=charts.make_weekly_exhibits,
        scorecard_fn=scorecard.build_scorecard,
        regime_fn=lambda: scorecard.regime_read(registry.current()),
        min_notes=dd.min_notes,
        max_grill_rounds=dd.max_grill_rounds,
        max_guard_retries=dd.max_guard_retries,
        models={"lead": dd.lead_model, "agents": dd.agent_model, "editor": dd.editor_model},
    )
