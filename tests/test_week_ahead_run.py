import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from castelino.week_ahead import run as r
from tests.test_week_ahead_te import page, row

NY = ZoneInfo("America/New_York")
TUE = datetime(2026, 10, 13, 9, 0, tzinfo=NY)  # in the week of Oct 12
ECON = [
    {
        "country": "United States",
        "eventName": "CPI",
        "gmt": "08:30",
        "consensus": "3.6%",
        "previous": "3.4%",
        "actual": "",
    }
]
EARN = [
    {
        "symbol": "JPM",
        "name": "JPMorgan",
        "time": "time-pre-market",
        "marketCap": "$1",
        "epsForecast": "$5.94",
        "lastYearEPS": "$5.07",
    }
]
HTML = (
    '"date":"2026-10-11 00:00:00","model_permaslug":"deepseek/v4","variant":"standard",'
    '"total_completion_tokens":1,"total_prompt_tokens":9'
)


SECTORS = [{"sector": "Energy", "etf": "XLE", "ytd": 50.5, "pe": 18.8, "earnings_growth": -14.0}]


def fake_fetch(kind, day):
    return ECON if kind == "economicevents" else EARN


def te_get(slug):  # Trading Economics' page: US CPI on Tuesday at 08:30 ET (12:30 UTC)
    if slug != "united-states":
        raise RuntimeError("HTTP 403")
    return page(
        row("2026-10-13", "12:30 PM", "US", "Inflation Rate YoY", consensus="3.6%", previous="3.4%")
    )


def go(tmp_path, now=TUE, **kw):
    kw.setdefault("fetch_day", fake_fetch)
    kw.setdefault("te_get", te_get)
    kw.setdefault("universe", {"JPM": ("JPMorgan Chase", "sp500")})
    kw.setdefault("yf", lambda t: (None, None))
    kw.setdefault("get_json", lambda url: {"data": []})
    kw.setdefault("search", lambda s, u: ("NONE", []))
    kw.setdefault("fetch_fred", lambda sid: pd.Series([1.0], index=pd.to_datetime(["2026-08-01"])))
    kw.setdefault("get_text", lambda url: HTML)
    kw.setdefault("build_sectors", lambda today: SECTORS)
    out = tmp_path / "week_ahead.json"
    msg = r.run(now, out=out, **kw)
    return msg, json.loads(out.read_text())


@pytest.mark.parametrize(
    "now,monday",
    [
        (datetime(2026, 10, 12, 8, 0, tzinfo=NY), date(2026, 10, 12)),
        (datetime(2026, 10, 16, 16, 59, tzinfo=NY), date(2026, 10, 12)),
        (datetime(2026, 10, 16, 17, 0, tzinfo=NY), date(2026, 10, 19)),
        (datetime(2026, 10, 18, 9, 0, tzinfo=NY), date(2026, 10, 19)),
    ],
)
def test_week_window(now, monday):
    assert r.week_window(now) == (monday, monday + timedelta(days=4))


def test_run_writes_all_lanes(tmp_path):
    msg, data = go(tmp_path)
    assert data["week_start"] == "2026-10-12" and data["week_end"] == "2026-10-16"
    assert {e["kind"] for e in data["events"]} == {"inflation", "earnings"}
    assert data["spend"]["ramp"]["RAMPAIALL"] == [["2026-08", 1.0]]
    assert data["spend"]["openrouter"]["labs"][0]["lab"] == "deepseek"
    assert data["gaps"] == [] and "events" in msg


def test_failed_lane_keeps_previous_same_week(tmp_path):
    go(tmp_path)

    def broken(url):
        raise RuntimeError("blocked")

    _, data = go(tmp_path, get_text=broken)
    assert data["spend"]["openrouter"]["labs"][0]["lab"] == "deepseek"  # kept
    assert data["gaps"] == [{"lane": "openrouter", "error": "blocked"}]


def test_failed_lane_does_not_reuse_other_week(tmp_path):
    go(tmp_path)  # week of Oct 12

    def broken(*a):
        raise RuntimeError("source down")

    _, data = go(
        tmp_path, now=datetime(2026, 10, 20, 9, 0, tzinfo=NY), fetch_day=broken, te_get=broken
    )
    assert data["week_start"] == "2026-10-19"
    assert not [
        e for e in data["events"] if e["kind"] in ("inflation", "jobs", "other", "earnings")
    ]
    assert {g["lane"] for g in data["gaps"]} == {"econ", "earnings"}


def test_no_search_key_is_a_note(tmp_path, monkeypatch):
    monkeypatch.setattr(r, "_has_key", lambda: False)
    _, data = go(tmp_path, search=None)
    assert data["gaps"] == [{"lane": "ai", "error": "no OPENAI_API_KEY: reported launches skipped"}]


def test_all_lanes_failing_raises_and_keeps_file(tmp_path):
    go(tmp_path)
    before = (tmp_path / "week_ahead.json").read_text()

    def boom(*a):
        raise RuntimeError("offline")

    with pytest.raises(RuntimeError, match="every lane failed"):
        go(
            tmp_path,
            fetch_day=boom,
            te_get=boom,
            get_json=boom,
            search=boom,
            fetch_fred=boom,
            get_text=boom,
            build_sectors=boom,
        )
    assert (tmp_path / "week_ahead.json").read_text() == before


def test_error_strips_query_strings(tmp_path):
    def leaky(sid):
        raise RuntimeError("GET https://api.stlouisfed.org/fred?api_key=SECRET failed")

    _, data = go(tmp_path, fetch_fred=leaky)
    assert "SECRET" not in json.dumps(data)


def test_endpoint(tmp_path, monkeypatch):
    from castelino.dashboard.main import app

    monkeypatch.setattr(r, "out_path", lambda: tmp_path / "week_ahead.json")
    c = TestClient(app)
    assert c.get("/week_ahead").json() == {}
    go(tmp_path)
    assert c.get("/week_ahead").json()["week_start"] == "2026-10-12"


def test_refresh_registers_job():
    from castelino.dashboard.endpoints import refresh

    assert "week_ahead" in refresh._RUNNERS and refresh.LABELS["week_ahead"] == "Week Ahead"


def test_search_failure_keeps_confirmed_launches(tmp_path):
    models = {"data": [{"id": "a/m", "name": "Lab: Model", "created": 1791460000}]}  # Oct 8

    def search(s, u):
        raise RuntimeError("credit balance is too low")

    _, data = go(tmp_path, get_json=lambda url: models, search=search)
    assert [e["name"] for e in data["events"] if e["kind"] == "ai"] == ["Model"]
    assert data["gaps"] == [{"lane": "ai", "error": "reported launches: credit balance is too low"}]


def test_sectors_lane_written_and_kept_on_failure(tmp_path):
    _, data = go(tmp_path)
    assert data["sectors"] == SECTORS

    def boom(today):
        raise RuntimeError("yahoo down")

    _, data = go(tmp_path, build_sectors=boom)
    assert data["sectors"] == SECTORS
    assert data["gaps"] == [{"lane": "sectors", "error": "yahoo down"}]
