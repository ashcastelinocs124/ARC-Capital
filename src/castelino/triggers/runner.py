"""Trigger runner — `castelino watch`.

Polling loop:
1. Read `data/system_state.json`. If `trading_enabled = False`, run dry but
   skip writing to portfolio.json (would-have-trades only).
2. Pull calendar events; if any high-impact within poll window → fire.
3. Pull RSS, classify with significance batch; if any score ≥ threshold → fire.
4. If neither and last_fire > 24h ago → cron fallback fires with sig=0.3.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from castelino.config import get_settings
from castelino.execution.portfolio import Portfolio
from castelino.forecast.regime_sectors import merge_forecast_into_state_kwargs
from castelino.memory import io as memio
from castelino.memory.io import WriterIdentity
from castelino.memory.schemas import TriggerRecord, TriggerSource
from castelino.orchestrator.graph import build_graph
from castelino.orchestrator.state import FundState
from castelino.triggers import calendar as calmod
from castelino.triggers.news import NewsHeadline, fetch_recent
from castelino.triggers.significance import score_batch

log = logging.getLogger(__name__)


def _system_state_path() -> Path:
    return get_settings().resolved_paths.data / "system_state.json"


def _load_system_state() -> dict:
    p = _system_state_path()
    if not p.exists():
        state = {
            "trading_enabled": True,
            "last_fire_utc": None,
            "fire_count": 0,
        }
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(state, indent=2))
        return state
    return json.loads(p.read_text())


def _save_system_state(state: dict) -> None:
    _system_state_path().write_text(json.dumps(state, indent=2, default=str))


# ─────────────────────────── trigger sources ───────────────────────────


def _trigger_from_calendar(events: list[calmod.CalendarEvent]) -> TriggerRecord | None:
    if not events:
        return None
    e = max(events, key=lambda x: (x.impact == "high", x.timestamp))
    significance = 0.85 if e.impact == "high" else 0.5 if e.impact == "medium" else 0.3
    return TriggerRecord(
        source=TriggerSource.CALENDAR,
        headline=f"{e.region} {e.name} due {e.timestamp.isoformat()}",
        significance=significance,
        asset_classes_affected=e.asset_classes_affected,
        raw_event_data={"region": e.region, "impact": e.impact, "timestamp": e.timestamp.isoformat()},
        one_sentence_reason=f"{e.impact} impact {e.name} ({e.region}).",
    )


def _trigger_from_news(headlines: list[NewsHeadline]) -> TriggerRecord | None:
    """Score the batch; fire if any meets the news threshold."""
    if not headlines:
        return None
    cfg = get_settings()
    scores = score_batch(headlines[:30])
    if not scores:
        return None
    by_id = {h.id: h for h in headlines}
    top = max(scores, key=lambda s: s.materiality)
    if top.materiality < cfg.triggers.news_significance_min:
        # Log near-fires to ST (significance < threshold but ≥ log_min)
        for s in scores:
            if s.materiality >= cfg.triggers.news_log_min:
                rec = TriggerRecord(
                    source=TriggerSource.NEWS,
                    headline=s.title,
                    significance=s.materiality,
                    asset_classes_affected=s.asset_classes_affected,
                    raw_event_data={"headline_id": s.headline_id, "logged_only": True},
                    one_sentence_reason=s.one_sentence_reason,
                )
                memio.append_short_term(rec, WriterIdentity.TRIGGER_RUNNER)
        return None
    h = by_id.get(top.headline_id)
    return TriggerRecord(
        source=TriggerSource.NEWS,
        headline=top.title,
        significance=top.materiality,
        asset_classes_affected=top.asset_classes_affected,
        raw_event_data={"headline_id": top.headline_id, "link": (h.link if h else "")},
        one_sentence_reason=top.one_sentence_reason,
    )


def _trigger_cron_fallback(last_fire: datetime | None) -> TriggerRecord | None:
    cfg = get_settings()
    if last_fire is None:
        delta = timedelta(days=999)
    else:
        delta = datetime.now(UTC) - last_fire
    if delta < timedelta(hours=cfg.triggers.cron_fallback_hours):
        return None
    return TriggerRecord(
        source=TriggerSource.CRON_FALLBACK,
        headline="No-news 24h check-in",
        significance=0.3,
        asset_classes_affected=[],
        one_sentence_reason="No-news cron fallback fired.",
    )


# ─────────────────────────── public entry points ───────────────────────────


def fire_pipeline(trigger: TriggerRecord, recent_headlines: list[str]) -> dict:
    """Run one pipeline pass. Returns the final state."""
    state_data = _load_system_state()
    memio.append_short_term(trigger, WriterIdentity.TRIGGER_RUNNER)

    if not state_data.get("trading_enabled", True):
        log.warning("trading_enabled=False; pipeline runs but no portfolio writes.")

    pf = Portfolio.load()
    state = FundState(
        trigger=trigger,
        recent_headlines=recent_headlines,
        portfolio=pf,
        **merge_forecast_into_state_kwargs(),
    )
    graph = build_graph()
    result = graph.invoke(state)

    state_data["last_fire_utc"] = datetime.now(UTC).isoformat()
    state_data["fire_count"] = state_data.get("fire_count", 0) + 1
    _save_system_state(state_data)
    return result


def watch_loop(poll_minutes: int = 15, once: bool = False) -> None:
    """Continuous polling loop. Each pass: calendar → news → cron."""
    log.info("watcher started (poll=%dmin, once=%s)", poll_minutes, once)
    while True:
        try:
            tick()
        except Exception as e:
            log.exception("watcher tick failed: %s", e)
        if once:
            break
        time.sleep(poll_minutes * 60)


def tick() -> str | None:
    """One polling cycle. Returns the trigger source that fired (or None)."""
    state = _load_system_state()
    last_fire = (
        datetime.fromisoformat(state["last_fire_utc"])
        if state.get("last_fire_utc")
        else None
    )

    # 1. Calendar
    cal_events = calmod.events_due()
    trg = _trigger_from_calendar(cal_events)
    if trg:
        log.info("calendar trigger: %s", trg.headline)
        fire_pipeline(trg, recent_headlines=[trg.headline])
        return "calendar"

    # 2. News
    news = fetch_recent(max_per_feed=20)
    trg = _trigger_from_news(news)
    if trg:
        log.info("news trigger sig=%.2f: %s", trg.significance, trg.headline)
        fire_pipeline(trg, recent_headlines=[h.title for h in news[:20]])
        return "news"

    # 3. Cron fallback
    trg = _trigger_cron_fallback(last_fire)
    if trg:
        log.info("cron fallback fired (last fire %s)", last_fire)
        fire_pipeline(trg, recent_headlines=[h.title for h in news[:20]])
        return "cron"

    log.info("tick: no trigger.")
    return None


def replay_historical(days: int = 30) -> None:
    """Backfill from cached news + calendar over `days`. Used by `castelino replay`."""
    log.info("replay_historical: %d days requested", days)
    # v1: walk the headline cache and fire each significant one.
    headlines = fetch_recent(max_per_feed=50, dedupe=False)
    headlines = [h for h in headlines if h.published > datetime.now(UTC) - timedelta(days=days)]
    if not headlines:
        log.info("no headlines to replay.")
        return
    trg = _trigger_from_news(headlines)
    if trg is None:
        log.info("no replay-worthy headlines.")
        return
    log.info("firing replay pipeline on %s", trg.headline)
    fire_pipeline(trg, recent_headlines=[h.title for h in headlines[:30]])


def set_trading_enabled(enabled: bool) -> None:
    state = _load_system_state()
    state["trading_enabled"] = bool(enabled)
    _save_system_state(state)
