"""Phase-1 tests: historical news archive read + merge."""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from castelino.backtest import news_archive as na


@pytest.fixture
def fake_archive(monkeypatch, tmp_path):
    # The window is [end-of-day(d) - window_hours, end-of-day(d)].
    # For d=2024-03-15 with window_hours=24, that's
    #   [2024-03-14 23:59:59.999, 2024-03-15 23:59:59.999].
    df = pd.DataFrame([
        {"date": pd.Timestamp("2024-03-15 09:00"), "source": "nyt",
         "headline": "Fed minutes signal patience",
         "abstract": "Members favor holding.", "url": "https://nyt/a"},
        {"date": pd.Timestamp("2024-03-15 18:30"), "source": "sonar_trump",
         "headline": "Trump threatens 60% China tariff",
         "abstract": "Campaign rally remarks.", "url": "https://sonar/a"},
        {"date": pd.Timestamp("2024-03-15 07:00"), "source": "nyt",
         "headline": "CPI cooler than expected",
         "abstract": "Headline 3.1% YoY.", "url": "https://nyt/b"},
        {"date": pd.Timestamp("2024-03-12 12:00"), "source": "nyt",
         "headline": "Old story three days back",
         "abstract": "Should be filtered out.", "url": "https://nyt/old"},
    ])
    p = tmp_path / "historical_news.parquet"
    df.to_parquet(p)
    monkeypatch.setattr(na, "historical_news_path", lambda: p)
    na.clear_cache()
    yield p
    na.clear_cache()


def test_headlines_for_24h_window(fake_archive):
    out = na.headlines_for(date(2024, 3, 15), window_hours=24)
    sources = sorted({h.source for h in out})
    headlines = [h.headline for h in out]
    assert "CPI cooler than expected" in headlines
    assert "Trump threatens 60% China tariff" in headlines
    assert "Fed minutes signal patience" in headlines
    assert "Old story three days back" not in headlines
    assert sources == ["nyt", "sonar_trump"]


def test_headlines_for_no_match_returns_empty(fake_archive):
    out = na.headlines_for(date(2025, 1, 1))
    assert out == []


def test_headlines_for_sorted_desc_by_date(fake_archive):
    out = na.headlines_for(date(2024, 3, 15))
    assert [h.date for h in out] == sorted(
        [h.date for h in out], reverse=True,
    )


def test_headlines_for_respects_max_items(fake_archive):
    out = na.headlines_for(date(2024, 3, 15), window_hours=24 * 30, max_items=2)
    assert len(out) == 2


def test_merge_source_archives_dedups_by_source_url():
    a = pd.DataFrame([
        {"date": pd.Timestamp("2024-01-01"), "source": "nyt",
         "headline": "Same article", "abstract": "v1", "url": "https://x/1"},
    ])
    b = pd.DataFrame([
        {"date": pd.Timestamp("2024-01-01"), "source": "nyt",
         "headline": "Same article (re-pulled)", "abstract": "v2", "url": "https://x/1"},
        {"date": pd.Timestamp("2024-01-02"), "source": "sonar_trump",
         "headline": "Different source same url", "abstract": "v3", "url": "https://x/1"},
    ])
    merged = na.merge_source_archives([a, b])
    # First-write-wins on (source, url); the sonar_trump row coexists since source differs
    assert len(merged) == 2
    assert set(merged["source"]) == {"nyt", "sonar_trump"}
    nyt_row = merged[merged["source"] == "nyt"].iloc[0]
    assert nyt_row["headline"] == "Same article"


def test_merge_source_archives_empty():
    out = na.merge_source_archives([])
    assert list(out.columns) == sorted(na.REQUIRED_COLUMNS)
    assert len(out) == 0


def test_merge_source_archives_rejects_bad_schema():
    bad = pd.DataFrame([{"date": pd.Timestamp("2024-01-01"), "headline": "x"}])
    with pytest.raises(na.NewsArchiveError, match="missing columns"):
        na.merge_source_archives([bad])
