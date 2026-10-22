import pandas as pd
import pytest

from castelino.agents.consultants import planner
from castelino.agents.consultants.models import Company, Watchlist
from castelino.agents.trade import llm


def _close(ticker: str) -> pd.Series:
    if ticker == "FAKE":
        raise ValueError("no data")
    if ticker == "EMPTY":
        return pd.Series(dtype=float)
    return pd.Series([1.0, 2.0])


def _stub(monkeypatch, wl: Watchlist) -> list:
    calls = []

    def fake(agent, model, messages, schema, meter, **kw):
        calls.append((agent, model, schema))
        return wl

    monkeypatch.setattr(llm, "structured", fake)
    return calls


def test_suggest_drops_tickers_yahoo_cannot_price(monkeypatch):
    wl = Watchlist(
        companies=[
            Company(name="NVIDIA", ticker="NVDA"),
            Company(name="Fake", ticker="FAKE"),
            Company(name="Empty", ticker="EMPTY"),
        ],
        series=[],
        queries=["AI chips"],
    )
    calls = _stub(monkeypatch, wl)
    out = planner.suggest("AI chips", llm.Meter(), close=_close)
    assert [c.ticker for c in out.companies] == ["NVDA"]
    assert calls[0][1] == "gpt-6-sol" and calls[0][2] is Watchlist


def test_suggest_drops_malformed_series(monkeypatch):
    _stub(monkeypatch, Watchlist(companies=[], series=["fred:DGS10", "bloomberg:XYZ"], queries=[]))
    assert planner.suggest("Rates", llm.Meter(), close=_close).series == ["fred:DGS10"]


def test_suggest_caps_lengths(monkeypatch):
    many = [Company(name=f"C{i}", ticker=f"T{i}") for i in range(12)]
    wl = Watchlist(
        companies=many,
        series=[f"fred:S{i}" for i in range(9)],
        queries=[f"q{i}" for i in range(7)],
    )
    _stub(monkeypatch, wl)
    out = planner.suggest("Big", llm.Meter(), close=_close)
    assert (len(out.companies), len(out.series), len(out.queries)) == (8, 6, 4)


def test_system_prompt_asks_for_queries_even_without_tickers():
    assert "queries" in planner.SYSTEM
    assert "no companies" in planner.SYSTEM.lower()


def test_check_company_uppercases_names_and_refuses_unpriced():
    co = planner.check_company(" avgo ", close=_close, name=lambda t: "Broadcom")
    assert (co.name, co.ticker) == ("Broadcom", "AVGO")
    with pytest.raises(ValueError, match="FAKE has no prices"):
        planner.check_company("fake", close=_close, name=str)


def test_check_series_normalises_and_refuses_no_data():
    assert planner.check_series("fred:dgs10", fred=_close, close=_close) == "fred:DGS10"
    assert planner.check_series("yahoo:^VIX", fred=_close, close=_close) == "yahoo:^VIX"
    with pytest.raises(ValueError, match="returned no data"):
        planner.check_series("yahoo:EMPTY", fred=_close, close=_close)
    with pytest.raises(ValueError, match="not fred:ID or yahoo:TICKER"):
        planner.check_series("bloomberg:XYZ", fred=_close, close=_close)
