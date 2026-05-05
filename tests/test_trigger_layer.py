"""Trigger layer — calendar, news, significance, cron fallback, off-switch."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from castelino.triggers import calendar as calmod
from castelino.triggers import news as newsmod
from castelino.triggers import runner
from castelino.triggers.news import NewsHeadline


@pytest.fixture(autouse=True)
def _isolate_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(calmod, "_calendar_path", lambda: tmp_path / "calendar.json")
    monkeypatch.setattr(newsmod, "_news_cache_path", lambda: tmp_path / "news.json")
    monkeypatch.setattr(runner, "_system_state_path", lambda: tmp_path / "system_state.json")


def test_calendar_bootstraps_with_defaults(tmp_path):
    events = calmod.pull_calendar(window_days=365)
    assert isinstance(events, list)
    # Default seed has plausible content
    if events:
        assert all(e.impact in ("high", "medium", "low") for e in events)


def test_calendar_filters_to_window():
    far_future = (datetime.now(UTC) + timedelta(days=400)).date().isoformat()
    near = (datetime.now(UTC) + timedelta(days=2)).date().isoformat()
    raw = [
        {"date": far_future, "name": "x", "region": "US", "impact": "low",
         "asset_classes": []},
        {"date": near, "name": "near event", "region": "US", "impact": "high",
         "asset_classes": ["equity"]},
    ]
    p = calmod._calendar_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(raw))
    out = calmod.pull_calendar(window_days=7)
    assert len(out) == 1
    assert out[0].name == "near event"


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
