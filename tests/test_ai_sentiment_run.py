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
ACCOUNTS = {f"user{i}": "" for i in range(25)}  # 25 handles -> 2 groups


def go(tmp_path, now=NOW, **kw):
    calls = []

    def find(handles, day):
        calls.append((len(handles), day))
        return [f"https://x.com/user0/status/{day.toordinal()}"]

    def fetch(urls, accounts):
        return [{"url": u, "author": "user0", "text": "Claude is fast. GPT is slow"} for u in urls]

    kw.setdefault("find", find)
    kw.setdefault("fetch", fetch)
    kw.setdefault("has_key", lambda: True)
    out = tmp_path / "ai_sentiment.json"
    msg = r.run(now, out=out, accounts=ACCOUNTS, lex=LEX, **kw)
    return msg, json.loads(out.read_text()), calls


def test_no_key_is_skipped(tmp_path):
    with pytest.raises(r.NotConfigured):
        go(tmp_path, has_key=lambda: False)


def test_first_run_backfills_14_days_in_groups_of_20(tmp_path):
    _, data, calls = go(tmp_path)
    assert len(data["days"]) == 14 and min(data["days"]) == "2026-10-01"
    assert sorted({n for n, _ in calls}) == [5, 20] and len(calls) == 28
    p = data["providers"]
    assert p["Anthropic"]["level"] == 100.0 and p["OpenAI"]["level"] == -100.0
    assert p["Anthropic"]["delta"] == 0.0 and p["Anthropic"]["n7"] == 7
    assert p["Anthropic"]["series"][-1] == ["2026-10-14", 100.0]
    assert p["OpenAI"]["samples"][0]["hits"] == ["slow"]


def test_later_run_only_fetches_missing_days(tmp_path):
    go(tmp_path)
    _, data, calls = go(tmp_path, now=datetime(2026, 10, 16, 17, 0, tzinfo=NY))
    assert sorted({d for _, d in calls}) == [date(2026, 10, 15), date(2026, 10, 16)]
    assert max(data["days"]) == "2026-10-16"


def test_today_is_always_refetched(tmp_path):
    go(tmp_path)
    _, _, calls = go(tmp_path)
    assert {d for _, d in calls} == {date(2026, 10, 14)}


def test_failed_group_is_a_gap_and_day_kept_from_other_group(tmp_path):
    def find(handles, day):
        if len(handles) == 5:
            raise RuntimeError("xai 500 https://api.x.ai/v1?key=SECRET")
        return [f"https://x.com/user0/status/{day.toordinal()}"]

    _, data, _ = go(tmp_path, find=find)
    assert len(data["days"]) == 14
    assert data["gaps"] and "SECRET" not in json.dumps(data)


def test_day_with_every_group_failing_is_not_written(tmp_path):
    go(tmp_path)

    def boom(handles, day):
        raise RuntimeError("down")

    _, data, _ = go(tmp_path, now=datetime(2026, 10, 15, 17, 0, tzinfo=NY), find=boom)
    assert "2026-10-15" not in data["days"] and max(data["days"]) == "2026-10-14"


def test_endpoint(tmp_path, monkeypatch):
    from castelino.dashboard.main import app

    monkeypatch.setattr(r, "out_path", lambda: tmp_path / "ai_sentiment.json")
    c = TestClient(app)
    assert c.get("/ai_sentiment").json() == {}
    go(tmp_path)
    assert "providers" in c.get("/ai_sentiment").json()


def test_refresh_job_registered_and_skips_without_key(monkeypatch):
    from castelino.dashboard.endpoints import refresh

    assert refresh.LABELS["ai_sentiment"] == "AI Model Sentiment"
    monkeypatch.setattr(r, "has_key", lambda: False)
    with pytest.raises(refresh.Skipped):
        refresh.job_ai_sentiment()
