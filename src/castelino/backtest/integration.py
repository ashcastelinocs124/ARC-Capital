"""Phase-3 integration — production score / trigger callables for the runner.

The skeleton runner (`backtest.runner.BacktestRunner`) injects callables for
scoring, trigger-detection, and fire. This module supplies the *real* ones
that wrap the production trigger plumbing:

    historical_to_news_headline → adapter
    real_score_fn               → score_batch + apply_readiness + conv.append
    real_trigger_fn             → priority order: black_swan → news → conviction → cron

The pipeline-fire callable (Phase 5) wraps the LangGraph DAG with a
backtest-portfolio thread; it lives in `backtest.execution`.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Optional

from castelino.backtest.news_archive import HistoricalHeadline
from castelino.backtest.runner import HeadlineScore as BTScore
from castelino.backtest.runner import TriggerCandidate
from castelino.triggers import conviction as conv
from castelino.triggers.news import NewsHeadline
from castelino.triggers.readiness import apply_readiness
from castelino.triggers.significance import HeadlineScore as ProdScore
from castelino.triggers.significance import score_batch

log = logging.getLogger(__name__)


# ─────────────────────── adapters ────────────────────────────────────────


def historical_to_news_headline(h: HistoricalHeadline) -> NewsHeadline:
    """Map archive row → production NewsHeadline shape."""
    h_id = hashlib.sha256(f"{h.url}|{h.headline}".encode()).hexdigest()[:16]
    return NewsHeadline(
        id=h_id,
        title=h.headline,
        summary=h.abstract,
        link=h.url,
        source=h.source,
        published=h.date if h.date.tzinfo else h.date.replace(tzinfo=UTC),
    )


def _prod_to_bt_score(s: ProdScore, src: str) -> BTScore:
    return BTScore(
        headline=s.title, materiality=s.materiality,
        source=src, abstract=s.one_sentence_reason,
    )


# ─────────────────────── score / readiness / conviction ──────────────────


def real_score_fn(headlines: list[HistoricalHeadline]) -> list[BTScore]:
    """Production scoring path: score_batch → apply_readiness → conv.append.

    Uses gpt-4o-mini in backtest mode (model resolved at call time via
    `agents.base._resolve_model_id`). Conviction ledger is mutated in
    place — callers that want pristine state should clear it between
    runs. Empty input → empty output (no LLM call).
    """
    if not headlines:
        return []

    news_inputs = [historical_to_news_headline(h) for h in headlines]
    src_by_id = {n.id: h.source for n, h in zip(news_inputs, headlines, strict=True)}

    raw_scores: list[ProdScore] = score_batch(news_inputs)
    matured: list[ProdScore] = apply_readiness(raw_scores)

    # Append to conviction ledger so the conviction-trigger path can fire
    # in subsequent ticks. Use the score's own materiality / direction.
    for s in matured:
        try:
            conv.append(s)
        except Exception as e:
            log.debug("conviction append failed for %s: %s", s.headline_id, e)

    return [_prod_to_bt_score(s, src_by_id.get(s.headline_id, "unknown"))
            for s in matured]


# ─────────────────────── trigger router ──────────────────────────────────


# Priority: black_swan ≥ 0.9  >  high-materiality news ≥ 0.7
#          >  accumulated conviction (cooldown'd)  >  cron fallback
#
# Calendar / regime-shift paths are intentionally deferred — they require a
# historical FRED-releases lookup and a rolling-trained regime nowcaster
# (Phase 4) that aren't in place yet for the backtest. They become live once
# Phase 4 lands `rolling_train.py`.

NEWS_FIRE_THRESHOLD = 0.7
BLACK_SWAN_THRESHOLD = 0.9


_LAST_FIRE: dict[str, datetime] = {}


def real_trigger_fn(d: date, scores: list[BTScore]) -> Optional[TriggerCandidate]:
    """Apply the same priority order as `triggers.runner` in live mode.

    `d` is the simulated business-day end. `_LAST_FIRE` enforces conviction
    cooldown across ticks within a run — clear it via `reset_state()` between
    independent backtest runs.
    """
    # 1. Black swan
    for s in scores:
        if s.materiality >= BLACK_SWAN_THRESHOLD:
            _LAST_FIRE["any"] = datetime.combine(d, datetime.max.time(), UTC)
            return TriggerCandidate(
                date=d, path="black_swan",
                headline=s.headline, materiality=s.materiality,
            )

    # 2. High-materiality news (no enrichment in backtest — Polymarket / X
    # are "today" data, not historical).
    top_news = max(scores, key=lambda x: x.materiality, default=None)
    if top_news is not None and top_news.materiality >= NEWS_FIRE_THRESHOLD:
        _LAST_FIRE["any"] = datetime.combine(d, datetime.max.time(), UTC)
        return TriggerCandidate(
            date=d, path="news",
            headline=top_news.headline, materiality=top_news.materiality,
        )

    # 3. Accumulated conviction (cooldown enforced via _LAST_FIRE)
    last = _LAST_FIRE.get("any")
    try:
        from castelino.config import get_settings
        cfg = get_settings().conviction
        if last is not None:
            elapsed_h = (
                datetime.combine(d, datetime.max.time(), UTC) - last
            ).total_seconds() / 3600
            if elapsed_h < cfg.cooldown_hours:
                return None
        result = conv.check_fire()
        if result.should_fire:
            _LAST_FIRE["any"] = datetime.combine(d, datetime.max.time(), UTC)
            return TriggerCandidate(
                date=d, path="conviction",
                headline=f"Accumulated conviction: {result.reason}",
                materiality=0.7,
            )
    except Exception as e:
        log.debug("conviction check failed: %s", e)

    # 4. Cron fallback — fire after `cron_fallback_hours` of silence
    try:
        from castelino.config import get_settings
        cfg = get_settings().triggers
        if last is None:
            last_age = timedelta(days=999)
        else:
            last_age = datetime.combine(d, datetime.max.time(), UTC) - last
        if last_age >= timedelta(hours=cfg.cron_fallback_hours):
            _LAST_FIRE["any"] = datetime.combine(d, datetime.max.time(), UTC)
            return TriggerCandidate(
                date=d, path="cron",
                headline="No-news 24h check-in", materiality=0.3,
            )
    except Exception as e:
        log.debug("cron check failed: %s", e)

    return None


def reset_state() -> None:
    """Reset cross-tick state. Call between independent backtest runs."""
    _LAST_FIRE.clear()
