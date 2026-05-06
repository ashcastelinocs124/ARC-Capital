"""Trigger layer — calendar, news, significance, cron fallback, off-switch."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import requests

from castelino.triggers import calendar as calmod
from castelino.triggers import news as newsmod
from castelino.triggers import runner
from castelino.triggers.news import NewsHeadline


@pytest.fixture(autouse=True)
def _isolate_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(calmod, "_fred_cache_path", lambda: tmp_path / "fred_cache.json")
    monkeypatch.setattr(newsmod, "_news_cache_path", lambda: tmp_path / "news.json")
    monkeypatch.setattr(runner, "_system_state_path", lambda: tmp_path / "system_state.json")
    monkeypatch.setenv("FRED_API_KEY", "test-key-fake")


def test_calendar_returns_events_from_fred_cache(tmp_path):
    """FRED cache with valid entries returns CalendarEvents."""
    near_date = (datetime.now(UTC) + timedelta(days=3)).strftime("%Y-%m-%d")
    cached = {"release_dates": [
        {"release_id": 10, "date": near_date},
        {"release_id": 50, "date": near_date},
    ]}
    (tmp_path / "fred_cache.json").write_text(json.dumps(cached))
    events = calmod.pull_calendar(window_days=30)
    us_events = [e for e in events if e.region == "US"]
    assert len(us_events) == 2
    assert all(e.impact in ("high", "medium", "low") for e in events)


def test_calendar_filters_to_window(tmp_path):
    far_future = (datetime.now(UTC) + timedelta(days=400)).strftime("%Y-%m-%d")
    near = (datetime.now(UTC) + timedelta(days=2)).strftime("%Y-%m-%d")
    cached = {"release_dates": [
        {"release_id": 10, "date": far_future},
        {"release_id": 10, "date": near},
    ]}
    (tmp_path / "fred_cache.json").write_text(json.dumps(cached))
    out = calmod.pull_calendar(window_days=7)
    us_events = [e for e in out if e.region == "US"]
    assert len(us_events) == 1
    assert us_events[0].name == "US CPI YoY"


def test_fred_fetch_parses_releases(tmp_path, monkeypatch):
    """FRED API response is parsed into CalendarEvents."""
    near_date = (datetime.now(UTC) + timedelta(days=3)).strftime("%Y-%m-%d")
    fake_response = {
        "release_dates": [
            {"release_id": 10, "date": near_date},
            {"release_id": 50, "date": near_date},
            {"release_id": 999, "date": near_date},
        ]
    }

    class FakeResp:
        status_code = 200
        def json(self):
            return fake_response
        def raise_for_status(self):
            pass

    monkeypatch.setattr("requests.get", lambda *a, **kw: FakeResp())

    events = calmod._fetch_fred_releases()
    assert len(events) == 2
    names = {e.name for e in events}
    assert "US CPI YoY" in names
    assert "US Non-Farm Payrolls" in names
    assert all(e.region == "US" for e in events)


def test_fred_cache_avoids_network_when_fresh(tmp_path, monkeypatch):
    """When cache exists and is fresh, no network call is made."""
    near_date = (datetime.now(UTC) + timedelta(days=3)).strftime("%Y-%m-%d")
    cached = {"release_dates": [{"release_id": 10, "date": near_date}]}
    (tmp_path / "fred_cache.json").write_text(json.dumps(cached))

    def boom(*a, **kw):
        raise AssertionError("Network should not be hit when cache is fresh")

    monkeypatch.setattr("requests.get", boom)

    events = calmod._fetch_fred_releases()
    assert len(events) == 1
    assert events[0].name == "US CPI YoY"


def test_fred_api_failure_uses_stale_cache(tmp_path, monkeypatch):
    """If FRED API is down but stale cache exists, use stale data."""
    import os as os_mod

    near_date = (datetime.now(UTC) + timedelta(days=3)).strftime("%Y-%m-%d")
    cached = {"release_dates": [{"release_id": 10, "date": near_date}]}
    cache_path = tmp_path / "fred_cache.json"
    cache_path.write_text(json.dumps(cached))

    # Make cache stale
    old_time = (datetime.now(UTC) - timedelta(hours=48)).timestamp()
    os_mod.utime(cache_path, (old_time, old_time))

    def fail(*a, **kw):
        raise requests.RequestException("timeout")

    monkeypatch.setattr("requests.get", fail)

    events = calmod._fetch_fred_releases()
    assert len(events) == 1
    assert events[0].name == "US CPI YoY"


def test_news_dedupes_seen_headlines(monkeypatch):
    # Stub feedparser so the test never hits the network
    class FakeFeed:
        feed = type("F", (), {"get": staticmethod(lambda k, d="": "Fake Source")})
        entries = [
            {"link": "http://x/1", "title": "Hello", "published_parsed": (2026, 5, 1, 12, 0, 0)},
            {"link": "http://x/2", "title": "World", "published_parsed": (2026, 5, 1, 12, 1, 0)},
        ]

    monkeypatch.setattr(newsmod.feedparser, "parse", lambda url: FakeFeed)
    h1 = newsmod.fetch_recent()
    assert len(h1) == 2 * len(["fake feeds"])  # rss_feeds in config has 4 entries → returns 4*2=8 unique by link
    # Second run should return zero new
    h2 = newsmod.fetch_recent()
    assert len(h2) == 0


def test_significance_filter_logs_below_threshold(monkeypatch, tmp_path):
    """News scoring batch with all materiality < 0.7 → no trigger but logs."""
    from castelino.memory import io as memio
    monkeypatch.setattr(
        memio,
        "_paths",
        lambda: memio.JournalPaths(
            short_term_md=tmp_path / "st.md",
            short_term_index=tmp_path / "st_idx.json",
            long_term_md=tmp_path / "lt.md",
            principles_md=tmp_path / "p.md",
        ),
    )

    from castelino.triggers import significance, runner as runner_mod

    def fake_score(headlines):
        return [
            significance.HeadlineScore(
                headline_id=h.id, title=h.title, materiality=0.5,
                asset_classes_affected=["equity"],
                one_sentence_reason="meh",
            )
            for h in headlines
        ]

    monkeypatch.setattr(runner_mod, "score_batch", fake_score)
    headlines = [
        NewsHeadline(id=f"h{i}", title=f"t{i}", summary="", link=f"l{i}",
                     source="src", published=datetime.now(UTC))
        for i in range(2)
    ]
    trg = runner_mod._trigger_from_news(headlines)
    assert trg is None
    # The two ≥0.4 entries should be logged
    counts = memio.journal_summary()
    assert counts.get("TriggerRecord", 0) == 2


def test_significance_fires_above_threshold(monkeypatch, tmp_path):
    from castelino.memory import io as memio
    monkeypatch.setattr(
        memio,
        "_paths",
        lambda: memio.JournalPaths(
            short_term_md=tmp_path / "st.md",
            short_term_index=tmp_path / "st_idx.json",
            long_term_md=tmp_path / "lt.md",
            principles_md=tmp_path / "p.md",
        ),
    )

    from castelino.triggers import significance, runner as runner_mod

    def fake_score(headlines):
        return [
            significance.HeadlineScore(
                headline_id=headlines[0].id,
                title=headlines[0].title,
                materiality=0.85,
                asset_classes_affected=["bond_etf"],
                one_sentence_reason="fed",
            )
        ]

    monkeypatch.setattr(runner_mod, "score_batch", fake_score)
    h = NewsHeadline(id="h1", title="FOMC pauses", summary="", link="l1",
                     source="src", published=datetime.now(UTC))
    trg = runner_mod._trigger_from_news([h])
    assert trg is not None
    assert trg.significance == 0.85
    assert "bond_etf" in trg.asset_classes_affected


def test_cron_fallback_fires_after_24h():
    last = datetime.now(UTC) - timedelta(hours=25)
    trg = runner._trigger_cron_fallback(last)
    assert trg is not None
    assert trg.significance == 0.3


def test_cron_fallback_skips_when_recent():
    last = datetime.now(UTC) - timedelta(hours=12)
    assert runner._trigger_cron_fallback(last) is None


def test_off_switch_persists():
    runner.set_trading_enabled(False)
    state = runner._load_system_state()
    assert state["trading_enabled"] is False
    runner.set_trading_enabled(True)
    state = runner._load_system_state()
    assert state["trading_enabled"] is True
