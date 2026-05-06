from __future__ import annotations

import json

from fastapi import APIRouter

from castelino.execution.portfolio import Portfolio
from castelino.memory import io as memio
from castelino.memory.schemas import PrincipleWarning

router = APIRouter()


@router.get("/exposure_by_class")
def exposure_by_class(theme: str = "dark", raw: bool = False):
    pf = Portfolio.load()
    by_class: dict[str, float] = {}
    for p in pf.positions:
        cls = p.asset_class.value if hasattr(p.asset_class, "value") else str(p.asset_class)
        by_class[cls] = by_class.get(cls, 0) + abs(p.quantity * p.current_price)
    if raw:
        return [{"asset_class": k, "exposure": round(v, 2)} for k, v in by_class.items()]
    import plotly.graph_objects as go
    fig = go.Figure(data=[go.Pie(labels=list(by_class.keys()), values=list(by_class.values()))])
    fig.update_layout(template="plotly_dark" if theme == "dark" else "plotly_white")
    return json.loads(fig.to_json())


@router.get("/exposure_by_instrument")
def exposure_by_instrument(theme: str = "dark", raw: bool = False):
    pf = Portfolio.load()
    data = [{"instrument": p.instrument_id, "exposure": round(abs(p.quantity * p.current_price), 2)}
            for p in pf.positions]
    if raw:
        return data
    import plotly.graph_objects as go
    fig = go.Figure(data=[go.Bar(x=[d["instrument"] for d in data], y=[d["exposure"] for d in data])])
    fig.update_layout(template="plotly_dark" if theme == "dark" else "plotly_white")
    return json.loads(fig.to_json())


@router.get("/warnings")
def warnings():
    entries = memio.read_short_term()
    warns = sorted(
        [e for e in entries if isinstance(e, PrincipleWarning)],
        key=lambda x: x.timestamp, reverse=True,
    )[:20]
    return [
        {"timestamp": w.timestamp.strftime("%Y-%m-%d %H:%M"), "rule_id": w.rule_id,
         "severity": w.severity, "description": w.description}
        for w in warns
    ]
