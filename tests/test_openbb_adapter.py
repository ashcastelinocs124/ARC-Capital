"""Tests for the OpenBB adapter module.

All tests mock the OpenBB SDK — no live network calls. Validates:
- Graceful degradation when PAT is missing or package uninstalled
- Correct error propagation via OpenBBError
- Data transformation from SDK responses to our domain types
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from castelino.data.openbb_adapter import (
    OBBPrice,
    OpenBBAdapter,
    OpenBBError,
    get_adapter,
    reset_adapter,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Ensure each test gets a fresh adapter instance."""
    reset_adapter()
    yield
    reset_adapter()


@pytest.fixture()
def adapter_no_pat(monkeypatch: pytest.MonkeyPatch) -> OpenBBAdapter:
    """An adapter with no OpenBB credentials configured."""
    monkeypatch.delenv("OPENBB_PAT", raising=False)
    # Simulate empty credentials — the OpenBB Platform v2+ always imports
    # successfully, so we patch the credentials object to have no fields.
    try:
        from openbb import obb

        mock_creds = MagicMock()
        mock_creds.model_fields = {}
        monkeypatch.setattr(obb.user, "credentials", mock_creds)
    except ImportError:
        pass
    return OpenBBAdapter()


@pytest.fixture()
def mock_obb():
    """A mock OpenBB SDK (obb) object with pre-configured responses."""
    obb_mock = MagicMock()
    # Configure default quote response
    quote_result = MagicMock()
    quote_record = MagicMock()
    quote_record.model_dump.return_value = {
        "last_price": 150.25,
        "date": "2025-01-15",
        "symbol": "AAPL",
    }
    quote_result.results = [quote_record]
    obb_mock.equity.price.quote.return_value = quote_result

    # Configure default historical response
    hist_result = MagicMock()
    hist_record_1 = MagicMock()
    hist_record_1.model_dump.return_value = {
        "date": "2025-01-14",
        "open": 149.0,
        "high": 151.0,
        "low": 148.5,
        "close": 150.0,
        "volume": 1000000,
    }
    hist_record_2 = MagicMock()
    hist_record_2.model_dump.return_value = {
        "date": "2025-01-15",
        "open": 150.0,
        "high": 152.0,
        "low": 149.5,
        "close": 151.5,
        "volume": 1200000,
    }
    hist_result.results = [hist_record_1, hist_record_2]
    obb_mock.equity.price.historical.return_value = hist_result

    # Configure default technical indicator responses
    rsi_result = MagicMock()
    rsi_record = MagicMock()
    rsi_record.model_dump.return_value = {"date": "2025-01-15", "rsi": 55.3}
    rsi_result.results = [rsi_record]
    obb_mock.technical.rsi.return_value = rsi_result

    macd_result = MagicMock()
    macd_record = MagicMock()
    macd_record.model_dump.return_value = {
        "date": "2025-01-15",
        "macd": 1.5,
        "signal": 1.2,
        "histogram": 0.3,
    }
    macd_result.results = [macd_record]
    obb_mock.technical.macd.return_value = macd_result

    bbands_result = MagicMock()
    bbands_record = MagicMock()
    bbands_record.model_dump.return_value = {
        "date": "2025-01-15",
        "upper": 155.0,
        "middle": 150.0,
        "lower": 145.0,
    }
    bbands_result.results = [bbands_record]
    obb_mock.technical.bbands.return_value = bbands_result

    return obb_mock


@pytest.fixture()
def adapter_with_sdk(monkeypatch: pytest.MonkeyPatch, mock_obb: MagicMock) -> OpenBBAdapter:
    """An adapter with a mocked SDK available."""
    monkeypatch.setenv("OPENBB_PAT", "test-pat-token")
    adapter = OpenBBAdapter()
    # Bypass the real import by directly setting internal state
    adapter._sdk = mock_obb
    adapter._available = True
    return adapter


# ---------------------------------------------------------------------------
# Test: Initialization / availability
# ---------------------------------------------------------------------------


