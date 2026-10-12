import json
from datetime import date
from pathlib import Path

from castelino.week_ahead import earnings

FIX = Path(__file__).parent / "fixtures" / "week_ahead"
UNIVERSE = {
    "JPM": ("JPMorgan Chase", "sp500"),
    "BRK.B": ("Berkshire Hathaway", "sp500"),
    "TSM": ("Taiwan Semiconductor", "ai_extra"),
    "005930.KS": ("Samsung Electronics", "ai_extra"),
}


def rows(day: str) -> list[dict]:
    return json.loads((FIX / f"earn-{day}.json").read_text())["data"]["rows"]


def test_load_universe_normalises(tmp_path):
    p = tmp_path / "u.csv"
    p.write_text(
        "ticker,name,group\nBRK.B,Berkshire Hathaway,sp500\nTSM,Taiwan Semiconductor,ai_extra\n"
    )
    assert earnings.load_universe(p) == {
        "BRK.B": ("Berkshire Hathaway", "sp500"),
        "TSM": ("Taiwan Semiconductor", "ai_extra"),
    }


def test_filters_to_universe_and_parses():
    evs = earnings.from_nasdaq(rows("2026-10-13"), date(2026, 10, 13), UNIVERSE)
    assert [e["ticker"] for e in evs] == ["JPM"]
    jpm = evs[0]
    assert jpm["company"] == "JPMorgan Chase" and jpm["group"] == "sp500"
    assert jpm["session"] == "pre" and jpm["eps_est"] == 5.94 and jpm["eps_year_ago"] == 5.07
    assert jpm["market_cap"] == 880976070000.0 and jpm["kind"] == "earnings"


def test_ai_extra_and_slash_symbols():
    evs = earnings.from_nasdaq(rows("2026-10-15"), date(2026, 10, 15), UNIVERSE)
    assert [e["ticker"] for e in evs] == ["TSM"] and evs[0]["group"] == "ai_extra"
    brk = [
        {
            "symbol": "BRK/B",
            "name": "Berkshire",
            "time": "time-after-hours",
            "marketCap": "",
            "epsForecast": "",
            "lastYearEPS": "($0.09)",
        }
    ]
    e = earnings.from_nasdaq(brk, date(2026, 10, 15), UNIVERSE)[0]
    assert e["ticker"] == "BRK.B" and e["session"] == "post"
    assert e["eps_est"] is None and e["eps_year_ago"] == -0.09


def test_fetch_week_adds_yfinance_names_inside_the_week():
    def fetch(kind, day):
        assert kind == "earnings"
        return rows(day.isoformat()) if day >= date(2026, 10, 13) else []

    def yf(t):
        assert t == "005930.KS"  # only non-US ai_extra tickers go to yfinance
        return date(2026, 10, 14), 1.25

    evs = earnings.fetch_week(date(2026, 10, 12), UNIVERSE, fetch=fetch, yf=yf)
    sam = [e for e in evs if e["ticker"] == "005930.KS"]
    assert sam and sam[0]["date"] == "2026-10-14" and sam[0]["eps_est"] == 1.25
    assert {e["ticker"] for e in evs} >= {"JPM", "TSM"}


def test_yfinance_date_outside_week_is_dropped_and_errors_skip():
    def nothing(kind, day):
        return []

    evs = earnings.fetch_week(
        date(2026, 10, 12), UNIVERSE, fetch=nothing, yf=lambda t: (date(2026, 11, 1), None)
    )
    assert evs == []

    def boom(t):
        raise RuntimeError("yahoo down")

    assert earnings.fetch_week(date(2026, 10, 12), UNIVERSE, fetch=nothing, yf=boom) == []
