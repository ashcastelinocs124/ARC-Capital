"""Phase-2 tests: replay loop skeleton — business-day walk, env-var lifecycle,
trigger-candidate routing, and summary persistence."""
from __future__ import annotations

import os
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from castelino.backtest import BACKTEST_AS_OF_ENV
from castelino.backtest import news_archive as na
from castelino.backtest import runner as runmod


@pytest.fixture
def runs_dir(monkeypatch, tmp_path):
    """Redirect runs_dir to tmp so backtest output lands somewhere disposable."""
    cfg = runmod.get_settings()
    monkeypatch.setattr(cfg.backtest, "runs_dir", str(tmp_path / "runs"))
    yield tmp_path / "runs"


@pytest.fixture
def fake_news(monkeypatch, tmp_path):
    """A tiny news archive across a 5-day window."""
    df = pd.DataFrame([
        # Mon 3/11 — quiet day
        {"date": pd.Timestamp("2024-03-11 14:00"), "source": "nyt",
         "headline": "Markets drift on light volume",
         "abstract": "S&P closes flat.", "url": "https://nyt/m1"},
        # Tue 3/12 — black swan
        {"date": pd.Timestamp("2024-03-12 09:30"), "source": "nyt",
         "headline": "Major bank default sparks panic",
         "abstract": "Regional lender collapses overnight.", "url": "https://nyt/m2"},
        # Wed 3/13 — Fed signal
        {"date": pd.Timestamp("2024-03-13 10:00"), "source": "nyt",
         "headline": "Fed minutes signal rate cuts",
         "abstract": "Members favor easing.", "url": "https://nyt/m3"},
        # Thu 3/14 — Trump
        {"date": pd.Timestamp("2024-03-14 16:00"), "source": "sonar_trump",
         "headline": "Trump threatens 60% China tariff at rally",
         "abstract": "Campaign remarks roil markets.", "url": "https://sonar/m4"},
        # Fri 3/15 — quiet
        {"date": pd.Timestamp("2024-03-15 12:00"), "source": "nyt",
         "headline": "Volatility ebbs into close",
         "abstract": "VIX drops 2 points.", "url": "https://nyt/m5"},
    ])
    p = tmp_path / "historical_news.parquet"
    df.to_parquet(p)
    monkeypatch.setattr(na, "historical_news_path", lambda: p)
    na.clear_cache()
    yield
    na.clear_cache()


def test_business_days_excludes_weekends():
    out = runmod.business_days(date(2024, 3, 11), date(2024, 3, 17))
    # Mon-Fri 11-15, then 16-17 are Sat/Sun → excluded
    assert out == [date(2024, 3, 11), date(2024, 3, 12), date(2024, 3, 13),
                   date(2024, 3, 14), date(2024, 3, 15)]


def test_business_days_inclusive_endpoints():
    # Both endpoints are Mondays
    out = runmod.business_days(date(2024, 3, 11), date(2024, 3, 11))
    assert out == [date(2024, 3, 11)]


def test_business_days_empty_when_start_after_end():
    assert runmod.business_days(date(2024, 3, 15), date(2024, 3, 10)) == []


def test_runner_walks_5_days_and_counts_triggers(fake_news, runs_dir):
    runner = runmod.BacktestRunner()
    summary = runner.run(
        start=date(2024, 3, 11), end=date(2024, 3, 15),
        run_id="test-001",
    )
    # 5 business days
    assert summary.business_days == 5
    assert len(summary.daily_records) == 5
    # Black swan on 3/12 ("default" → 0.92), Fed on 3/13 (≥0.7), Trump 3/14 (≥0.7)
    # Mon 3/11 and Fri 3/15 should NOT trigger ("drift", "ebbs" don't hit any rule)
    assert summary.triggers_by_path.get("black_swan", 0) == 1
    assert summary.triggers_by_path.get("news", 0) >= 2  # Fed + Trump
    assert summary.pipeline_fires == 3


def test_runner_env_var_balanced_after_run(fake_news, runs_dir):
    os.environ.pop(BACKTEST_AS_OF_ENV, None)
    runner = runmod.BacktestRunner()
    runner.run(
        start=date(2024, 3, 11), end=date(2024, 3, 15),
        run_id="test-env",
    )
    # After the run, env must be unset (no leak between run and live code)
    assert BACKTEST_AS_OF_ENV not in os.environ


def test_runner_env_var_unset_even_on_exception(fake_news, runs_dir, monkeypatch):
    """If the score fn raises, the env var still gets cleaned up."""
    def raises(_):
        raise RuntimeError("boom")
    runner = runmod.BacktestRunner(score_fn=raises)
    with pytest.raises(RuntimeError, match="boom"):
        runner.run(start=date(2024, 3, 11), end=date(2024, 3, 11), run_id="err")
    assert BACKTEST_AS_OF_ENV not in os.environ


def test_runner_writes_summary_json(fake_news, runs_dir):
    runner = runmod.BacktestRunner()
    runner.run(
        start=date(2024, 3, 11), end=date(2024, 3, 15),
        run_id="test-write",
    )
    p = runs_dir / "test-write" / "summary.json"
    assert p.exists()
    import json
    payload = json.loads(p.read_text())
    assert payload["run_id"] == "test-write"
    assert payload["business_days"] == 5
    assert payload["pipeline_fires"] >= 3


def test_stub_score_keyword_rules():
    """Smoke test the stub scorer's rule table — Phase 3 will replace it."""
    from castelino.backtest.news_archive import HistoricalHeadline
    h = [
        HistoricalHeadline(date=datetime(2024, 1, 1, tzinfo=UTC),
            source="nyt", headline="Fed minutes hint at cuts",
            abstract="", url="x"),
        HistoricalHeadline(date=datetime(2024, 1, 1, tzinfo=UTC),
            source="nyt", headline="Bank panic spreads to regional lenders",
            abstract="", url="y"),
        HistoricalHeadline(date=datetime(2024, 1, 1, tzinfo=UTC),
            source="sonar_trump", headline="Trump threatens new tariff",
            abstract="", url="z"),
        HistoricalHeadline(date=datetime(2024, 1, 1, tzinfo=UTC),
            source="nyt", headline="Markets quietly close",
            abstract="", url="w"),
    ]
    scores = runmod.stub_score(h)
    assert scores[0].materiality >= 0.7      # Fed
    assert scores[1].materiality >= 0.9      # panic
    assert scores[2].materiality >= 0.7      # Trump/tariff
    assert scores[3].materiality < 0.5       # quiet


def test_runner_uses_injected_callables(fake_news, runs_dir):
    """Verify Phase 3 can swap the trigger / fire functions cleanly."""
    seen: list[date] = []
    def custom_trigger(d, scores):
        seen.append(d)
        # Always fire on Wed only, single path "custom"
        if d.weekday() == 2:
            return runmod.TriggerCandidate(
                date=d, path="custom", headline="forced",
                materiality=0.8,
            )
        return None
    def custom_fire(d, trigger, scores):
        return True

    runner = runmod.BacktestRunner(
        trigger_fn=custom_trigger, fire_fn=custom_fire,
    )
    summary = runner.run(
        start=date(2024, 3, 11), end=date(2024, 3, 15),
        run_id="test-inject",
    )
    assert summary.triggers_by_path == {"custom": 1}
    assert len(seen) == 5
