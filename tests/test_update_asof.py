from datetime import date

import pandas as pd

from castelino.agents.update import asof, bls
from castelino.agents.update.models import SeriesRef
from castelino.agents.update.sources import polymarket

DAY = date(2026, 10, 3)


class Resp:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self.body


def test_fred_vintage_asks_for_values_as_known_that_day(monkeypatch):
    seen = {}

    def get(url, params, timeout):
        seen.update(params)
        return Resp(
            {
                "observations": [
                    {"date": "2026-08-01", "value": "3.7"},
                    {"date": "2026-09-01", "value": "."},
                ]
            }
        )

    s = asof.fred_vintage("CPIAUCSL", DAY, api_key="k", get=get)
    assert seen["realtime_start"] == seen["realtime_end"] == "2026-10-03"
    assert list(s.index) == [pd.Timestamp("2026-08-01")] and s.iloc[0] == 3.7


def test_truncate_drops_later_observations():
    s = pd.Series([1.0, 2.0, 3.0], index=pd.to_datetime(["2026-10-02", "2026-10-03", "2026-10-06"]))
    assert list(asof.truncate(s, DAY)) == [1.0, 2.0]


def test_bls_rows_after_the_cutoff_month_are_ignored():
    data = {
        "CUSR0000SAH1": [
            ("Sep 2026", 410.0),
            ("Aug 2026", 404.0),
            ("Jul 2026", 402.0),
            ("Jun 2026", 401.0),
        ]
    }
    facts = bls.bls_facts(fetch_fn=lambda ids: data, upto=lambda sid: "2026-08")
    assert "(Aug 2026)" in facts[0].text and "Sep 2026" not in facts[0].text


def test_polymarket_moves_are_computed_from_history_up_to_the_day():
    end = asof.day_end_ts(DAY)
    hist = [
        (end - 8 * 86400, 0.50),
        (end - 7 * 86400, 0.55),
        (end - 86400, 0.60),
        (end - 60, 0.62),
        (end + 3600, 0.99),
    ]
    events = [
        {
            "title": "Fed?",
            "slug": "fed",
            "markets": [
                {
                    "question": "Cut?",
                    "active": True,
                    "closed": False,
                    "outcomePrices": '["0.99", "0.01"]',
                    "clobTokenIds": '["tok", "x"]',
                    "oneDayPriceChange": 0.4,
                    "oneWeekPriceChange": 0.4,
                }
            ],
        }
    ]
    f = polymarket.facts(events, history_fn=lambda tok, start, end: hist, day=DAY)[0]
    assert f.numbers[-3:] == [
        62.0,
        2.0,
        7.0,
    ]  # yes, 1d, 1w as of the day; the later 0.99 is ignored


def test_chart_fetch_asof_ends_on_the_day(monkeypatch):
    s = pd.Series(range(20), index=pd.date_range("2026-09-20", periods=20, freq="D"), dtype=float)
    monkeypatch.setattr(asof, "_close", lambda ref: s)
    pts = asof.chart_fetch(SeriesRef(kind="daily", provider="yahoo", id="SPY", label="SPY"), DAY)
    assert len(pts) == 7 and pts[-1][0] == "Oct 03"


def test_news_search_names_the_past_day_and_forbids_later_items():
    from castelino.agents.update import news

    seen = []

    def search(system, user, model=None):
        seen.append(user)
        return "", []

    try:
        news.run("rates", search=search, day=DAY)
    except RuntimeError:
        pass  # no cited stories in this fake; only the prompt matters here
    assert "2026-10-03" in seen[0] and "published after 2026-10-03" in seen[0]


def test_macro_gather_uses_vintage_fetchers_for_a_past_day(monkeypatch):
    from castelino.agents.update import macro

    calls = {}

    def collect(**k):
        calls["monthly"] = k["fetch_monthly"]
        calls["close"] = k["fetch_close"]
        from castelino.agents.update.models import MarketSnapshot

        return MarketSnapshot(date=k["today"])

    monkeypatch.setattr(
        asof, "fred_vintage", lambda sid, day: pd.Series([1.0], index=[pd.Timestamp("2026-08-01")])
    )
    facts, snap = macro.gather_facts(
        collect_fn=collect, bls_fn=lambda: [], claims_fn=lambda: None, today="2026-10-03", day=DAY
    )
    assert snap.date == "2026-10-03"
    assert calls["monthly"]("CPIAUCSL").index[-1] == pd.Timestamp("2026-08-01")
