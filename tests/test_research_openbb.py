"""Tests for OpenBB integration in research agents."""

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from castelino.agents.research.technical import _compute_ta_openbb


def test_openbb_ta_returns_none_when_unavailable():
    """When adapter.available is False, _compute_ta_openbb returns None."""
    mock_adapter = MagicMock()
    mock_adapter.available = False
    with patch(
        "castelino.agents.research.technical.get_adapter", return_value=mock_adapter
    ):
        result = _compute_ta_openbb("SPY")
    assert result is None


def test_openbb_ta_returns_features_when_available():
    """When adapter provides valid data, features are computed correctly."""
    mock_adapter = MagicMock()
    mock_adapter.available = True

    # Mock history — 60 daily closes
    closes = np.linspace(440, 452, 60)
    hist_df = pd.DataFrame(
        {"close": closes, "open": closes - 1, "high": closes + 1, "low": closes - 2},
        index=pd.date_range("2026-03-01", periods=60),
    )
    mock_adapter.history.return_value = hist_df

    # Mock technical_indicators — returns list[dict] per _extract_results
    rsi_data = [{"rsi_14": 65.0}, {"rsi_14": 66.0}, {"rsi_14": 67.0}]
    mock_adapter.technical_indicators.return_value = {"rsi": rsi_data}

    with patch(
        "castelino.agents.research.technical.get_adapter", return_value=mock_adapter
    ):
        result = _compute_ta_openbb("SPY")

    assert result is not None
    assert result.instrument_id == "SPY"
    assert result.last_close == pytest.approx(452.0, rel=1e-3)
    # sma_50 = mean of last 50 closes
    expected_sma_50 = float(pd.Series(closes).tail(50).mean())
    assert result.sma_50 == pytest.approx(expected_sma_50, rel=1e-3)
    assert result.rsi_14 == pytest.approx(67.0, rel=1e-3)
    assert result.key_support == pytest.approx(float(min(closes)), rel=1e-3)
    assert result.key_resistance == pytest.approx(float(max(closes)), rel=1e-3)
    assert result.realized_vol_30d > 0  # non-zero for linearly increasing series


def test_openbb_ta_returns_none_on_error():
    """When adapter raises an exception, function returns None gracefully."""
    mock_adapter = MagicMock()
    mock_adapter.available = True
    mock_adapter.history.side_effect = Exception("network error")

    with patch(
        "castelino.agents.research.technical.get_adapter", return_value=mock_adapter
    ):
        result = _compute_ta_openbb("SPY")
    assert result is None


def test_openbb_ta_returns_none_on_empty_history():
    """When history returns an empty DataFrame, function returns None."""
    mock_adapter = MagicMock()
    mock_adapter.available = True
    mock_adapter.history.return_value = pd.DataFrame()

    with patch(
        "castelino.agents.research.technical.get_adapter", return_value=mock_adapter
    ):
        result = _compute_ta_openbb("SPY")
    assert result is None


def test_openbb_ta_rsi_fallback_on_indicator_error():
    """When technical_indicators fails, RSI falls back to manual computation."""
    mock_adapter = MagicMock()
    mock_adapter.available = True

    # Provide enough history for RSI(14) manual computation with realistic
    # up/down movements (random walk with upward drift)
    rng = np.random.default_rng(42)
    daily_returns = rng.normal(loc=0.005, scale=0.015, size=60)
    closes = 440.0 * np.cumprod(1 + daily_returns)
    hist_df = pd.DataFrame(
        {"close": closes, "open": closes * 0.999, "high": closes * 1.005, "low": closes * 0.995},
        index=pd.date_range("2026-03-01", periods=60),
    )
    mock_adapter.history.return_value = hist_df

    # Make technical_indicators raise
    from castelino.data.openbb_adapter import OpenBBError

    mock_adapter.technical_indicators.side_effect = OpenBBError("API unavailable")

    with patch(
        "castelino.agents.research.technical.get_adapter", return_value=mock_adapter
    ):
        result = _compute_ta_openbb("SPY")

    assert result is not None
    # RSI should be computed manually — with drift and variance it won't be exactly 50
    assert 0 < result.rsi_14 < 100
    # With a positive drift of 0.5% daily, RSI should be above 50
    assert result.rsi_14 > 50


class TestCorrelationOpenBB:
    """Tests for the OpenBB correlation helper in risk.py."""

    def test_correlation_returns_none_when_unavailable(self):
        from castelino.agents.research.risk import _correlation_openbb

        mock_adapter = MagicMock()
        mock_adapter.available = False
        with patch(
            "castelino.agents.research.risk.get_adapter", return_value=mock_adapter
        ):
            result = _correlation_openbb(["SPY", "QQQ"])
        assert result is None

    def test_correlation_returns_dataframe_when_available(self):
        from castelino.agents.research.risk import _correlation_openbb

        mock_adapter = MagicMock()
        mock_adapter.available = True
        corr_df = pd.DataFrame(
            [[1.0, 0.85], [0.85, 1.0]],
            columns=["SPY", "QQQ"],
            index=["SPY", "QQQ"],
        )
        mock_adapter.correlation_matrix.return_value = corr_df

        with patch(
            "castelino.agents.research.risk.get_adapter", return_value=mock_adapter
        ):
            result = _correlation_openbb(["SPY", "QQQ"])
        assert result is not None
        assert result.loc["SPY", "QQQ"] == pytest.approx(0.85)

    def test_correlation_returns_none_on_error(self):
        from castelino.agents.research.risk import _correlation_openbb

        mock_adapter = MagicMock()
        mock_adapter.available = True
        mock_adapter.correlation_matrix.side_effect = Exception("timeout")

        with patch(
            "castelino.agents.research.risk.get_adapter", return_value=mock_adapter
        ):
            result = _correlation_openbb(["SPY", "QQQ"])
        assert result is None


class TestWebOpenBBNews:
    """Tests for the OpenBB news helper in web.py."""

    def test_fetch_news_returns_empty_when_unavailable(self):
        from castelino.agents.research.web import _fetch_openbb_news

        mock_adapter = MagicMock()
        mock_adapter.available = False
        with patch(
            "castelino.agents.research.web.get_adapter", return_value=mock_adapter
        ):
            result = _fetch_openbb_news("SPY")
        assert result == []

    def test_fetch_news_returns_titles_when_available(self):
        from castelino.agents.research.web import _fetch_openbb_news

        mock_adapter = MagicMock()
        mock_adapter.available = True
        mock_adapter.news.return_value = [
            {"title": "SPY hits all-time high", "date": "2026-05-05"},
            {"title": "Fed holds rates steady", "date": "2026-05-04"},
            {"title": "", "date": "2026-05-03"},  # empty title — should be filtered
        ]

        with patch(
            "castelino.agents.research.web.get_adapter", return_value=mock_adapter
        ):
            result = _fetch_openbb_news("SPY", limit=5)
        assert result == ["SPY hits all-time high", "Fed holds rates steady"]

    def test_fetch_news_returns_empty_on_error(self):
        from castelino.agents.research.web import _fetch_openbb_news

        mock_adapter = MagicMock()
        mock_adapter.available = True
        mock_adapter.news.side_effect = Exception("API error")

        with patch(
            "castelino.agents.research.web.get_adapter", return_value=mock_adapter
        ):
            result = _fetch_openbb_news("SPY")
        assert result == []
