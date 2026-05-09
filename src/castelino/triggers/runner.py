"""Trigger runner — `castelino watch`.

Polling loop with four trigger paths (priority order):
1. Black swan — single headline materiality ≥ 0.9 → instant fire.
2. Regime shift — XGBoost nowcaster label flips → fire.
3. Accumulated conviction — directional decayed sums cross threshold → fire.
4. Cron fallback — nothing fired for 24h → fire with low significance.

All headlines ≥ 0.3 are appended to the conviction ledger every tick,
regardless of whether the pipeline fires.
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
from castelino.triggers import conviction as conv
from castelino.triggers.news import NewsHeadline, enrich_significant_headlines, fetch_recent, fetch_x_sentiment
from castelino.triggers.polymarket import fetch_related_contracts
from castelino.triggers.readiness import apply_readiness
from castelino.triggers.significance import HeadlineScore, rescore_borderlines, score_batch

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


def _check_black_swan(scores: list[HeadlineScore]) -> TriggerRecord | None:
    """Path 1: any single headline ≥ black_swan_min fires instantly."""
    cfg = get_settings().conviction
    for s in scores:
        if s.materiality >= cfg.black_swan_min:
            return TriggerRecord(
                source=TriggerSource.NEWS,
                headline=s.title,
                significance=s.materiality,
                asset_classes_affected=s.asset_classes_affected,
                raw_event_data={
                    "trigger_path": "black_swan",
                    "headline_id": s.headline_id,
                    "growth_direction": s.growth_direction,
                    "inflation_direction": s.inflation_direction,
                },
                one_sentence_reason=s.one_sentence_reason,
            )
    return None


def _check_regime_shift(state: dict) -> TriggerRecord | None:
    """Path 2: regime nowcaster label changed since last fire.

    Always persists the current regime key so the *next* tick can detect a shift.
    """
    try:
        forecast_kwargs = merge_forecast_into_state_kwargs()
    except Exception as e:
        log.debug("regime forecast unavailable: %s", e)
        return None

    current_key = forecast_kwargs.get("macro_regime_key", "")
    if not current_key:
        return None

    last_regime = state.get("last_regime_key", "")
    _save_regime_key(current_key)

    if last_regime and current_key != last_regime:
        return TriggerRecord(
            source=TriggerSource.REGIME_SHIFT,
            headline=f"Regime shift: {last_regime} → {current_key}",
            significance=0.80,
            asset_classes_affected=[],
            raw_event_data={
                "trigger_path": "regime_shift",
                "old_regime": last_regime,
                "new_regime": current_key,
                "growth_prob_up": forecast_kwargs.get("growth_prob_up"),
                "inflation_prob_up": forecast_kwargs.get("inflation_prob_up"),
            },
            one_sentence_reason=f"Regime shifted from {last_regime} to {current_key}.",
        )
    return None


def _check_conviction(last_fire: datetime | None) -> tuple[TriggerRecord | None, list[str]]:
    """Path 3: accumulated directional conviction crosses threshold.

    Returns (trigger_or_None, contributing_headlines).
    Subject to cooldown — skipped if last fire was too recent.
    """
    cfg = get_settings().conviction
    if last_fire:
        cooldown_elapsed = (datetime.now(UTC) - last_fire).total_seconds() / 3600
        if cooldown_elapsed < cfg.cooldown_hours:
            return None, []

    result = conv.check_fire()
    if not result.should_fire:
        log.debug("conviction check: %s", result.reason)
        return None, []

    snap = result.snapshot
    trg = TriggerRecord(
        source=TriggerSource.CONVICTION,
        headline=f"Accumulated conviction: {result.reason}",
        significance=0.70,
        asset_classes_affected=[],
        raw_event_data={
            "trigger_path": "conviction",
            "growth_bullish": round(snap.growth_bullish, 3),
            "growth_bearish": round(snap.growth_bearish, 3),
            "inflation_bullish": round(snap.inflation_bullish, 3),
            "inflation_bearish": round(snap.inflation_bearish, 3),
            "dominant_dimension": snap.dominant_dimension,
            "contributing_headlines": result.contributing_headlines[:10],
        },
        one_sentence_reason=result.reason,
    )
    return trg, result.contributing_headlines


def _maybe_spawn_speech_listeners(cal_events: list) -> None:
    """For each upcoming calendar event flagged has_live_stream, spawn a
    background listener thread. No-op if speech is disabled or none qualify.

    Failures are logged and swallowed — the watcher must never crash on a
    bad listener. The next tick will retry the spawn.
    """
    cfg = get_settings()
    if not cfg.speech.enabled:
        return
    try:
        from castelino.triggers.figure_deviation.orchestrator import (
            default_llm_client_factory,
            default_provider_factory,
            default_stream_resolver,
            spawn_listener_threaded,
        )
    except Exception as e:
        log.debug("speech orchestrator unavailable: %s", e)
        return

    for ev in cal_events:
        try:
            spawn_listener_threaded(
                ev,
                provider_factory=default_provider_factory,
                llm_client_factory=default_llm_client_factory,
                stream_resolver=default_stream_resolver,
            )
        except Exception as e:
            log.warning("speech listener spawn failed for %s: %s", getattr(ev, "name", "?"), e)


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


# ─────────────────────────── two-pass enrichment ─────────────────────────


def _enrich_borderlines(scores: list[HeadlineScore]) -> list[HeadlineScore]:
    """Second pass: re-score borderline headlines with Polymarket + X context."""
    cfg = get_settings().enrichment
    if not scores:
        return scores

    borderlines = [
        s for s in scores
        if cfg.borderline_min <= s.materiality <= cfg.borderline_max
    ]
    if not borderlines:
        return scores

    log.info("enrichment: %d borderline headlines to re-score", len(borderlines))

    contracts: dict[str, list] = {}
    x_sentiments: dict[str, str] = {}
    for s in borderlines:
        contracts[s.headline_id] = fetch_related_contracts(s.title)
        x_sentiments[s.headline_id] = fetch_x_sentiment(s.title)

    rescored = rescore_borderlines(borderlines, contracts, x_sentiments)

    rescored_by_id = {s.headline_id: s for s in rescored}
    return [rescored_by_id.get(s.headline_id, s) for s in scores]


# ─────────────────────────── public entry points ───────────────────────────


def fire_pipeline(
    trigger: TriggerRecord,
    recent_headlines: list[str],
    source_summaries: list[str] | None = None,
) -> dict:
    """Run one pipeline pass. Returns the final state."""
    state_data = _load_system_state()
    memio.append_short_term(trigger, WriterIdentity.TRIGGER_RUNNER)

    if not state_data.get("trading_enabled", True):
        log.warning("trading_enabled=False; pipeline runs but no portfolio writes.")

    pf = Portfolio.load()
    state = FundState(
        trigger=trigger,
        recent_headlines=recent_headlines,
        source_summaries=source_summaries or [],
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
    """One polling cycle. Four trigger paths in priority order.

    Every tick: score headlines, append to conviction ledger, then check
    black swan → regime shift → accumulated conviction → cron fallback.
    """
    state = _load_system_state()
    last_fire = (
        datetime.fromisoformat(state["last_fire_utc"])
        if state.get("last_fire_utc")
        else None
    )

    # ── Always: pull news + score + readiness + enrich borderlines + feed ledger ──
    news = fetch_recent(max_per_feed=20)
    scores = score_batch(news[:30]) if news else []
    scores = apply_readiness(scores)
    scores = _enrich_borderlines(scores)
    if scores:
        conv.append(scores)

    # ── Path 0: Calendar (unchanged — high-impact event imminent) ──
    cal_events = calmod.events_due()

    # Speech listener spawning: side-effect, runs alongside other paths.
    # For any calendar event with a live stream within the lookahead window,
    # fire off a daemon thread to listen + score + push triggers onto the
    # speech queue. The next tick's Path 0.5 picks them up.
    _maybe_spawn_speech_listeners(cal_events)

    trg = _trigger_from_calendar(cal_events)
    if trg:
        log.info("calendar trigger: %s", trg.headline)
        fire_pipeline(trg, recent_headlines=[trg.headline])
        return "calendar"

    # ── Path 0.5: Speech deviation triggers from live listener ──
    from castelino.triggers.figure_deviation.queue import speech_trigger_queue
    pending = speech_trigger_queue.drain()
    if pending:
        trg = pending[0]
        log.info("SPEECH trigger: %s", trg.headline)
        fire_pipeline(trg, recent_headlines=[trg.headline])
        return "speech"

    # ── Path 1: Black swan — single headline ≥ 0.9 ──
    trg = _check_black_swan(scores)
    if trg:
        log.info("BLACK SWAN trigger: %s", trg.headline)
        enriched = enrich_significant_headlines(news[:20])
        fire_pipeline(
            trg,
            recent_headlines=[h.title for h in enriched],
            source_summaries=[h.deep_summary for h in enriched],
        )
        return "black_swan"

    # ── Path 2: Regime shift — nowcaster label flipped ──
    trg = _check_regime_shift(state)
    if trg:
        log.info("REGIME SHIFT trigger: %s", trg.headline)
        headlines = [h.title for h in news[:20]] if news else []
        fire_pipeline(trg, recent_headlines=headlines)
        return "regime_shift"

    # ── Path 3: Accumulated conviction — directional sum crossed threshold ──
    trg, contrib = _check_conviction(last_fire)
    if trg:
        log.info("CONVICTION trigger: %s", trg.headline)
        enriched = enrich_significant_headlines(news[:20])
        fire_pipeline(
            trg,
            recent_headlines=[h.title for h in enriched],
            source_summaries=[h.deep_summary for h in enriched],
        )
        return "conviction"

    # ── Path 4: Cron fallback — nothing fired for 24h ──
    trg = _trigger_cron_fallback(last_fire)
    if trg:
        log.info("cron fallback fired (last fire %s)", last_fire)
        headlines = [h.title for h in news[:20]] if news else []
        fire_pipeline(trg, recent_headlines=headlines)
        return "cron"

    snap = conv.compute()
    log.info(
        "tick: no trigger. conviction: gb=%.2f gd=%.2f ib=%.2f id=%.2f",
        snap.growth_bullish, snap.growth_bearish,
        snap.inflation_bullish, snap.inflation_bearish,
    )
    return None


def _save_regime_key(key: str) -> None:
    """Persist the current regime key so we can detect shifts next tick."""
    state = _load_system_state()
    state["last_regime_key"] = key
    _save_system_state(state)



def replay_historical(days: int) -> None:
    log.warning("replay_historical(%d) called but replay is not yet implemented", days)


def set_trading_enabled(enabled: bool) -> None:
    state = _load_system_state()
    state["trading_enabled"] = bool(enabled)
    _save_system_state(state)
