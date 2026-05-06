from __future__ import annotations

import json

from fastapi import APIRouter, Query

from castelino.data.openbb_adapter import OpenBBError, get_adapter

router = APIRouter()


@router.get("/ta_chart")
def ta_chart(symbol: str = Query("SPY"), theme: str = "dark", raw: bool = False):
    import plotly.graph_objects as go
    from castelino.execution.pricing import PricingError, history

    df = None
    adapter = get_adapter()
    if adapter.available:
        try:
            df = adapter.history(symbol, lookback_days=120)
        except OpenBBError:
            pass

    if df is None or df.empty:
        try:
            df = history(symbol, lookback_days=120)
        except (PricingError, Exception):
            return [] if raw else {"data": [], "layout": {}}

    if df.empty:
        return [] if raw else {"data": [], "layout": {}}

    if raw:
        return df.reset_index().to_dict("records")

    fig = go.Figure(data=[go.Candlestick(
        x=df.index.astype(str).tolist(), open=df["open"], high=df["high"],
        low=df["low"], close=df["close"]
    )])
    fig.update_layout(template="plotly_dark" if theme == "dark" else "plotly_white",
                      xaxis_rangeslider_visible=False)
    return json.loads(fig.to_json())


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
    import pandas as pd
    import plotly.graph_objects as go
    from castelino.execution.pricing import PricingError, history

    symbols = ["SPY", "TLT", "GLD", "USO", "EURUSD"]

    adapter = get_adapter()
    corr = None
    if adapter.available:
        try:
            corr = adapter.correlation_matrix(symbols, lookback_days=90)
        except OpenBBError:
            pass

    if corr is None:
        try:
            frames = {}
            for sym in symbols:
                df = history(sym, lookback_days=90)
                frames[sym] = df["close"]
            combined = pd.DataFrame(frames).dropna()
            corr = combined.pct_change().dropna().corr()
        except (PricingError, Exception):
            return [] if raw else {"data": [], "layout": {}}

    if raw:
        return corr.reset_index().to_dict("records")

    fig = go.Figure(data=go.Heatmap(
        z=corr.values.tolist(), x=corr.columns.tolist(),
        y=corr.index.tolist(), colorscale="RdBu", zmid=0
    ))
    fig.update_layout(template="plotly_dark" if theme == "dark" else "plotly_white")
    return json.loads(fig.to_json())


@router.get("/sector_performance")
def sector_performance():
    adapter = get_adapter()
    if not adapter.available:
        return []
    try:
        return adapter.sector_performance()
    except (OpenBBError, Exception):
        return []