class TestAdapterInitialization:
    """Tests for adapter initialization and availability detection."""

    def test_unavailable_when_no_pat(self, adapter_no_pat: OpenBBAdapter):
        """Adapter reports unavailable when OPENBB_PAT is not set."""
        assert adapter_no_pat.available is False

    def test_unavailable_when_pat_is_empty(self, monkeypatch: pytest.MonkeyPatch):
        """Adapter reports unavailable when OPENBB_PAT is empty string and no platform credentials."""
        monkeypatch.setenv("OPENBB_PAT", "   ")
        try:
            from openbb import obb

            mock_creds = MagicMock()
            mock_creds.model_fields = {}
            monkeypatch.setattr(obb.user, "credentials", mock_creds)
        except ImportError:
            pass
        adapter = OpenBBAdapter()
        assert adapter.available is False

    def test_unavailable_when_import_fails(self, monkeypatch: pytest.MonkeyPatch):
        """Adapter reports unavailable when openbb import raises ImportError."""
        monkeypatch.setenv("OPENBB_PAT", "valid-token")
        with patch.dict("sys.modules", {"openbb": None}):
            with patch(
                "castelino.data.openbb_adapter.OpenBBAdapter._try_init",
                return_value=False,
            ):
                adapter = OpenBBAdapter()
                assert adapter.available is False

    def test_available_with_working_sdk(self, adapter_with_sdk: OpenBBAdapter):
        """Adapter reports available when SDK is properly configured."""
        assert adapter_with_sdk.available is True

    def test_singleton_get_adapter(self, monkeypatch: pytest.MonkeyPatch):
        """get_adapter() returns the same instance on repeated calls."""
        monkeypatch.delenv("OPENBB_PAT", raising=False)
        a1 = get_adapter()
        a2 = get_adapter()
        assert a1 is a2

    def test_reset_adapter_clears_singleton(self, monkeypatch: pytest.MonkeyPatch):
        """reset_adapter() causes get_adapter() to return a new instance."""
        monkeypatch.delenv("OPENBB_PAT", raising=False)
        a1 = get_adapter()
        reset_adapter()
        a2 = get_adapter()
        assert a1 is not a2


# ---------------------------------------------------------------------------
# Test: Error propagation when unavailable
# ---------------------------------------------------------------------------


class TestUnavailableErrors:
    """All public methods must raise OpenBBError when SDK is unavailable."""

    def test_latest_price_raises(self, adapter_no_pat: OpenBBAdapter):
        with pytest.raises(OpenBBError, match="not available"):
            adapter_no_pat.latest_price("AAPL")

    def test_history_raises(self, adapter_no_pat: OpenBBAdapter):
        with pytest.raises(OpenBBError, match="not available"):
            adapter_no_pat.history("AAPL")

    def test_technical_indicators_raises(self, adapter_no_pat: OpenBBAdapter):
        with pytest.raises(OpenBBError, match="not available"):
            adapter_no_pat.technical_indicators("AAPL")

    def test_income_statement_raises(self, adapter_no_pat: OpenBBAdapter):
        with pytest.raises(OpenBBError, match="not available"):
            adapter_no_pat.income_statement("AAPL")

    def test_balance_sheet_raises(self, adapter_no_pat: OpenBBAdapter):
        with pytest.raises(OpenBBError, match="not available"):
            adapter_no_pat.balance_sheet("AAPL")

    def test_analyst_estimates_raises(self, adapter_no_pat: OpenBBAdapter):
        with pytest.raises(OpenBBError, match="not available"):
            adapter_no_pat.analyst_estimates("AAPL")

    def test_earnings_calendar_raises(self, adapter_no_pat: OpenBBAdapter):
        with pytest.raises(OpenBBError, match="not available"):
            adapter_no_pat.earnings_calendar()

    def test_screen_equities_raises(self, adapter_no_pat: OpenBBAdapter):
        with pytest.raises(OpenBBError, match="not available"):
            adapter_no_pat.screen_equities()

    def test_sector_performance_raises(self, adapter_no_pat: OpenBBAdapter):
        with pytest.raises(OpenBBError, match="not available"):
            adapter_no_pat.sector_performance()

    def test_correlation_matrix_raises(self, adapter_no_pat: OpenBBAdapter):
        with pytest.raises(OpenBBError, match="not available"):
            adapter_no_pat.correlation_matrix(["AAPL", "MSFT"])

    def test_economic_indicators_raises(self, adapter_no_pat: OpenBBAdapter):
        with pytest.raises(OpenBBError, match="not available"):
            adapter_no_pat.economic_indicators(["GDP"])

    def test_economic_calendar_raises(self, adapter_no_pat: OpenBBAdapter):
        with pytest.raises(OpenBBError, match="not available"):
            adapter_no_pat.economic_calendar()

    def test_yield_curve_raises(self, adapter_no_pat: OpenBBAdapter):
        with pytest.raises(OpenBBError, match="not available"):
            adapter_no_pat.yield_curve()

    def test_news_raises(self, adapter_no_pat: OpenBBAdapter):
        with pytest.raises(OpenBBError, match="not available"):
            adapter_no_pat.news()


