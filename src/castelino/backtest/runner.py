"""Backtest replay loop — walks business days and routes through the pipeline.

Phase-2 skeleton: the loop, business-day walk, env-var lifecycle, and
trigger-candidate detection are real. The pipeline-fire step is injected
so Phase 3 can wire the real LangGraph DAG without modifying the loop.

Public surface:
    BacktestRunner(score_fn, trigger_fn, fire_fn).run(start, end, run_id)
        -> BacktestSummary

Defaults provided here are stubs that print "would fire pipeline" so the
skeleton is verifiably-correct in isolation.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Optional

from castelino.backtest import BACKTEST_AS_OF_ENV
from castelino.backtest.news_archive import HistoricalHeadline, headlines_for
from castelino.config import get_settings

log = logging.getLogger(__name__)


# ─────────────────────────── data classes ────────────────────────────────


@dataclass(frozen=True)
class HeadlineScore:
    """Lightweight headline-with-score record used inside the loop.

    Mirrors the relevant subset of `castelino.triggers.significance.HeadlineScore`
    so Phase 2 can run without importing that module's heavier deps."""
    headline: str
    materiality: float
    source: str
    abstract: str = ""


@dataclass(frozen=True)
class TriggerCandidate:
    """A would-be pipeline trigger. Phase 2 records these without firing."""
    date: date
    path: str             # one of: "black_swan", "calendar", "regime", "conviction", "cron"
    headline: str
    materiality: float


@dataclass
class DailyRecord:
    date: date
    n_headlines: int
    n_scored: int
    trigger: Optional[TriggerCandidate]
    pipeline_fired: bool


@dataclass
class BacktestSummary:
    run_id: str
    start: date
    end: date
    business_days: int
    total_headlines: int
    triggers_by_path: dict[str, int] = field(default_factory=dict)
    pipeline_fires: int = 0
    daily_records: list[DailyRecord] = field(default_factory=list)


# ─────────────────────────── default stubs ───────────────────────────────


def stub_score(headlines: list[HistoricalHeadline]) -> list[HeadlineScore]:
    """Phase-2 stub: deterministic per-headline score from a tiny keyword rule.

    Real scorer (`triggers.significance.score_batch`) is wired in Phase 3.
    """
    out: list[HeadlineScore] = []
    for h in headlines:
        text = (h.headline + " " + h.abstract).lower()
        m = 0.3
        if any(k in text for k in ("fed", "fomc", "rate", "cpi")):
            m = 0.75
        if any(k in text for k in ("crash", "panic", "war", "default")):
            m = 0.92
        if "tariff" in text or "trump" in text:
            m = max(m, 0.72)
        out.append(HeadlineScore(
            headline=h.headline,
            materiality=m,
            source=h.source,
            abstract=h.abstract,
        ))
    return out


def stub_trigger(d: date, scores: list[HeadlineScore]) -> TriggerCandidate | None:
    """Phase-2 stub: black-swan only (≥0.9). Calendar / regime / conviction
    paths land in Phase 3 once the real triggers are wired."""
    for s in scores:
        if s.materiality >= 0.9:
            return TriggerCandidate(
                date=d, path="black_swan",
                headline=s.headline, materiality=s.materiality,
            )
    # Conviction-style stand-in: any single ≥0.7 in the batch
    top = max(scores, key=lambda x: x.materiality, default=None)
    if top is not None and top.materiality >= 0.7:
        return TriggerCandidate(
            date=d, path="news",
            headline=top.headline, materiality=top.materiality,
        )
    return None


def stub_fire(d: date, trigger: TriggerCandidate, scores: list[HeadlineScore]) -> bool:
    """Phase-2 stub: log "would fire pipeline" and return True. Real LangGraph
    invocation lands in Phase 3."""
    log.info(
        "[backtest %s] would fire pipeline (path=%s, mat=%.2f) headline=%r",
        d, trigger.path, trigger.materiality, trigger.headline[:80],
    )
    return True


# ───────────────────────── business-day walk ─────────────────────────────


def business_days(start: date, end: date) -> list[date]:
    """Inclusive business-day range. Skips Sat/Sun. Holidays handled live."""
    if start > end:
        return []
    out: list[date] = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


# ─────────────────────────── runner ──────────────────────────────────────


ScoreFn = Callable[[list[HistoricalHeadline]], list[HeadlineScore]]
TriggerFn = Callable[[date, list[HeadlineScore]], Optional[TriggerCandidate]]
FireFn = Callable[[date, TriggerCandidate, list[HeadlineScore]], bool]
EndOfDayFn = Callable[[date], None]


class BacktestRunner:
    """Walks days, routes each through (score → trigger-detect → fire?).

    All side-effecting pipeline work is injected via callables so Phase 2
    is testable in isolation and Phase 3 can hot-swap the wiring.

    `end_of_day_fn`, when supplied, is invoked at the end of every business
    day after any pipeline-fire — used by Phase 5 to run the daily mark
    loop and persist a portfolio-NAV snapshot.
    """

    def __init__(
        self,
        *,
        score_fn: ScoreFn = stub_score,
        trigger_fn: TriggerFn = stub_trigger,
        fire_fn: FireFn = stub_fire,
        end_of_day_fn: EndOfDayFn | None = None,
        headlines_loader: Callable[[date], list[HistoricalHeadline]] = headlines_for,
    ) -> None:
        self.score_fn = score_fn
        self.trigger_fn = trigger_fn
        self.fire_fn = fire_fn
        self.end_of_day_fn = end_of_day_fn
        self.headlines_loader = headlines_loader

    def run(self, *, start: date, end: date, run_id: str) -> BacktestSummary:
        days = business_days(start, end)
        summary = BacktestSummary(
            run_id=run_id, start=start, end=end,
            business_days=len(days), total_headlines=0,
        )
        for d in days:
            self._tick(d, summary)
        self._write_summary(summary)
        return summary

    def _tick(self, d: date, summary: BacktestSummary) -> None:
        os.environ[BACKTEST_AS_OF_ENV] = d.isoformat()
        try:
            headlines = self.headlines_loader(d)
            scores = self.score_fn(headlines)
            trigger = self.trigger_fn(d, scores)
            fired = False
            if trigger is not None:
                fired = bool(self.fire_fn(d, trigger, scores))
                summary.triggers_by_path[trigger.path] = (
                    summary.triggers_by_path.get(trigger.path, 0) + 1
                )
                if fired:
                    summary.pipeline_fires += 1
            summary.total_headlines += len(headlines)
            summary.daily_records.append(DailyRecord(
                date=d, n_headlines=len(headlines), n_scored=len(scores),
                trigger=trigger, pipeline_fired=fired,
            ))
            if self.end_of_day_fn is not None:
                self.end_of_day_fn(d)
        finally:
            os.environ.pop(BACKTEST_AS_OF_ENV, None)

    def _write_summary(self, summary: BacktestSummary) -> None:
        cfg = get_settings()
        runs_dir = Path(cfg.root) / cfg.backtest.runs_dir / summary.run_id
        runs_dir.mkdir(parents=True, exist_ok=True)
        path = runs_dir / "summary.json"
        path.write_text(json.dumps({
            "run_id": summary.run_id,
            "start": summary.start.isoformat(),
            "end": summary.end.isoformat(),
            "business_days": summary.business_days,
            "total_headlines": summary.total_headlines,
            "triggers_by_path": summary.triggers_by_path,
            "pipeline_fires": summary.pipeline_fires,
        }, indent=2))
        log.info("wrote skeleton summary → %s", path)
