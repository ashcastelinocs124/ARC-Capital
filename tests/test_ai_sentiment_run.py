import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from castelino.ai_sentiment import run as r

NY = ZoneInfo("America/New_York")
NOW = datetime(2026, 10, 14, 17, 0, tzinfo=NY)
LEX = {
    "positive": ["fast"],
    "negative": ["slow"],
    "negators": ["not"],
    "families": {"Anthropic": ["claude"], "OpenAI": ["gpt"]},
}
ACCOUNTS = {"user0": "", "user1": ""}


def go(tmp_path, now=NOW, **kw):
    calls = []

    def fetch_day(day):
        calls.append(day)
        return [
            {
                "url": f"https://x.com/user0/status/{day.toordinal()}",
                "author": "user0",
                "text": "Claude is fast. GPT is slow",
            },
            # an untracked author never counts, even if the search returned it
            {
                "url": "https://x.com/stranger/status/1",
                "author": "stranger",
                "text": "Claude is slow",
            },
        ]

    kw.setdefault("fetch_day", fetch_day)
    kw.setdefault("has_key", lambda: True)
    out = tmp_path / "ai_sentiment.json"
    msg = r.run(now, out=out, accounts=ACCOUNTS, lex=LEX, **kw)
    return msg, json.loads(out.read_text()), calls


def test_no_token_is_skipped(tmp_path):
    with pytest.raises(r.NotConfigured):
        go(tmp_path, has_key=lambda: False)


def test_first_run_backfills_the_7_days_x_allows(tmp_path):
    _, data, calls = go(tmp_path)
    assert calls == [date(2026, 10, d) for d in range(8, 15)]
    assert sorted(data["days"]) == [f"2026-10-{d:02d}" for d in range(8, 15)]
    p = data["providers"]
    assert p["Anthropic"]["level"] == 100.0 and p["OpenAI"]["level"] == -100.0
    assert p["Anthropic"]["n7"] == 7
    assert p["Anthropic"]["delta"] is None  # needs 14 days
    assert p["OpenAI"]["samples"][0]["hits"] == ["slow"]


def test_later_run_fetches_missing_days_and_today(tmp_path):
    go(tmp_path)
    _, data, calls = go(tmp_path, now=datetime(2026, 10, 16, 17, 0, tzinfo=NY))
    assert calls == [date(2026, 10, 15), date(2026, 10, 16)]
    assert max(data["days"]) == "2026-10-16"


def test_delta_appears_after_14_days(tmp_path):
    go(tmp_path)
    _, data, _ = go(tmp_path, now=datetime(2026, 10, 21, 17, 0, tzinfo=NY))
    assert data["providers"]["Anthropic"]["delta"] == 0.0


def test_failed_day_is_a_gap_and_not_written(tmp_path):
    go(tmp_path)

    def boom(day):
        raise RuntimeError("x api: HTTP 429 https://api.x.com/2?token=SECRET")

    _, data, _ = go(tmp_path, now=datetime(2026, 10, 15, 17, 0, tzinfo=NY), fetch_day=boom)
    assert "2026-10-15" not in data["days"] and max(data["days"]) == "2026-10-14"
    assert data["gaps"] and "SECRET" not in json.dumps(data)


def test_endpoint(tmp_path, monkeypatch):
    from castelino.dashboard.main import app

    monkeypatch.setattr(r, "out_path", lambda: tmp_path / "ai_sentiment.json")
    c = TestClient(app)
    assert c.get("/ai_sentiment").json() == {}
    go(tmp_path)
    assert "providers" in c.get("/ai_sentiment").json()


def test_refresh_job_registered_and_skips_without_token(monkeypatch):
    from castelino.dashboard.endpoints import refresh

    assert refresh.LABELS["ai_sentiment"] == "AI Model Sentiment"
    monkeypatch.setattr(r, "has_key", lambda: False)
    with pytest.raises(refresh.Skipped):
        refresh.job_ai_sentiment()
