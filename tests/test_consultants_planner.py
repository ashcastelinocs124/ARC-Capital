import httpx
import pandas as pd
import pytest

from castelino.agents.consultants import planner
from castelino.agents.consultants.models import Company, Watchlist, WatchlistDraft
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
    monkeypatch.setattr(planner, "find_links", lambda topic, meter: [])
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
    assert calls[0][1] == "gpt-6-sol" and calls[0][2] is WatchlistDraft


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


def test_check_link_cleans_and_refuses_bad_or_dead_links():
    ok = planner.check_link(
        " https://tradingeconomics.com/united-states/inflation-cpi#chart ", status=lambda u: 200
    )
    assert ok == "https://tradingeconomics.com/united-states/inflation-cpi"
    assert (
        planner.check_link("https://a.com/x", status=lambda u: 403) == "https://a.com/x"
    )  # bot wall
    with pytest.raises(ValueError, match="not a web address"):
        planner.check_link("tradingeconomics.com/x", status=lambda u: 200)
    with pytest.raises(ValueError, match="not found"):
        planner.check_link("https://a.com/gone", status=lambda u: 404)

    def down(u):
        raise ValueError("a private address")

    with pytest.raises(ValueError, match="did not answer"):
        planner.check_link("http://localhost:8080/admin", status=down)

    def slow(u):
        raise httpx.ReadTimeout("timed out")

    fred = "https://fred.stlouisfed.org/series/DGS10"
    assert planner.check_link(fred, status=slow) == fred  # FRED stalls on non-browser requests


def test_page_status_refuses_private_addresses():
    with pytest.raises(ValueError, match="private"):
        planner.page_status("http://127.0.0.1:8080/")


def _cited(*rows):
    """(line, url) rows -> a search answer whose every line cites its url."""
    text, cites, pos = "", [], 0
    for line, url in rows:
        cites.append((url, url, pos, pos + 1))
        text += line + "\n"
        pos = len(text)
    return text, cites


def test_find_links_keeps_updating_cited_pages_cleaned_two_per_site(monkeypatch):
    eia = "https://www.eia.gov/electricity/monthly/"
    rows = [
        (
            "Electric Power Monthly: generation by source, updated monthly.",
            eia + "?utm_source=openai",
        ),
        ("Same page again, monthly.", eia + "#table"),
        ("EIA STEO, a monthly forecast.", "https://www.eia.gov/outlooks/steo/"),
        (
            "EIA hourly grid monitor, real-time demand.",
            "https://www.eia.gov/electricity/gridmonitor/",
        ),
        ("FRED industrial production, monthly.", "https://fred.stlouisfed.org/series/IPG2211S"),
        ("Yahoo XLU quote, live.", "https://finance.yahoo.com/quote/XLU"),
        ("A PDF of grid filings, quarterly.", "https://www.iso-ne.com/static-assets/letters.pdf"),
        ("Polymarket odds, updated live.", "https://polymarket.com/event/x?tid=1&utm_medium=x"),
    ] + [(f"Tracker {i}, weekly.", f"https://s{i}.org/data") for i in range(4)]
    seen = {}

    def search(system, user, model=None):
        seen["model"] = model
        return _cited(*rows)

    monkeypatch.setattr(planner.web_search, "search_cited", search)
    meter = llm.Meter()
    out = planner.find_links("AI power demand", meter)
    assert out == [
        eia,
        "https://www.eia.gov/outlooks/steo/",
        "https://polymarket.com/event/x?tid=1",
        "https://s0.org/data",
        "https://s1.org/data",
    ]
    assert meter.total == llm.SEARCH_USD and seen["model"] == "gpt-6-luna"


def test_find_links_failure_proposes_none(monkeypatch):
    def boom(system, user, model=None):
        raise RuntimeError("search down")

    monkeypatch.setattr(planner.web_search, "search_cited", boom)
    assert planner.find_links("AI power demand", llm.Meter()) == []


def test_suggest_adds_the_found_pages(monkeypatch):
    _stub(monkeypatch, Watchlist(companies=[], series=["fred:DGS10"], queries=[]))
    monkeypatch.setattr(planner, "find_links", lambda topic, meter: ["https://www.eia.gov/x"])
    assert planner.suggest("Power", llm.Meter(), close=_close).links == ["https://www.eia.gov/x"]