# ---------------------------------------------------------------------------
# Test: Pricing (with mocked SDK)
# ---------------------------------------------------------------------------


class TestLatestPrice:
    """Tests for latest_price() with a mocked SDK."""

    def test_returns_obb_price(self, adapter_with_sdk: OpenBBAdapter):
        """latest_price returns a well-formed OBBPrice dataclass."""
        result = adapter_with_sdk.latest_price("AAPL")
        assert isinstance(result, OBBPrice)
        assert result.instrument_id == "AAPL"
        assert result.price == 150.25
        assert isinstance(result.asof, datetime)

    def test_raises_on_empty_response(self, adapter_with_sdk: OpenBBAdapter):
        """latest_price raises OpenBBError when SDK returns no data."""
        adapter_with_sdk._sdk.equity.price.quote.return_value.results = []
        with pytest.raises(OpenBBError, match="No quote data"):
            adapter_with_sdk.latest_price("FAKE")

    def test_raises_on_sdk_exception(self, adapter_with_sdk: OpenBBAdapter):
        """latest_price wraps SDK exceptions in OpenBBError."""
        adapter_with_sdk._sdk.equity.price.quote.side_effect = RuntimeError("API down")
        with pytest.raises(OpenBBError, match="Failed to fetch latest price"):
            adapter_with_sdk.latest_price("AAPL")

    def test_obb_price_is_frozen(self, adapter_with_sdk: OpenBBAdapter):
        """OBBPrice instances are immutable (frozen dataclass)."""
        result = adapter_with_sdk.latest_price("AAPL")
        with pytest.raises(AttributeError):
            result.price = 999.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Test: History (with mocked SDK)
# ---------------------------------------------------------------------------


class TestHistory:
    """Tests for history() with a mocked SDK."""

    def test_returns_dataframe(self, adapter_with_sdk: OpenBBAdapter):
        """history returns a DataFrame with expected OHLCV columns."""
        df = adapter_with_sdk.history("AAPL", lookback_days=30)
        assert isinstance(df, pd.DataFrame)
        assert "close" in df.columns
        assert "open" in df.columns
        assert "high" in df.columns
        assert "low" in df.columns
        assert "volume" in df.columns
        assert len(df) == 2

    def test_index_is_datetime(self, adapter_with_sdk: OpenBBAdapter):
        """history DataFrame is indexed by datetime."""
        df = adapter_with_sdk.history("AAPL", lookback_days=30)
        assert df.index.name == "date"
        assert pd.api.types.is_datetime64_any_dtype(df.index)

    def test_raises_on_empty_response(self, adapter_with_sdk: OpenBBAdapter):
        """history raises OpenBBError when SDK returns no data."""
        adapter_with_sdk._sdk.equity.price.historical.return_value.results = []
        with pytest.raises(OpenBBError, match="No history data"):
            adapter_with_sdk.history("FAKE")

    def test_raises_on_sdk_exception(self, adapter_with_sdk: OpenBBAdapter):
        """history wraps SDK exceptions in OpenBBError."""
        adapter_with_sdk._sdk.equity.price.historical.side_effect = RuntimeError("timeout")
        with pytest.raises(OpenBBError, match="Failed to fetch history"):
            adapter_with_sdk.history("AAPL")


# ---------------------------------------------------------------------------
# Test: Technical Indicators (with mocked SDK)
# ---------------------------------------------------------------------------


