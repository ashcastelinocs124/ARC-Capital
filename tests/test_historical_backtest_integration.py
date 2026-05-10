"""Phase-3 tests: production score / trigger callables."""
from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import patch

import pytest

from castelino.backtest import integration as ig
from castelino.backtest.news_archive import HistoricalHeadline
from castelino.backtest.runner import HeadlineScore as BTScore
from castelino.triggers.significance import HeadlineScore as ProdScore


@pytest.fixture(autouse=True)
def _reset_state():
    ig.reset_state()
    yield
    ig.reset_state()


def _hh(headline: str, *, source: str = "nyt", url: str | None = None) -> HistoricalHeadline:
    return HistoricalHeadline(
        date=datetime(2024, 3, 15, 10, 0, tzinfo=UTC),
        source=source, headline=headline, abstract="",
        url=url or f"https://test/{headline[:20].replace(' ', '_')}",
    )


def test_historical_to_news_headline_preserves_metadata():
    h = HistoricalHeadline(
        date=datetime(2024, 1, 5, 12, tzinfo=UTC),
        source="sonar_trump", headline="Trump tariff threat",
        abstract="rally remarks", url="https://x/1",
    )
    n = ig.historical_to_news_headline(h)
    assert n.title == "Trump tariff threat"
    assert n.summary == "rally remarks"
    assert n.source == "sonar_trump"
    assert n.published == h.date
    assert len(n.id) >= 8  # stable hash


def test_real_score_fn_empty_headlines_short_circuits():
    """No LLM call when input is empty."""
    with patch.object(ig, "score_batch") as mock_sb:
        out = ig.real_score_fn([])
        assert out == []
        mock_sb.assert_not_called()


def test_real_score_fn_pipes_through_score_batch_and_readiness():
    headlines = [_hh("Fed minutes signal patience"), _hh("CPI cooler than expected")]
    fake_prod = [
        ProdScore(headline_id=ig.historical_to_news_headline(headlines[0]).id,
                  title="Fed minutes signal patience",
                  materiality=0.78, asset_classes_affected=["bond_etf"],
                  one_sentence_reason="dovish read"),
        ProdScore(headline_id=ig.historical_to_news_headline(headlines[1]).id,
                  title="CPI cooler than expected", materiality=0.82,
                  asset_classes_affected=["bond_etf"],
                  one_sentence_reason="disinflation continues"),
    ]
    with patch.object(ig, "score_batch", return_value=fake_prod) as mock_sb, \
         patch.object(ig, "apply_readiness", side_effect=lambda x: x) as mock_ar, \
         patch("castelino.backtest.integration.conv.append") as mock_conv:
        out = ig.real_score_fn(headlines)
        mock_sb.assert_called_once()
        mock_ar.assert_called_once()
        assert mock_conv.call_count == 2
        assert [s.materiality for s in out] == [0.78, 0.82]
        assert all(isinstance(s, BTScore) for s in out)
        assert out[0].source == "nyt"  # source is propagated through


def test_real_trigger_fn_black_swan_priority():
    scores = [
        BTScore(headline="Bank panic spreads", materiality=0.95, source="nyt"),
        BTScore(headline="Fed minutes", materiality=0.75, source="nyt"),
    ]
    out = ig.real_trigger_fn(date(2024, 3, 15), scores)
    assert out is not None
    assert out.path == "black_swan"
    assert out.materiality == 0.95


def test_real_trigger_fn_news_threshold():
    scores = [BTScore(headline="Fed minutes", materiality=0.78, source="nyt")]
    out = ig.real_trigger_fn(date(2024, 3, 15), scores)
    assert out is not None and out.path == "news"


def test_real_trigger_fn_below_threshold_no_fire_unless_cron():
    """Mat < 0.7 alone won't fire news — but cron may still fire on the very
    first tick (no prior fire). Then cooldown applies."""
    scores = [BTScore(headline="quiet day", materiality=0.4, source="nyt")]
    first = ig.real_trigger_fn(date(2024, 3, 15), scores)
    # First tick with no prior fire and no high materiality → cron fallback
    assert first is None or first.path == "cron"
    # Second tick same day window — cooldown means no cron retrigger
    second = ig.real_trigger_fn(date(2024, 3, 15), scores)
    if first is not None:
        assert second is None


def test_real_trigger_fn_cooldown_prevents_immediate_refire():
    """A black-swan fire on day d should suppress the conviction path on the
    same simulated day even if the ledger says fire."""
    high = [BTScore(headline="Bank default", materiality=0.93, source="nyt")]
    low = [BTScore(headline="quiet", materiality=0.3, source="nyt")]
    a = ig.real_trigger_fn(date(2024, 3, 15), high)
    assert a is not None and a.path == "black_swan"

    # Mock conviction.check_fire to claim it WOULD fire — cooldown should win
    from castelino.triggers.conviction import ConvictionFireResult
    with patch("castelino.backtest.integration.conv.check_fire") as mock_cf:
        mock_cf.return_value = ConvictionFireResult(
            should_fire=True, reason="strong bullish growth",
            snapshot=None, contributing_headlines=[],
        )
        b = ig.real_trigger_fn(date(2024, 3, 15), low)
        # Within same-day cooldown window, conviction is suppressed
        # Only cron may fire if elapsed > cron threshold (it isn't here)
        assert b is None or b.path == "cron"
