from datetime import date

import numpy as np
import pandas as pd
import pytest

from castelino.agents.trade import llm, tools
from castelino.agents.weekly.board import Board


def series(n=800, start=100.0, drift=0.0005, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2023-06-01", periods=n)
    return pd.Series(start * np.exp(np.cumsum(drift + rng.normal(0, 0.01, n))), index=idx)


def test_technical_numbers_by_hand():
    px = series()
    out = tools.technical_numbers(px, None)
    last252 = px.iloc[-252:]
    assert out["range_pos"] == pytest.approx(
        round((px.iloc[-1] - last252.min()) / (last252.max() - last252.min()) * 100, 1)
    )
    assert out["dd_52w"] == pytest.approx(round((px.iloc[-1] / last252.max() - 1) * 100, 1))
    assert 0 <= out["vol_pct"] <= 100 and 0 <= out["rsi14"] <= 100
    assert "rs_3m" not in out


def test_relative_strength_against_a_benchmark():
    px, bench = series(seed=1), series(seed=2)
    out = tools.technical_numbers(px, bench)
    ratio = (px / bench).dropna()
    assert out["rs_3m"] == pytest.approx(round((ratio.iloc[-1] / ratio.iloc[-64] - 1) * 100, 1))
    assert 0 <= out["rs_pos"] <= 100


def box(**kw):
    s = {"INDA": series(seed=1), "SMH": series(seed=2)}
    return tools.TradeToolBox(
        agent="t",
        prefix=tools.prefix("T", 1),
        allowed=["technicals", "cot", "yahoo_prices"],
        board=Board(),
        end=date(2026, 10, 14),
        max_calls=5,
        yahoo=lambda t: s[t],
        **kw,
    )


def test_technicals_tool_makes_one_fact_with_every_number():
    b = box()
    text = b.call("technicals", {"ticker": "INDA", "vs": "SMH"})
    f = b.facts[0]
    assert f.id == "T1.1" and text.startswith("[T1.1]")
    assert "RSI" in f.text and "vs SMH" in f.text
    assert len(f.numbers) == 11 and f.provenance == "data" and f.series.id == "INDA"


def test_cot_tool_and_unknown_market():
    weeks = pd.date_range("2024-01-02", periods=120, freq="W-TUE")
    b = box(cftc=lambda code: pd.Series(np.linspace(-10, 20, 120), index=weeks))
    assert "net speculative" in b.call("cot", {"market": "S&P 500"})
    assert b.call("cot", {"market": "Rupee"}).startswith("Error: no COT data for Rupee")


def test_web_search_is_priced_into_the_meter():
    m = llm.Meter()
    b = tools.TradeToolBox(
        agent="t",
        prefix="NA1.",
        allowed=["web_search"],
        board=Board(),
        end=date(2026, 10, 14),
        max_calls=3,
        search=lambda *a, **k: ("", []),
        meter=m,
    )
    b.call("web_search", {"query": "q"})
    assert m.total == pytest.approx(llm.SEARCH_USD)


def test_chat_tools_shape():
    specs = tools.chat_tools(box())
    names = [s["function"]["name"] for s in specs]
    assert names[:3] == ["technicals", "cot", "yahoo_prices"]
    assert all(
        s["type"] == "function" and s["function"]["parameters"]["type"] == "object" for s in specs
    )
