from __future__ import annotations

import json

from fastapi import APIRouter, Query

from castelino.data.openbb_adapter import OpenBBError, get_adapter

router = APIRouter()


@router.get("/ta_chart")
def ta_chart(symbol: str = Query("SPY"), theme: str = "dark", raw: bool = False):
    adapter = get_adapter()
    if not adapter.available:
        return [] if raw else {"data": [], "layout": {}}
    try:
        df = adapter.history(symbol, lookback_days=120)
        if raw:
            return df.reset_index().to_dict("records")
        import plotly.graph_objects as go
        fig = go.Figure(data=[go.Candlestick(
            x=df.index.astype(str).tolist(), open=df["open"], high=df["high"],
            low=df["low"], close=df["close"]
        )])
        fig.update_layout(template="plotly_dark" if theme == "dark" else "plotly_white",
                          xaxis_rangeslider_visible=False)
        return json.loads(fig.to_json())
    except (OpenBBError, Exception):
        return [] if raw else {"data": [], "layout": {}}


@router.get("/screener")
def screener():
    adapter = get_adapter()
    if not adapter.available:
        return []
    try:
        df = adapter.screen_equities()
        return df.head(50).to_dict("records")
    except (OpenBBError, Exception):
        return []


@router.get("/correlations")
def correlations(theme: str = "dark", raw: bool = False):
    adapter = get_adapter()
    if not adapter.available:
        return [] if raw else {"data": [], "layout": {}}
    try:
        symbols = ["SPY", "TLT", "GLD", "USO", "EURUSD"]
        corr = adapter.correlation_matrix(symbols, lookback_days=90)
        if raw:
            return corr.reset_index().to_dict("records")
        import plotly.graph_objects as go
        fig = go.Figure(data=go.Heatmap(
            z=corr.values.tolist(), x=corr.columns.tolist(),
            y=corr.index.tolist(), colorscale="RdBu", zmid=0
        ))
        fig.update_layout(template="plotly_dark" if theme == "dark" else "plotly_white")
        return json.loads(fig.to_json())
    except (OpenBBError, Exception):
        return [] if raw else {"data": [], "layout": {}}


@router.get("/sector_performance")
def sector_performance():
    adapter = get_adapter()
    if not adapter.available:
        return []
    try:
        return adapter.sector_performance()
    except (OpenBBError, Exception):
        return []