class TestTechnicalIndicators:
    """Tests for technical_indicators() with a mocked SDK."""

    def test_returns_dict_with_indicators(self, adapter_with_sdk: OpenBBAdapter):
        """technical_indicators returns a dict mapping indicator name to data."""
        result = adapter_with_sdk.technical_indicators("AAPL")
        assert isinstance(result, dict)
        assert "rsi" in result
        assert "macd" in result
        assert "bbands" in result

    def test_rsi_data_correct(self, adapter_with_sdk: OpenBBAdapter):
        """RSI data is correctly extracted."""
        result = adapter_with_sdk.technical_indicators("AAPL", indicators=["rsi"])
        assert "rsi" in result
        assert result["rsi"][0]["rsi"] == 55.3

    def test_custom_indicator_list(self, adapter_with_sdk: OpenBBAdapter):
        """Only requested indicators are computed."""
        result = adapter_with_sdk.technical_indicators("AAPL", indicators=["macd"])
        assert "macd" in result
        assert "rsi" not in result
        assert "bbands" not in result

    def test_unknown_indicator_skipped(self, adapter_with_sdk: OpenBBAdapter):
        """Unknown indicators are silently skipped (logged as warning)."""
        result = adapter_with_sdk.technical_indicators("AAPL", indicators=["rsi", "unknown_ind"])
        assert "rsi" in result
        assert "unknown_ind" not in result

    def test_raises_on_sdk_exception(self, adapter_with_sdk: OpenBBAdapter):
        """technical_indicators wraps SDK exceptions in OpenBBError."""
        adapter_with_sdk._sdk.technical.rsi.side_effect = RuntimeError("API error")
        with pytest.raises(OpenBBError, match="Failed to compute technical"):
            adapter_with_sdk.technical_indicators("AAPL", indicators=["rsi"])


# ---------------------------------------------------------------------------
# Test: Moving Averages
# ---------------------------------------------------------------------------


class TestMovingAverages:
    """Tests for moving_averages() — uses history under the hood."""

    def test_returns_sma_columns(self, adapter_with_sdk: OpenBBAdapter):
        """moving_averages returns DataFrame with sma_N columns."""
        # Need enough data for the rolling window; mock returns 2 rows only
        # so SMA values will be NaN for larger windows, but structure is correct
        result = adapter_with_sdk.moving_averages("AAPL", windows=[1, 2])
        assert isinstance(result, pd.DataFrame)
        assert "sma_1" in result.columns
        assert "sma_2" in result.columns

    def test_default_windows(self, adapter_with_sdk: OpenBBAdapter):
        """Default windows are [20, 50, 200]."""
        result = adapter_with_sdk.moving_averages("AAPL")
        assert "sma_20" in result.columns
        assert "sma_50" in result.columns
        assert "sma_200" in result.columns


# ---------------------------------------------------------------------------
# Test: Helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    """Tests for internal helper methods."""

    def test_extract_results_none(self):
        """_extract_results handles None gracefully."""
        assert OpenBBAdapter._extract_results(None) == []

    def test_extract_results_empty_list(self):
        """_extract_results handles empty results list."""
        result = MagicMock()
        result.results = []
        assert OpenBBAdapter._extract_results(result) == []

    def test_extract_results_with_model_dump(self):
        """_extract_results calls model_dump on Pydantic-style records."""
        record = MagicMock()
        record.model_dump.return_value = {"key": "value"}
        result = MagicMock()
        result.results = [record]
        assert OpenBBAdapter._extract_results(result) == [{"key": "value"}]

    def test_parse_datetime_string(self):
        """_parse_datetime handles ISO date strings."""
        dt = OpenBBAdapter._parse_datetime("2025-01-15")
        assert dt == datetime(2025, 1, 15)

    def test_parse_datetime_datetime(self):
        """_parse_datetime passes through datetime objects."""
        now = datetime(2025, 1, 15, 10, 30, 0)
        assert OpenBBAdapter._parse_datetime(now) is now

    def test_parse_datetime_fallback(self):
        """_parse_datetime returns current time for unparseable values."""
        dt = OpenBBAdapter._parse_datetime(12345)  # int — unparseable
        assert isinstance(dt, datetime)
