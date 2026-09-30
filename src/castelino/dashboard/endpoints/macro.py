from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks

from castelino.data.openbb_adapter import OpenBBError, get_adapter
from castelino.memory import io as memio
from castelino.memory.schemas import Hypothesis, TriggerRecord

router = APIRouter()
log = logging.getLogger(__name__)

_REGIME_MAX_AGE = timedelta(hours=24)  # ponytail: fixed TTL; nowcast is monthly, so daily is plenty
_regime_lock = threading.Lock()


def _retrain_regime() -> None:
    if not _regime_lock.acquire(blocking=False):
        return  # a retrain is already running
    try:
        from castelino.forecast.regime import train_and_forecast, write_forecast

        write_forecast(train_and_forecast())
    except Exception:
        log.exception("regime retrain failed")
    finally:
        _regime_lock.release()


@router.get("/regime_forecast")
def regime_forecast(bg: BackgroundTasks):
    """Saved forecast now; kicks off a background retrain when missing or stale."""
    from castelino.forecast.regime import read_forecast

    fc = read_forecast()
    if fc is None or datetime.now(UTC) - fc.asof > _REGIME_MAX_AGE:
        bg.add_task(_retrain_regime)
    return {
        "running": _regime_lock.locked() or fc is None or datetime.now(UTC) - fc.asof > _REGIME_MAX_AGE,
        "asof": fc.asof.isoformat() if fc else None,
        "growth_up": fc.growth.up if fc else None,
        "inflation_up": fc.inflation.up if fc else None,
        "growth_prob": fc.growth.prob_up if fc else None,
        "inflation_prob": fc.inflation.prob_up if fc else None,
    }


@router.get("/macro_indicators")
def macro_indicators():
    adapter = get_adapter()
    if not adapter.available:
        return []
    try:
        df = adapter.economic_indicators(["GDP", "CPIAUCSL", "UNRATE"])
        df = df.fillna(0).tail(24)
        records = df.reset_index().to_dict("records")
        for r in records:
            if "date" in r:
                r["date"] = str(r["date"])[:10]
        return records
    except OpenBBError:
        return []


@router.get("/yield_curve")
def yield_curve(theme: str = "dark", raw: bool = False):
    adapter = get_adapter()
    if not adapter.available:
        return [] if raw else {"data": [], "layout": {}}
    try:
        df = adapter.yield_curve()
        if raw:
            return df.reset_index().to_dict("records")
        import json
        import plotly.graph_objects as go
        fig = go.Figure()
        if not df.empty:
            row = df.iloc[-1]
            fig.add_trace(go.Scatter(x=list(row.index), y=[float(v) for v in row.values], mode="lines+markers"))
        fig.update_layout(template="plotly_dark" if theme == "dark" else "plotly_white")
        return json.loads(fig.to_json())
    except (OpenBBError, Exception):
        return [] if raw else {"data": [], "layout": {}}


@router.get("/triggers")
def triggers():
    entries = memio.read_short_term()
    trigs = sorted(
        [e for e in entries if isinstance(e, TriggerRecord)],
        key=lambda x: x.timestamp, reverse=True,
    )[:20]
    return [
        {"timestamp": t.timestamp.strftime("%Y-%m-%d %H:%M"), "source": t.source.value,
         "significance": round(t.significance, 2), "headline": t.headline}
        for t in trigs
    ]


@router.get("/hypotheses")
def hypotheses():
    entries = memio.read_short_term()
    hyps = sorted(
        [e for e in entries if isinstance(e, Hypothesis)],
        key=lambda x: x.timestamp, reverse=True,
    )[:10]
    return [
        {"timestamp": h.timestamp.strftime("%Y-%m-%d %H:%M"), "regime": h.regime.value,
         "conviction": h.conviction.value, "horizon_days": h.horizon_days,
         "thesis": h.thesis,
         "kill_criteria": " | ".join(c.description for c in h.kill_criteria)[:200]}
        for h in hyps
    ]


@router.get("/news")
def news():
    adapter = get_adapter()
    if not adapter.available:
        return []
    try:
        articles = adapter.news(limit=20)
        return [
            {"title": a.get("title", ""), "date": str(a.get("date", "")),
             "author": a.get("author", ""), "excerpt": a.get("text", "")[:200],
             "body": a.get("text", "")}
            for a in articles
        ]
    except OpenBBError:
        return []


@router.get("/economic_calendar")
def economic_calendar():
    adapter = get_adapter()
    if not adapter.available:
        return []
    try:
        return adapter.economic_calendar()
    except OpenBBError:
        return []
