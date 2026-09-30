from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from castelino.config import get_settings
from castelino.data.openbb_adapter import OpenBBError, get_adapter
from castelino.memory import io as memio
from castelino.memory.schemas import Hypothesis, TriggerRecord

router = APIRouter()


def _update_root() -> Path:
    cfg = get_settings()
    return cfg.root / cfg.update_agent.data_dir


_ACTIVE = {"checking", "refitting", "gating", "collecting", "writing", "guarding"}


@router.get("/regime_forecast")
def regime_forecast():
    """Read-only: the registry's served forecast. The daily update run owns retraining."""
    from castelino.agents.update.registry import ModelRegistry
    from castelino.agents.update.runner import read_status
    from castelino.forecast.regime import read_forecast

    root = _update_root()
    fc = ModelRegistry(root / "models").current() or read_forecast()  # legacy file until first run
    return {
        "running": read_status(root)["stage"] in _ACTIVE,
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
