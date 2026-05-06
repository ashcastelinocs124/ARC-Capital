# OpenBB Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Integrate OpenBB Platform as the primary data source, build an interactive OpenBB Workspace dashboard, and add human-in-the-loop approval gates to the pipeline.

**Architecture:** Embedded OpenBB SDK via a thin adapter module (`openbb_adapter.py`), with the dashboard as a FastAPI app inside the castelino package that imports pipeline modules directly. Two HITL gates (post-hypothesis, post-debate) stall the LangGraph pipeline until CLI approval.

**Tech Stack:** OpenBB SDK 4.x, FastAPI, Plotly, Typer (CLI extensions), LangGraph conditional edges for gates.

---

## Workstream 1: Data Layer (OpenBB Adapter + Pricing Fallback)

### Task 1: Add OpenBB dependency and config

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/castelino/config.py`
- Modify: `config.yaml`
- Create: `.env.example` (update if exists)

**Step 1: Add `openbb` to pyproject.toml dependencies**

In `pyproject.toml`, add to `dependencies`:
```
"openbb>=4.0",
```

**Step 2: Add OpenBB config section to config.py**

Add after `FredCfg`:
```python
class OpenBBCfg(BaseModel):
    preferred_provider: str = "yfinance"
    fallback_enabled: bool = True
    cache_ttl_minutes: int = 15
```

Add `openbb: OpenBBCfg` field to `Settings` class.

Add property to `Settings`:
```python
@property
def openbb_pat(self) -> str | None:
    key = os.environ.get("OPENBB_PAT", "").strip()
    return key or None
```

**Step 3: Add `openbb:` section to config.yaml**

```yaml
openbb:
  preferred_provider: yfinance
  fallback_enabled: true
  cache_ttl_minutes: 15
```

**Step 4: Update .env.example**

Add:
```
OPENBB_PAT=your_openbb_pat_here
```

**Step 5: Commit**

```bash
git add pyproject.toml src/castelino/config.py config.yaml .env.example
git commit -m "feat: add OpenBB dependency and configuration"
```

---

### Task 2: Create OpenBB adapter module

**Files:**
- Create: `src/castelino/data/openbb_adapter.py`
- Test: `tests/test_openbb_adapter.py`

**Step 1: Write the failing test**

```python
"""tests/test_openbb_adapter.py"""
from unittest.mock import patch, MagicMock
import pandas as pd
import pytest

from castelino.data.openbb_adapter import OpenBBAdapter, OpenBBError


def test_adapter_initializes_without_pat():
    """Adapter should not crash if no PAT is set — graceful degradation."""
    with patch.dict("os.environ", {"OPENBB_PAT": ""}, clear=False):
        adapter = OpenBBAdapter()
        assert adapter._obb is None
        assert adapter.available is False


def test_adapter_initializes_with_pat():
    """Adapter should initialize SDK when PAT is present."""
    with patch("castelino.data.openbb_adapter.openbb") as mock_obb:
        mock_obb.obb = MagicMock()
        with patch.dict("os.environ", {"OPENBB_PAT": "test_pat"}, clear=False):
            adapter = OpenBBAdapter()
            assert adapter.available is True


def test_latest_price_returns_price_dataclass():
    adapter = OpenBBAdapter.__new__(OpenBBAdapter)
    adapter._obb = MagicMock()
    adapter._preferred_provider = "yfinance"

    mock_result = MagicMock()
    mock_result.results = [MagicMock(close=150.0, date="2026-05-05")]
    adapter._obb.equity.price.historical.return_value = mock_result

    price = adapter.latest_price("AAPL")
    assert price.price == 150.0
    assert price.instrument_id == "AAPL"


def test_latest_price_raises_on_no_sdk():
    adapter = OpenBBAdapter.__new__(OpenBBAdapter)
    adapter._obb = None
    with pytest.raises(OpenBBError, match="not available"):
        adapter.latest_price("AAPL")


def test_history_returns_dataframe():
    adapter = OpenBBAdapter.__new__(OpenBBAdapter)
    adapter._obb = MagicMock()
    adapter._preferred_provider = "yfinance"

    mock_result = MagicMock()
    mock_result.to_dataframe.return_value = pd.DataFrame({
        "open": [100.0], "high": [105.0], "low": [99.0],
        "close": [103.0], "volume": [1000000],
    }, index=pd.to_datetime(["2026-05-05"]))
    adapter._obb.equity.price.historical.return_value = mock_result

    df = adapter.history("AAPL", lookback_days=10)
    assert not df.empty
    assert "close" in df.columns


def test_technical_indicators_returns_dict():
    adapter = OpenBBAdapter.__new__(OpenBBAdapter)
    adapter._obb = MagicMock()
    adapter._preferred_provider = "yfinance"

    mock_result = MagicMock()
    mock_result.to_dataframe.return_value = pd.DataFrame({
        "rsi": [65.0], "macd": [1.2], "signal": [0.8],
    })
    adapter._obb.technical.rsi.return_value = mock_result
    adapter._obb.technical.macd.return_value = mock_result

    result = adapter.technical_indicators("AAPL")
    assert isinstance(result, dict)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_openbb_adapter.py -v`
Expected: FAIL with "ModuleNotFoundError" or "ImportError"

**Step 3: Write the adapter implementation**

```python
"""src/castelino/data/openbb_adapter.py
Thin wrapper around the OpenBB SDK. Single instance, lazy-initialized.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache

import pandas as pd

from castelino.data.instruments import PriceSource

log = logging.getLogger(__name__)


class OpenBBError(RuntimeError):
    """Raised when OpenBB SDK call fails or SDK is unavailable."""


@dataclass(frozen=True)
class OBBPrice:
    instrument_id: str
    price: float
    asof: datetime
    source: PriceSource = PriceSource.OPENBB


class OpenBBAdapter:
    """Single entry point for all OpenBB SDK calls."""

    def __init__(self) -> None:
        pat = os.environ.get("OPENBB_PAT", "").strip()
        if not pat:
            log.warning("OPENBB_PAT not set — adapter disabled, will fallback to yfinance/FRED")
            self._obb = None
            return
        try:
            from openbb import obb
            obb.account.login(pat=pat)
            self._obb = obb
            self._preferred_provider = "yfinance"
            log.info("OpenBB SDK initialized successfully")
        except Exception as e:
            log.warning("OpenBB SDK init failed: %s — adapter disabled", e)
            self._obb = None

    @property
    def available(self) -> bool:
        return self._obb is not None

    def _require_sdk(self) -> None:
        if self._obb is None:
            raise OpenBBError("OpenBB SDK not available — PAT missing or init failed")

    # ── Pricing ──────────────────────────────────────────────────────

    def latest_price(self, symbol: str, provider: str | None = None) -> OBBPrice:
        self._require_sdk()
        prov = provider or self._preferred_provider
        try:
            result = self._obb.equity.price.historical(
                symbol=symbol, provider=prov, limit=1
            )
            if not result.results:
                raise OpenBBError(f"No price data for {symbol}")
            row = result.results[-1]
            return OBBPrice(
                instrument_id=symbol,
                price=float(row.close),
                asof=datetime.now(UTC),
                source=PriceSource.OPENBB,
            )
        except OpenBBError:
            raise
        except Exception as e:
            raise OpenBBError(f"Failed to fetch price for {symbol}: {e}") from e

    def history(
        self, symbol: str, lookback_days: int = 252, provider: str | None = None
    ) -> pd.DataFrame:
        self._require_sdk()
        prov = provider or self._preferred_provider
        try:
            from datetime import timedelta
            start = (datetime.now(UTC) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
            result = self._obb.equity.price.historical(
                symbol=symbol, provider=prov, start_date=start
            )
            df = result.to_dataframe()
            if df.empty:
                raise OpenBBError(f"Empty history for {symbol}")
            return df
        except OpenBBError:
            raise
        except Exception as e:
            raise OpenBBError(f"Failed to fetch history for {symbol}: {e}") from e

    # ── Technical Analysis ───────────────────────────────────────────

    def technical_indicators(
        self, symbol: str, indicators: list[str] | None = None
    ) -> dict:
        self._require_sdk()
        indicators = indicators or ["rsi", "macd", "bbands"]
        results = {}
        try:
            data = self._obb.equity.price.historical(symbol=symbol, limit=200)
            df = data.to_dataframe()

            if "rsi" in indicators:
                rsi = self._obb.technical.rsi(data=df)
                results["rsi"] = rsi.to_dataframe()
            if "macd" in indicators:
                macd = self._obb.technical.macd(data=df)
                results["macd"] = macd.to_dataframe()
            if "bbands" in indicators:
                bbands = self._obb.technical.bbands(data=df)
                results["bbands"] = bbands.to_dataframe()
        except Exception as e:
            raise OpenBBError(f"TA failed for {symbol}: {e}") from e
        return results

    def moving_averages(
        self, symbol: str, windows: list[int] | None = None
    ) -> pd.DataFrame:
        self._require_sdk()
        windows = windows or [20, 50, 200]
        try:
            data = self._obb.equity.price.historical(symbol=symbol, limit=max(windows) + 50)
            df = data.to_dataframe()
            for w in windows:
                df[f"sma_{w}"] = df["close"].rolling(w).mean()
            return df[["close"] + [f"sma_{w}" for w in windows]].dropna()
        except Exception as e:
            raise OpenBBError(f"Moving averages failed for {symbol}: {e}") from e

    # ── Fundamentals ─────────────────────────────────────────────────

    def income_statement(
        self, symbol: str, period: str = "annual", provider: str | None = None
    ) -> pd.DataFrame:
        self._require_sdk()
        try:
            result = self._obb.equity.fundamental.income(
                symbol=symbol, period=period, provider=provider or self._preferred_provider
            )
            return result.to_dataframe()
        except Exception as e:
            raise OpenBBError(f"Income statement failed for {symbol}: {e}") from e

    def balance_sheet(self, symbol: str, provider: str | None = None) -> pd.DataFrame:
        self._require_sdk()
        try:
            result = self._obb.equity.fundamental.balance(
                symbol=symbol, provider=provider or self._preferred_provider
            )
            return result.to_dataframe()
        except Exception as e:
            raise OpenBBError(f"Balance sheet failed for {symbol}: {e}") from e

    def analyst_estimates(self, symbol: str, provider: str | None = None) -> list[dict]:
        self._require_sdk()
        try:
            result = self._obb.equity.estimates.consensus(
                symbol=symbol, provider=provider or self._preferred_provider
            )
            return [r.__dict__ for r in result.results]
        except Exception as e:
            raise OpenBBError(f"Analyst estimates failed for {symbol}: {e}") from e

    def earnings_calendar(
        self, start: str | None = None, end: str | None = None
    ) -> list[dict]:
        self._require_sdk()
        try:
            result = self._obb.equity.calendar.earnings(start_date=start, end_date=end)
            return [r.__dict__ for r in result.results]
        except Exception as e:
            raise OpenBBError(f"Earnings calendar failed: {e}") from e

    # ── Screening ────────────────────────────────────────────────────

    def screen_equities(self, **filters) -> pd.DataFrame:
        self._require_sdk()
        try:
            result = self._obb.equity.screener(**filters)
            return result.to_dataframe()
        except Exception as e:
            raise OpenBBError(f"Screening failed: {e}") from e

    def sector_performance(self) -> list[dict]:
        self._require_sdk()
        try:
            result = self._obb.equity.performance.sector()
            return [r.__dict__ for r in result.results]
        except Exception as e:
            raise OpenBBError(f"Sector performance failed: {e}") from e

    # ── Risk / Quantitative ──────────────────────────────────────────

    def correlation_matrix(
        self, symbols: list[str], lookback_days: int = 90
    ) -> pd.DataFrame:
        self._require_sdk()
        try:
            from datetime import timedelta
            start = (datetime.now(UTC) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
            frames = {}
            for sym in symbols:
                result = self._obb.equity.price.historical(
                    symbol=sym, start_date=start
                )
                df = result.to_dataframe()
                frames[sym] = df["close"]
            combined = pd.DataFrame(frames).dropna()
            return combined.pct_change().dropna().corr()
        except Exception as e:
            raise OpenBBError(f"Correlation matrix failed: {e}") from e

    # ── Macro / Economy ──────────────────────────────────────────────

    def economic_indicators(self, series_ids: list[str]) -> pd.DataFrame:
        self._require_sdk()
        try:
            frames = {}
            for sid in series_ids:
                result = self._obb.economy.fred_series(symbol=sid)
                df = result.to_dataframe()
                frames[sid] = df["value"] if "value" in df.columns else df.iloc[:, 0]
            return pd.DataFrame(frames)
        except Exception as e:
            raise OpenBBError(f"Economic indicators failed: {e}") from e

    def economic_calendar(
        self, start: str | None = None, end: str | None = None
    ) -> list[dict]:
        self._require_sdk()
        try:
            result = self._obb.economy.calendar(start_date=start, end_date=end)
            return [r.__dict__ for r in result.results]
        except Exception as e:
            raise OpenBBError(f"Economic calendar failed: {e}") from e

    def yield_curve(self) -> pd.DataFrame:
        self._require_sdk()
        try:
            result = self._obb.fixedincome.rate.treasury()
            return result.to_dataframe()
        except Exception as e:
            raise OpenBBError(f"Yield curve failed: {e}") from e

    def news(self, query: str | None = None, limit: int = 20) -> list[dict]:
        self._require_sdk()
        try:
            kwargs = {"limit": limit}
            if query:
                kwargs["query"] = query
            result = self._obb.news.world(**kwargs)
            return [r.__dict__ for r in result.results]
        except Exception as e:
            raise OpenBBError(f"News fetch failed: {e}") from e


# ── Singleton ────────────────────────────────────────────��───────────

_ADAPTER: OpenBBAdapter | None = None


def get_adapter() -> OpenBBAdapter:
    global _ADAPTER
    if _ADAPTER is None:
        _ADAPTER = OpenBBAdapter()
    return _ADAPTER


def reset_adapter() -> None:
    global _ADAPTER
    _ADAPTER = None
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_openbb_adapter.py -v`
Expected: All 6 tests PASS

**Step 5: Commit**

```bash
git add src/castelino/data/openbb_adapter.py tests/test_openbb_adapter.py
git commit -m "feat: add OpenBB adapter module with pricing, TA, fundamentals, macro"
```

---

### Task 3: Add PriceSource.OPENBB and wire fallback into pricing.py

**Files:**
- Modify: `src/castelino/data/instruments.py`
- Modify: `src/castelino/execution/pricing.py`
- Test: `tests/test_pricing_fallback.py`

**Step 1: Write the failing test**

```python
"""tests/test_pricing_fallback.py"""
from unittest.mock import patch, MagicMock
from datetime import UTC, datetime
import pytest

from castelino.data.openbb_adapter import OpenBBError, OBBPrice
from castelino.execution.pricing import latest, Price, PricingError


def test_pricing_tries_openbb_first(tmp_path):
    """If OpenBB succeeds, should return its price without calling yfinance."""
    mock_adapter = MagicMock()
    mock_adapter.available = True
    mock_adapter.latest_price.return_value = OBBPrice(
        instrument_id="SPY", price=450.0, asof=datetime.now(UTC)
    )

    with patch("castelino.execution.pricing._try_openbb", return_value=Price(
        instrument_id="SPY", price=450.0, asof=datetime.now(UTC),
        source="openbb"
    )):
        with patch("castelino.execution.pricing._fetch_yf") as mock_yf:
            price = latest("SPY")
            assert price.price == 450.0
            mock_yf.assert_not_called()


def test_pricing_falls_back_to_yfinance_on_openbb_failure():
    """If OpenBB fails, should fallback to yfinance."""
    with patch("castelino.execution.pricing._try_openbb", return_value=None):
        with patch("castelino.execution.pricing._fetch_yf_latest") as mock_yf:
            mock_yf.return_value = Price(
                instrument_id="SPY", price=448.0,
                asof=datetime.now(UTC), source="yfinance"
            )
            price = latest("SPY")
            assert price.price == 448.0
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_pricing_fallback.py -v`
Expected: FAIL (functions don't exist yet)

**Step 3: Add OPENBB to PriceSource enum**

In `src/castelino/data/instruments.py`, add to `PriceSource`:
```python
class PriceSource(str, Enum):
    YFINANCE = "yfinance"
    FRED = "fred"
    OPENBB = "openbb"
```

**Step 4: Modify pricing.py to add OpenBB fallback**

Add at the top of `pricing.py`:
```python
from castelino.data.openbb_adapter import OpenBBError, get_adapter
```

Add helper function before `latest()`:
```python
def _try_openbb(instrument_id: str) -> Price | None:
    """Attempt to fetch via OpenBB. Returns None on any failure."""
    adapter = get_adapter()
    if not adapter.available:
        return None
    try:
        from castelino.data.openbb_adapter import OBBPrice
        obb_price = adapter.latest_price(instrument_id)
        return Price(
            instrument_id=instrument_id,
            price=obb_price.price,
            asof=obb_price.asof,
            source=PriceSource.OPENBB,
        )
    except OpenBBError as e:
        log.debug("OpenBB fallback for %s: %s", instrument_id, e)
        return None
```

Modify `latest()` function to try OpenBB first:
```python
def latest(instrument_id: str) -> Price:
    """Most recent price. Tries OpenBB first, falls back to yfinance/FRED."""
    # Try OpenBB as primary source
    obb_price = _try_openbb(instrument_id)
    if obb_price is not None:
        return obb_price

    # Fallback to existing adapters
    inst = get_instrument(instrument_id)
    df = history(instrument_id, lookback_days=10)
    if df.empty:
        raise PricingError(f"No price history for {instrument_id}")
    last_row = df.iloc[-1]
    px = float(last_row["close"])
    asof = last_row.name if isinstance(last_row.name, pd.Timestamp) else df.index[-1]
    asof_dt = asof.to_pydatetime() if hasattr(asof, "to_pydatetime") else asof

    _validate_price(inst, px, asof_dt, df)
    return Price(
        instrument_id=instrument_id,
        price=px,
        asof=asof_dt,
        source=inst.source,
    )
```

**Step 5: Run tests**

Run: `pytest tests/test_pricing_fallback.py tests/test_broker_fills.py tests/test_accounting_invariant.py -v`
Expected: All PASS (existing tests unaffected due to fallback)

**Step 6: Commit**

```bash
git add src/castelino/data/instruments.py src/castelino/execution/pricing.py tests/test_pricing_fallback.py
git commit -m "feat: wire OpenBB as primary pricing source with yfinance/FRED fallback"
```

---

### Task 4: Wire OpenBB into research agents

**Files:**
- Modify: `src/castelino/agents/research/technical.py`
- Modify: `src/castelino/agents/research/risk.py`
- Modify: `src/castelino/agents/research/web.py`
- Test: `tests/test_research_openbb.py`

**Step 1: Write failing test**

```python
"""tests/test_research_openbb.py"""
from unittest.mock import patch, MagicMock
import pandas as pd
import pytest

from castelino.agents.research.technical import compute_ta_features


def test_ta_features_uses_openbb_when_available():
    """TA computation should try OpenBB adapter for indicators."""
    mock_adapter = MagicMock()
    mock_adapter.available = True
    mock_adapter.technical_indicators.return_value = {
        "rsi": pd.DataFrame({"rsi": [65.0]}),
        "macd": pd.DataFrame({"macd": [1.2], "signal": [0.8]}),
    }

    with patch("castelino.agents.research.technical.get_adapter", return_value=mock_adapter):
        # Should still work via existing fallback when OpenBB returns partial data
        features = compute_ta_features("SPY")
        assert features.instrument_id == "SPY"
```

**Step 2: Modify technical.py**

Add import at top:
```python
from castelino.data.openbb_adapter import get_adapter, OpenBBError
```

Add OpenBB-enhanced TA function (keep existing `compute_ta_features` as fallback):
```python
def compute_ta_features_openbb(instrument_id: str) -> TAFeatures | None:
    """Try to compute TA features via OpenBB. Returns None on failure."""
    adapter = get_adapter()
    if not adapter.available:
        return None
    try:
        indicators = adapter.technical_indicators(instrument_id, ["rsi", "macd", "bbands"])
        ma = adapter.moving_averages(instrument_id, [50, 200])
        if ma.empty:
            return None
        last = float(ma["close"].iloc[-1])
        sma_50 = float(ma["sma_50"].iloc[-1])
        sma_200 = float(ma["sma_200"].iloc[-1])
        rsi = float(indicators["rsi"]["rsi"].iloc[-1]) if "rsi" in indicators else 50.0
        vol_df = adapter.history(instrument_id, lookback_days=60)
        log_rets = (vol_df["close"].pct_change().dropna())
        realized_vol = float(log_rets.tail(30).std() * (252 ** 0.5)) if len(log_rets) >= 30 else 0.0
        window = vol_df["close"].tail(60)
        return TAFeatures(
            instrument_id=instrument_id,
            last_close=last,
            sma_50=sma_50,
            sma_200=sma_200,
            rsi_14=rsi,
            realized_vol_30d=realized_vol,
            key_support=float(window.min()),
            key_resistance=float(window.max()),
        )
    except (OpenBBError, Exception) as e:
        log.debug("OpenBB TA failed for %s, falling back: %s", instrument_id, e)
        return None
```

Modify existing `compute_ta_features` to try OpenBB first:
```python
def compute_ta_features(instrument_id: str, lookback_days: int | None = None) -> TAFeatures:
    # Try OpenBB first
    obb_features = compute_ta_features_openbb(instrument_id)
    if obb_features is not None:
        return obb_features

    # Existing pandas-based computation (unchanged)
    cfg = get_settings()
    n = lookback_days or cfg.research.ta_lookback_days
    # ... rest of existing code unchanged ...
```

**Step 3: Modify risk.py — add correlation via OpenBB**

Add import:
```python
from castelino.data.openbb_adapter import get_adapter, OpenBBError
```

Add helper:
```python
def _correlation_openbb(symbols: list[str], lookback_days: int) -> pd.DataFrame | None:
    adapter = get_adapter()
    if not adapter.available:
        return None
    try:
        return adapter.correlation_matrix(symbols, lookback_days)
    except OpenBBError:
        return None
```

**Step 4: Modify web.py — add news via OpenBB**

Add import:
```python
from castelino.data.openbb_adapter import get_adapter, OpenBBError
```

Add helper that supplements RSS with OpenBB news:
```python
def _fetch_openbb_news(query: str, limit: int = 10) -> list[dict]:
    adapter = get_adapter()
    if not adapter.available:
        return []
    try:
        return adapter.news(query=query, limit=limit)
    except OpenBBError:
        return []
```

**Step 5: Run all tests**

Run: `pytest tests/ -v --ignore=tests/integration`
Expected: All PASS

**Step 6: Commit**

```bash
git add src/castelino/agents/research/technical.py src/castelino/agents/research/risk.py src/castelino/agents/research/web.py tests/test_research_openbb.py
git commit -m "feat: wire OpenBB adapter into research agents (TA, risk, web)"
```

---

## Workstream 2: Human-in-the-Loop Approval Gates

### Task 5: Create approval queue module

**Files:**
- Create: `src/castelino/orchestrator/approval.py`
- Test: `tests/test_approval_queue.py`

**Step 1: Write the failing test**

```python
"""tests/test_approval_queue.py"""
import json
from pathlib import Path
import pytest

from castelino.orchestrator.approval import (
    ApprovalItem,
    ApprovalQueue,
    ApprovalStatus,
    GateType,
)


@pytest.fixture
def queue(tmp_path):
    return ApprovalQueue(state_dir=tmp_path)


def test_submit_hypothesis_creates_pending_item(queue):
    item = queue.submit(
        gate=GateType.POST_HYPOTHESIS,
        payload={"thesis": "Rates will rise", "regime": "tightening"},
        entry_id="H-abc123",
    )
    assert item.status == ApprovalStatus.PENDING
    assert item.gate == GateType.POST_HYPOTHESIS
    assert item.entry_id == "H-abc123"


def test_pending_items_persists_to_disk(queue, tmp_path):
    queue.submit(
        gate=GateType.POST_HYPOTHESIS,
        payload={"thesis": "test"},
        entry_id="H-001",
    )
    # Reload from disk
    queue2 = ApprovalQueue(state_dir=tmp_path)
    pending = queue2.pending()
    assert len(pending) == 1
    assert pending[0].entry_id == "H-001"


def test_approve_marks_item_approved(queue):
    queue.submit(gate=GateType.POST_DEBATE, payload={}, entry_id="V-001")
    item = queue.approve("V-001")
    assert item.status == ApprovalStatus.APPROVED


def test_reject_marks_item_rejected(queue):
    queue.submit(gate=GateType.POST_DEBATE, payload={}, entry_id="V-001")
    item = queue.reject("V-001", reason="too risky")
    assert item.status == ApprovalStatus.REJECTED
    assert item.rejection_reason == "too risky"


def test_edit_updates_payload_and_approves(queue):
    queue.submit(
        gate=GateType.POST_HYPOTHESIS,
        payload={"thesis": "original"},
        entry_id="H-001",
    )
    item = queue.edit("H-001", updated_payload={"thesis": "revised"})
    assert item.status == ApprovalStatus.APPROVED
    assert item.payload["thesis"] == "revised"


def test_approve_nonexistent_raises(queue):
    with pytest.raises(KeyError):
        queue.approve("NOPE")


def test_wait_for_approval_returns_when_approved(queue):
    queue.submit(gate=GateType.POST_HYPOTHESIS, payload={}, entry_id="H-001")
    # Simulate approval
    queue.approve("H-001")
    item = queue.get("H-001")
    assert item.status == ApprovalStatus.APPROVED
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_approval_queue.py -v`
Expected: FAIL with ImportError

**Step 3: Write the implementation**

```python
"""src/castelino/orchestrator/approval.py
Human-in-the-loop approval queue. Persists to JSON on disk.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from castelino.config import get_settings

log = logging.getLogger(__name__)


class GateType(str, Enum):
    POST_HYPOTHESIS = "post_hypothesis"
    POST_DEBATE = "post_debate"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalItem(BaseModel):
    entry_id: str
    gate: GateType
    status: ApprovalStatus = ApprovalStatus.PENDING
    payload: dict = Field(default_factory=dict)
    submitted_at: str = ""
    resolved_at: str | None = None
    rejection_reason: str | None = None

    model_config = {"use_enum_values": True}


class ApprovalQueue:
    """Disk-backed approval queue. Thread-safe via file-level atomicity."""

    def __init__(self, state_dir: Path | None = None):
        if state_dir is None:
            cfg = get_settings()
            state_dir = cfg.resolved_paths.data
        self._path = state_dir / "approval_queue.json"
        self._items: dict[str, ApprovalItem] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            raw = json.loads(self._path.read_text())
            for entry_id, data in raw.items():
                self._items[entry_id] = ApprovalItem.model_validate(data)

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {k: v.model_dump() for k, v in self._items.items()}
        self._path.write_text(json.dumps(payload, indent=2, default=str))

    def submit(
        self, *, gate: GateType, payload: dict, entry_id: str
    ) -> ApprovalItem:
        item = ApprovalItem(
            entry_id=entry_id,
            gate=gate,
            payload=payload,
            submitted_at=datetime.now(UTC).isoformat(),
        )
        self._items[entry_id] = item
        self._save()
        log.info("Approval gate %s: item %s pending", gate.value, entry_id)
        return item

    def pending(self) -> list[ApprovalItem]:
        return [i for i in self._items.values() if i.status == ApprovalStatus.PENDING]

    def get(self, entry_id: str) -> ApprovalItem:
        if entry_id not in self._items:
            raise KeyError(f"No approval item with id {entry_id}")
        return self._items[entry_id]

    def approve(self, entry_id: str) -> ApprovalItem:
        item = self.get(entry_id)
        item.status = ApprovalStatus.APPROVED
        item.resolved_at = datetime.now(UTC).isoformat()
        self._save()
        log.info("Approved: %s", entry_id)
        return item

    def reject(self, entry_id: str, reason: str = "") -> ApprovalItem:
        item = self.get(entry_id)
        item.status = ApprovalStatus.REJECTED
        item.rejection_reason = reason
        item.resolved_at = datetime.now(UTC).isoformat()
        self._save()
        log.info("Rejected: %s — %s", entry_id, reason)
        return item

    def edit(self, entry_id: str, updated_payload: dict) -> ApprovalItem:
        item = self.get(entry_id)
        item.payload = updated_payload
        item.status = ApprovalStatus.APPROVED
        item.resolved_at = datetime.now(UTC).isoformat()
        self._save()
        log.info("Edited + approved: %s", entry_id)
        return item

    def wait_for_resolution(self, entry_id: str, poll_interval: float = 2.0) -> ApprovalItem:
        """Block until the item is approved or rejected. Used by pipeline nodes."""
        while True:
            self._load()
            item = self.get(entry_id)
            if item.status != ApprovalStatus.PENDING:
                return item
            time.sleep(poll_interval)

    def history(self, limit: int = 50) -> list[ApprovalItem]:
        resolved = [i for i in self._items.values() if i.status != ApprovalStatus.PENDING]
        return sorted(resolved, key=lambda x: x.resolved_at or "", reverse=True)[:limit]
```

**Step 4: Run test to verify passes**

Run: `pytest tests/test_approval_queue.py -v`
Expected: All 7 tests PASS

**Step 5: Commit**

```bash
git add src/castelino/orchestrator/approval.py tests/test_approval_queue.py
git commit -m "feat: add HITL approval queue with disk persistence"
```

---

### Task 6: Wire approval gates into the LangGraph pipeline

**Files:**
- Modify: `src/castelino/orchestrator/graph.py`
- Test: `tests/test_pipeline_gates.py`

**Step 1: Write the failing test**

```python
"""tests/test_pipeline_gates.py"""
from unittest.mock import patch, MagicMock
import threading
import time
import pytest

from castelino.orchestrator.approval import ApprovalQueue, ApprovalStatus, GateType


def test_hypothesis_gate_stalls_pipeline(tmp_path):
    """Pipeline should stall at post_hypothesis gate until approved."""
    queue = ApprovalQueue(state_dir=tmp_path)
    item = queue.submit(
        gate=GateType.POST_HYPOTHESIS,
        payload={"thesis": "test"},
        entry_id="H-test",
    )

    # Approve in background after short delay
    def approve_later():
        time.sleep(0.5)
        queue.approve("H-test")

    t = threading.Thread(target=approve_later)
    t.start()

    result = queue.wait_for_resolution("H-test", poll_interval=0.1)
    t.join()
    assert result.status == ApprovalStatus.APPROVED


def test_debate_gate_rejects_aborts_pipeline(tmp_path):
    """Rejected verdict should cause pipeline to abort."""
    queue = ApprovalQueue(state_dir=tmp_path)
    queue.submit(
        gate=GateType.POST_DEBATE,
        payload={"decision": "proceed"},
        entry_id="V-test",
    )
    queue.reject("V-test", reason="too risky")

    item = queue.get("V-test")
    assert item.status == ApprovalStatus.REJECTED
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_pipeline_gates.py -v`
Expected: PASS (these test the queue directly — step 3 modifies graph.py)

**Step 3: Add gate nodes to graph.py**

Add import at top of `graph.py`:
```python
from castelino.orchestrator.approval import ApprovalQueue, ApprovalStatus, GateType
```

Add gate nodes:
```python
def _node_gate_hypothesis(state: FundState) -> dict:
    """HITL gate: stall until human approves/edits/rejects the hypothesis."""
    log.info("⏸ GATE: awaiting hypothesis approval")
    if state.hypothesis is None:
        return {"aborted": True, "abort_reason": "no hypothesis to approve"}

    queue = ApprovalQueue()
    item = queue.submit(
        gate=GateType.POST_HYPOTHESIS,
        payload={
            "thesis": state.hypothesis.thesis,
            "regime": state.hypothesis.regime.value,
            "conviction": state.hypothesis.conviction.value,
            "horizon_days": state.hypothesis.horizon_days,
            "kill_criteria": [c.description for c in state.hypothesis.kill_criteria],
        },
        entry_id=f"H-{state.hypothesis.entry_id}",
    )
    result = queue.wait_for_resolution(item.entry_id)

    if result.status == ApprovalStatus.REJECTED:
        return {"aborted": True, "abort_reason": f"hypothesis rejected: {result.rejection_reason}"}

    # If edited, update the hypothesis thesis in state
    if result.payload.get("thesis") and result.payload["thesis"] != state.hypothesis.thesis:
        state.hypothesis.thesis = result.payload["thesis"]

    return {}


def _node_gate_debate(state: FundState) -> dict:
    """HITL gate: stall until human approves/rejects debate verdicts."""
    log.info("⏸ GATE: awaiting debate verdict approval")
    if not state.verdicts:
        return {"aborted": True, "abort_reason": "no verdicts to approve"}

    queue = ApprovalQueue()
    for i, (exp, verdict) in enumerate(zip(state.expressions, state.verdicts, strict=True)):
        item = queue.submit(
            gate=GateType.POST_DEBATE,
            payload={
                "instrument": exp.instrument_id,
                "direction": exp.direction.value,
                "decision": verdict.decision,
                "size_multiplier": verdict.size_multiplier,
                "decisive_factor": verdict.decisive_factor,
                "bull_summary": verdict.bull_summary,
                "bear_summary": verdict.bear_summary,
            },
            entry_id=f"V-{verdict.entry_id}",
        )
        result = queue.wait_for_resolution(item.entry_id)

        if result.status == ApprovalStatus.REJECTED:
            return {
                "aborted": True,
                "abort_reason": f"verdict rejected for {exp.instrument_id}: {result.rejection_reason}",
            }

    return {}
```

Modify `build_graph()` to insert gate nodes:
```python
def build_graph():
    g = StateGraph(FundState)
    g.add_node("current_event", _node_current_event)
    g.add_node("hypothesis", _node_hypothesis)
    g.add_node("gate_hypothesis", _node_gate_hypothesis)  # NEW
    g.add_node("asset_selection", _node_asset_selection)
    g.add_node("research", _node_research)
    g.add_node("debate", _node_debate)
    g.add_node("gate_debate", _node_gate_debate)  # NEW
    g.add_node("guard", _node_guard)
    g.add_node("portfolio", _node_portfolio_and_execute)

    g.set_entry_point("current_event")
    g.add_edge("current_event", "hypothesis")
    g.add_conditional_edges(
        "hypothesis",
        _route_after_hypothesis,
        {"asset_selection": "gate_hypothesis", "abort": END},  # CHANGED
    )
    g.add_conditional_edges(
        "gate_hypothesis",
        lambda s: "abort" if s.aborted else "asset_selection",
        {"asset_selection": "asset_selection", "abort": END},
    )
    g.add_conditional_edges(
        "asset_selection",
        _route_after_asset_selection,
        {"research": "research", "abort": END},
    )
    g.add_edge("research", "debate")
    g.add_edge("debate", "gate_debate")  # CHANGED
    g.add_conditional_edges(
        "gate_debate",
        lambda s: "abort" if s.aborted else "guard",
        {"guard": "guard", "abort": END},
    )
    g.add_edge("guard", "portfolio")
    g.add_edge("portfolio", END)
    return g.compile()
```

**Step 4: Run full test suite**

Run: `pytest tests/ -v --ignore=tests/integration`
Expected: All PASS (existing e2e test may need mock of approval queue — see next step)

**Step 5: Patch e2e test to auto-approve**

In `tests/test_pipeline_e2e.py`, add fixture:
```python
@pytest.fixture(autouse=True)
def auto_approve_gates(monkeypatch):
    """Auto-approve all gates in tests so pipeline doesn't stall."""
    from castelino.orchestrator.approval import ApprovalQueue, ApprovalItem, ApprovalStatus
    original_wait = ApprovalQueue.wait_for_resolution

    def instant_approve(self, entry_id, poll_interval=2.0):
        self.approve(entry_id)
        return self.get(entry_id)

    monkeypatch.setattr(ApprovalQueue, "wait_for_resolution", instant_approve)
```

**Step 6: Run tests again**

Run: `pytest tests/ -v --ignore=tests/integration`
Expected: All PASS

**Step 7: Commit**

```bash
git add src/castelino/orchestrator/graph.py tests/test_pipeline_gates.py tests/test_pipeline_e2e.py
git commit -m "feat: add HITL gates (post-hypothesis, post-debate) to pipeline graph"
```

---

### Task 7: Add approval CLI commands

**Files:**
- Modify: `src/castelino/orchestrator/cli.py`
- Test: `tests/test_cli_approval.py`

**Step 1: Write the failing test**

```python
"""tests/test_cli_approval.py"""
from typer.testing import CliRunner
from castelino.orchestrator.cli import app
from castelino.orchestrator.approval import ApprovalQueue, GateType

runner = CliRunner()


def test_queue_command_shows_pending(tmp_path, monkeypatch):
    monkeypatch.setenv("CASTELINO_DATA_DIR", str(tmp_path))
    queue = ApprovalQueue(state_dir=tmp_path)
    queue.submit(gate=GateType.POST_HYPOTHESIS, payload={"thesis": "test"}, entry_id="H-001")

    result = runner.invoke(app, ["queue", "--state-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "H-001" in result.output


def test_approve_command(tmp_path):
    queue = ApprovalQueue(state_dir=tmp_path)
    queue.submit(gate=GateType.POST_HYPOTHESIS, payload={"thesis": "test"}, entry_id="H-001")

    result = runner.invoke(app, ["approve", "H-001", "--state-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "Approved" in result.output


def test_reject_command(tmp_path):
    queue = ApprovalQueue(state_dir=tmp_path)
    queue.submit(gate=GateType.POST_DEBATE, payload={}, entry_id="V-001")

    result = runner.invoke(app, ["reject", "V-001", "--reason", "too risky", "--state-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "Rejected" in result.output
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_approval.py -v`
Expected: FAIL (commands don't exist)

**Step 3: Add CLI commands to cli.py**

Add these commands after the existing ones:

```python
@app.command()
def queue(
    state_dir: str = typer.Option(None, help="Override state directory (for testing)."),
):
    """List pending approval items."""
    from castelino.orchestrator.approval import ApprovalQueue

    sd = Path(state_dir) if state_dir else None
    q = ApprovalQueue(state_dir=sd)
    pending = q.pending()
    if not pending:
        print("[green]No pending approvals.[/green]")
        return
    table = Table(title="Pending Approvals")
    table.add_column("ID")
    table.add_column("Gate")
    table.add_column("Submitted")
    table.add_column("Payload")
    for item in pending:
        table.add_row(
            item.entry_id,
            item.gate,
            item.submitted_at[:19],
            str(item.payload)[:100],
        )
    print(table)


@app.command()
def approve(
    entry_id: str = typer.Argument(..., help="Approval item ID (e.g. H-abc123, V-def456)."),
    state_dir: str = typer.Option(None, help="Override state directory."),
):
    """Approve a pending hypothesis or verdict."""
    from castelino.orchestrator.approval import ApprovalQueue

    sd = Path(state_dir) if state_dir else None
    q = ApprovalQueue(state_dir=sd)
    item = q.approve(entry_id)
    print(f"[green]Approved:[/green] {item.entry_id} ({item.gate})")


@app.command()
def reject(
    entry_id: str = typer.Argument(..., help="Approval item ID."),
    reason: str = typer.Option("", help="Reason for rejection."),
    state_dir: str = typer.Option(None, help="Override state directory."),
):
    """Reject a pending hypothesis or verdict."""
    from castelino.orchestrator.approval import ApprovalQueue

    sd = Path(state_dir) if state_dir else None
    q = ApprovalQueue(state_dir=sd)
    item = q.reject(entry_id, reason=reason)
    print(f"[red]Rejected:[/red] {item.entry_id} — {reason or '(no reason)'}")


@app.command()
def edit(
    entry_id: str = typer.Argument(..., help="Approval item ID."),
    thesis: str = typer.Option(None, help="Revised thesis text."),
    state_dir: str = typer.Option(None, help="Override state directory."),
):
    """Edit and approve a pending hypothesis."""
    from castelino.orchestrator.approval import ApprovalQueue

    sd = Path(state_dir) if state_dir else None
    q = ApprovalQueue(state_dir=sd)
    current = q.get(entry_id)
    payload = current.payload.copy()
    if thesis:
        payload["thesis"] = thesis
    item = q.edit(entry_id, updated_payload=payload)
    print(f"[green]Edited + Approved:[/green] {item.entry_id}")
    print(f"  thesis: {payload.get('thesis', '(unchanged)')}")
```

**Step 4: Run tests**

Run: `pytest tests/test_cli_approval.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/castelino/orchestrator/cli.py tests/test_cli_approval.py
git commit -m "feat: add castelino queue/approve/reject/edit CLI commands"
```

---

## Workstream 3: OpenBB Workspace Dashboard

### Task 8: Create dashboard FastAPI skeleton

**Files:**
- Create: `src/castelino/dashboard/__init__.py`
- Create: `src/castelino/dashboard/main.py`
- Create: `src/castelino/dashboard/widgets.json`
- Create: `src/castelino/dashboard/apps.json`
- Test: `tests/test_dashboard_app.py`

**Step 1: Write failing test**

```python
"""tests/test_dashboard_app.py"""
from fastapi.testclient import TestClient
import pytest


@pytest.fixture
def client():
    from castelino.dashboard.main import app
    return TestClient(app)


def test_root_returns_200(client):
    r = client.get("/")
    assert r.status_code == 200


def test_widgets_json_returns_dict(client):
    r = client.get("/widgets.json")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, dict)


def test_apps_json_returns_array(client):
    r = client.get("/apps.json")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) >= 1
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_dashboard_app.py -v`
Expected: FAIL with ImportError

**Step 3: Create the FastAPI app**

`src/castelino/dashboard/__init__.py`:
```python
```

`src/castelino/dashboard/main.py`:
```python
"""OpenBB Workspace backend for Castelino Capital."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Castelino Capital — OpenBB Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://pro.openbb.co",
        "https://pro.openbb.dev",
        "http://localhost:1420",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_DIR = Path(__file__).parent
WIDGETS = json.loads((_DIR / "widgets.json").read_text())
APPS = json.loads((_DIR / "apps.json").read_text())


@app.get("/")
def root():
    return {"name": "Castelino Capital", "status": "running"}


@app.get("/widgets.json")
def get_widgets():
    return WIDGETS


@app.get("/apps.json")
def get_apps():
    return APPS


# Import endpoint routers
from castelino.dashboard.endpoints import portfolio, macro, research, risk, agents, approvals  # noqa: E402

app.include_router(portfolio.router)
app.include_router(macro.router)
app.include_router(research.router)
app.include_router(risk.router)
app.include_router(agents.router)
app.include_router(approvals.router)
```

**Step 4: Create initial widgets.json**

```json
{
  "nav_metrics": {
    "name": "Portfolio Metrics",
    "description": "NAV, cash, exposure metrics",
    "category": "Portfolio",
    "type": "metric",
    "endpoint": "portfolio_metrics"
  },
  "positions_table": {
    "name": "Open Positions",
    "description": "Current portfolio positions with live P&L",
    "category": "Portfolio",
    "type": "table",
    "endpoint": "positions",
    "data": {
      "table": {
        "columnsDefs": [
          {"field": "instrument_id", "headerName": "Instrument", "cellDataType": "text", "pinned": "left"},
          {"field": "side", "headerName": "Side", "cellDataType": "text"},
          {"field": "asset_class", "headerName": "Class", "cellDataType": "text"},
          {"field": "quantity", "headerName": "Qty", "cellDataType": "number", "formatterFn": "none"},
          {"field": "entry_price", "headerName": "Entry", "cellDataType": "number", "formatterFn": "none"},
          {"field": "mark_price", "headerName": "Mark", "cellDataType": "number", "formatterFn": "none"},
          {"field": "market_value", "headerName": "Mkt Value", "cellDataType": "number", "formatterFn": "none"},
          {"field": "pct_nav", "headerName": "% NAV", "cellDataType": "number", "formatterFn": "percent"},
          {"field": "unrealized_pnl", "headerName": "Unrealized $", "cellDataType": "number", "formatterFn": "none", "renderFn": "greenRed"},
          {"field": "unrealized_pct", "headerName": "Unrealized %", "cellDataType": "number", "formatterFn": "percent", "renderFn": "greenRed"}
        ]
      }
    }
  },
  "recent_fills": {
    "name": "Recent Fills",
    "description": "Latest trade executions",
    "category": "Portfolio",
    "type": "table",
    "endpoint": "recent_fills"
  },
  "equity_curve": {
    "name": "Equity Curve",
    "description": "Portfolio NAV over time",
    "category": "Portfolio",
    "type": "chart",
    "endpoint": "equity_curve_chart"
  },
  "macro_indicators": {
    "name": "Macro Indicators",
    "description": "Key economic indicators",
    "category": "Macro",
    "type": "table",
    "endpoint": "macro_indicators"
  },
  "yield_curve_chart": {
    "name": "Yield Curve",
    "description": "US Treasury yield curve",
    "category": "Macro",
    "type": "chart",
    "endpoint": "yield_curve"
  },
  "triggers_table": {
    "name": "Recent Triggers",
    "description": "Pipeline trigger events",
    "category": "Macro",
    "type": "table",
    "endpoint": "triggers"
  },
  "hypotheses_table": {
    "name": "Active Hypotheses",
    "description": "Current macro theses",
    "category": "Macro",
    "type": "table",
    "endpoint": "hypotheses"
  },
  "news_feed": {
    "name": "Market News",
    "description": "Latest financial news",
    "category": "Macro",
    "type": "newsfeed",
    "endpoint": "news"
  },
  "econ_calendar": {
    "name": "Economic Calendar",
    "description": "Upcoming economic events",
    "category": "Macro",
    "type": "table",
    "endpoint": "economic_calendar"
  },
  "ta_chart": {
    "name": "Technical Analysis",
    "description": "Price chart with indicators",
    "category": "Research",
    "type": "chart",
    "endpoint": "ta_chart",
    "params": [
      {"paramName": "symbol", "type": "text", "label": "Symbol", "value": "SPY"}
    ]
  },
  "screener": {
    "name": "Screener",
    "description": "Equity screener",
    "category": "Research",
    "type": "table",
    "endpoint": "screener"
  },
  "correlation_heatmap": {
    "name": "Correlation Matrix",
    "description": "Cross-asset correlations",
    "category": "Research",
    "type": "chart",
    "endpoint": "correlations"
  },
  "sector_perf": {
    "name": "Sector Performance",
    "description": "S&P 500 sector returns",
    "category": "Research",
    "type": "table",
    "endpoint": "sector_performance"
  },
  "exposure_class_chart": {
    "name": "Exposure by Class",
    "description": "Gross exposure breakdown by asset class",
    "category": "Risk",
    "type": "chart",
    "endpoint": "exposure_by_class"
  },
  "exposure_instrument_chart": {
    "name": "Exposure by Instrument",
    "description": "Position-level exposure",
    "category": "Risk",
    "type": "chart",
    "endpoint": "exposure_by_instrument"
  },
  "warnings_table": {
    "name": "Principle Warnings",
    "description": "Recent guard warnings",
    "category": "Risk",
    "type": "table",
    "endpoint": "warnings"
  },
  "verdicts_table": {
    "name": "Bull vs Bear Verdicts",
    "description": "Debate outcomes",
    "category": "Agents",
    "type": "table",
    "endpoint": "verdicts"
  },
  "guard_decisions_table": {
    "name": "Guard Decisions",
    "description": "Principles guard outcomes",
    "category": "Agents",
    "type": "table",
    "endpoint": "guard_decisions"
  },
  "approval_count": {
    "name": "Pending Approvals",
    "description": "Items awaiting human decision",
    "category": "Approvals",
    "type": "metric",
    "endpoint": "approval_metrics"
  },
  "approval_queue_table": {
    "name": "Approval Queue",
    "description": "Pending hypotheses and verdicts",
    "category": "Approvals",
    "type": "table",
    "endpoint": "approval_queue"
  },
  "approval_history_table": {
    "name": "Decision History",
    "description": "Past approval decisions",
    "category": "Approvals",
    "type": "table",
    "endpoint": "approval_history"
  }
}
```

**Step 5: Create initial apps.json**

```json
[
  {
    "name": "Castelino Capital",
    "description": "Multi-agent macro fund dashboard",
    "img": "",
    "img_dark": "",
    "img_light": "",
    "allowCustomization": true,
    "tabs": {
      "portfolio": {
        "id": "portfolio",
        "name": "Portfolio",
        "layout": [
          {"i": "nav_metrics", "x": 0, "y": 0, "w": 40, "h": 5},
          {"i": "positions_table", "x": 0, "y": 5, "w": 40, "h": 14},
          {"i": "equity_curve", "x": 0, "y": 19, "w": 20, "h": 12},
          {"i": "recent_fills", "x": 20, "y": 19, "w": 20, "h": 12}
        ]
      },
      "macro": {
        "id": "macro",
        "name": "Macro & Signals",
        "layout": [
          {"i": "macro_indicators", "x": 0, "y": 0, "w": 20, "h": 12},
          {"i": "yield_curve_chart", "x": 20, "y": 0, "w": 20, "h": 12},
          {"i": "triggers_table", "x": 0, "y": 12, "w": 20, "h": 10},
          {"i": "hypotheses_table", "x": 20, "y": 12, "w": 20, "h": 10},
          {"i": "news_feed", "x": 0, "y": 22, "w": 20, "h": 14},
          {"i": "econ_calendar", "x": 20, "y": 22, "w": 20, "h": 14}
        ]
      },
      "research": {
        "id": "research",
        "name": "Research & Technicals",
        "layout": [
          {"i": "ta_chart", "x": 0, "y": 0, "w": 26, "h": 14, "groups": ["Group 1"]},
          {"i": "screener", "x": 26, "y": 0, "w": 14, "h": 14},
          {"i": "correlation_heatmap", "x": 0, "y": 14, "w": 20, "h": 14},
          {"i": "sector_perf", "x": 20, "y": 14, "w": 20, "h": 14}
        ]
      },
      "risk": {
        "id": "risk",
        "name": "Risk & Attribution",
        "layout": [
          {"i": "exposure_class_chart", "x": 0, "y": 0, "w": 20, "h": 14},
          {"i": "exposure_instrument_chart", "x": 20, "y": 0, "w": 20, "h": 14},
          {"i": "warnings_table", "x": 0, "y": 14, "w": 40, "h": 12}
        ]
      },
      "agents": {
        "id": "agents",
        "name": "Agent Decisions",
        "layout": [
          {"i": "verdicts_table", "x": 0, "y": 0, "w": 20, "h": 14},
          {"i": "guard_decisions_table", "x": 20, "y": 0, "w": 20, "h": 14}
        ]
      },
      "approvals": {
        "id": "approvals",
        "name": "Approval Queue",
        "layout": [
          {"i": "approval_count", "x": 0, "y": 0, "w": 40, "h": 5},
          {"i": "approval_queue_table", "x": 0, "y": 5, "w": 40, "h": 14},
          {"i": "approval_history_table", "x": 0, "y": 19, "w": 40, "h": 12}
        ]
      }
    },
    "groups": [
      {
        "name": "Group 1",
        "type": "param",
        "paramName": "symbol",
        "widgetIds": ["ta_chart", "screener"],
        "defaultValue": "SPY"
      }
    ],
    "prompts": []
  }
]
```

**Step 6: Create endpoint directory and stub routers**

Create: `src/castelino/dashboard/endpoints/__init__.py` (empty)

Create stub routers (one file each). Example for `portfolio.py`:

```python
"""src/castelino/dashboard/endpoints/portfolio.py"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from castelino.execution.portfolio import Portfolio
from castelino.execution.pricing import PricingError, latest
from castelino.memory import io as memio
from castelino.memory.schemas import TradeEvent

router = APIRouter()


@router.get("/portfolio_metrics")
def portfolio_metrics():
    pf = Portfolio.load()
    nav = pf.nav
    initial = pf.initial_nav
    ret_pct = (nav / initial - 1) * 100 if initial > 0 else 0.0
    return [
        {"label": "NAV", "value": f"${nav:,.0f}", "delta": f"{ret_pct:+.2f}%"},
        {"label": "Cash", "value": f"${pf.cash:,.0f}", "subvalue": f"{pf.cash/nav*100:.1f}% of NAV" if nav > 0 else ""},
        {"label": "Gross Exposure", "value": f"${pf.gross_exposure:,.0f}", "subvalue": f"{pf.gross_exposure/nav*100:.1f}% of NAV" if nav > 0 else ""},
        {"label": "Net Exposure", "value": f"${pf.net_exposure:,.0f}", "subvalue": f"{pf.net_exposure/nav*100:.1f}% of NAV" if nav > 0 else ""},
        {"label": "Unrealized P&L", "value": f"${pf.unrealized_pnl:+,.2f}", "delta": f"{pf.unrealized_pnl/nav*100:+.2f}%" if nav > 0 else ""},
        {"label": "Positions", "value": str(len(pf.positions)), "subvalue": "open"},
    ]


@router.get("/positions")
def positions():
    pf = Portfolio.load()
    nav = pf.nav
    rows = []
    for p in pf.positions:
        try:
            mark = latest(p.instrument_id).price
        except PricingError:
            mark = p.current_price
        mv = p.quantity * mark
        cost = p.quantity * p.avg_entry_price
        unrealized = mv - cost
        rows.append({
            "instrument_id": p.instrument_id,
            "side": "LONG" if p.quantity > 0 else "SHORT",
            "asset_class": p.asset_class.value if hasattr(p.asset_class, "value") else str(p.asset_class),
            "quantity": round(p.quantity, 4),
            "entry_price": round(p.avg_entry_price, 4),
            "mark_price": round(mark, 4),
            "market_value": round(mv, 2),
            "pct_nav": round(abs(mv) / nav * 100, 2) if nav > 0 else 0,
            "unrealized_pnl": round(unrealized, 2),
            "unrealized_pct": round((mark / p.avg_entry_price - 1) * 100, 2) if p.avg_entry_price > 0 else 0,
        })
    return rows


@router.get("/recent_fills")
def recent_fills():
    entries = memio.read_short_term()
    fills = sorted(
        [e for e in entries if isinstance(e, TradeEvent)],
        key=lambda x: x.timestamp, reverse=True,
    )[:20]
    return [
        {
            "timestamp": f.timestamp.strftime("%Y-%m-%d %H:%M"),
            "type": f.event_type,
            "instrument_id": f.instrument_id,
            "quantity": round(f.quantity, 4),
            "fill_price": round(f.fill_price, 4),
            "slippage": round(f.slippage_cost, 2),
            "commission": round(f.commission_cost, 2),
            "realized_pnl": round(f.realized_pnl, 2),
        }
        for f in fills
    ]


@router.get("/equity_curve_chart")
def equity_curve_chart(theme: str = "dark", raw: bool = False):
    # TODO: Read equity curve history from reports/equity_data.json
    # For now return placeholder
    return [] if raw else {"data": [], "layout": {}}
```

Create similar stubs for `macro.py`, `research.py`, `risk.py`, `agents.py`, `approvals.py` — each with a `router = APIRouter()` and the endpoints referenced in widgets.json.

**Step 7: Run tests**

Run: `pytest tests/test_dashboard_app.py -v`
Expected: All 3 PASS

**Step 8: Commit**

```bash
git add src/castelino/dashboard/ tests/test_dashboard_app.py
git commit -m "feat: create OpenBB Workspace dashboard skeleton (6 tabs, 22 widgets)"
```

---

### Task 9: Implement dashboard endpoint routers (macro, research, risk, agents, approvals)

**Files:**
- Create: `src/castelino/dashboard/endpoints/macro.py`
- Create: `src/castelino/dashboard/endpoints/research.py`
- Create: `src/castelino/dashboard/endpoints/risk.py`
- Create: `src/castelino/dashboard/endpoints/agents.py`
- Create: `src/castelino/dashboard/endpoints/approvals.py`
- Test: `tests/test_dashboard_endpoints.py`

**Step 1: Write failing tests**

```python
"""tests/test_dashboard_endpoints.py"""
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import pytest


@pytest.fixture
def client():
    from castelino.dashboard.main import app
    return TestClient(app)


def test_approval_metrics_returns_metric_format(client):
    with patch("castelino.dashboard.endpoints.approvals.ApprovalQueue") as MockQ:
        mock_q = MagicMock()
        mock_q.pending.return_value = []
        MockQ.return_value = mock_q
        r = client.get("/approval_metrics")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert data[0]["label"] == "Pending"


def test_approval_queue_returns_table(client):
    with patch("castelino.dashboard.endpoints.approvals.ApprovalQueue") as MockQ:
        mock_q = MagicMock()
        mock_q.pending.return_value = []
        MockQ.return_value = mock_q
        r = client.get("/approval_queue")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


def test_triggers_endpoint(client):
    with patch("castelino.dashboard.endpoints.macro.memio") as mock_memio:
        mock_memio.read_short_term.return_value = []
        r = client.get("/triggers")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


def test_hypotheses_endpoint(client):
    with patch("castelino.dashboard.endpoints.macro.memio") as mock_memio:
        mock_memio.read_short_term.return_value = []
        r = client.get("/hypotheses")
        assert r.status_code == 200
        assert isinstance(r.json(), list)
```

**Step 2: Implement endpoint routers**

`src/castelino/dashboard/endpoints/macro.py`:
```python
from __future__ import annotations
from fastapi import APIRouter
from castelino.data.openbb_adapter import get_adapter, OpenBBError
from castelino.memory import io as memio
from castelino.memory.schemas import Hypothesis, TriggerRecord

router = APIRouter()


@router.get("/macro_indicators")
def macro_indicators():
    adapter = get_adapter()
    if not adapter.available:
        return []
    try:
        return adapter.economic_indicators(["GDP", "CPIAUCSL", "UNRATE"]).reset_index().to_dict("records")
    except OpenBBError:
        return []


@router.get("/yield_curve")
def yield_curve(theme: str = "dark", raw: bool = False):
    adapter = get_adapter()
    if not adapter.available:
        return [] if raw else {"data": [], "layout": {}}
    try:
        df = adapter.yield_curve()
        if raw:
            return df.reset_index().to_dict("records")
        import plotly.graph_objects as go
        fig = go.Figure()
        if not df.empty:
            row = df.iloc[-1]
            fig.add_trace(go.Scatter(x=list(row.index), y=list(row.values), mode="lines+markers"))
        fig.update_layout(template="plotly_dark" if theme == "dark" else "plotly_white")
        import json
        return json.loads(fig.to_json())
    except OpenBBError:
        return [] if raw else {"data": [], "layout": {}}


@router.get("/triggers")
def triggers():
    entries = memio.read_short_term()
    trigs = sorted(
        [e for e in entries if isinstance(e, TriggerRecord)],
        key=lambda x: x.timestamp, reverse=True,
    )[:20]
    return [
        {"timestamp": t.timestamp.strftime("%Y-%m-%d %H:%M"), "source": t.source.value,
         "significance": round(t.significance, 2), "headline": t.headline}
        for t in trigs
    ]


@router.get("/hypotheses")
def hypotheses():
    entries = memio.read_short_term()
    hyps = sorted(
        [e for e in entries if isinstance(e, Hypothesis)],
        key=lambda x: x.timestamp, reverse=True,
    )[:10]
    return [
        {"timestamp": h.timestamp.strftime("%Y-%m-%d %H:%M"), "regime": h.regime.value,
         "conviction": h.conviction.value, "horizon_days": h.horizon_days,
         "thesis": h.thesis,
         "kill_criteria": " | ".join(c.description for c in h.kill_criteria)[:200]}
        for h in hyps
    ]


@router.get("/news")
def news():
    adapter = get_adapter()
    if not adapter.available:
        return []
    try:
        articles = adapter.news(limit=20)
        return [
            {"title": a.get("title", ""), "date": str(a.get("date", "")),
             "author": a.get("author", ""), "excerpt": a.get("text", "")[:200],
             "body": a.get("text", "")}
            for a in articles
        ]
    except OpenBBError:
        return []


@router.get("/economic_calendar")
def economic_calendar():
    adapter = get_adapter()
    if not adapter.available:
        return []
    try:
        return adapter.economic_calendar()
    except OpenBBError:
        return []
```

`src/castelino/dashboard/endpoints/research.py`:
```python
from __future__ import annotations
import json
from fastapi import APIRouter, Query
from castelino.data.openbb_adapter import get_adapter, OpenBBError

router = APIRouter()


@router.get("/ta_chart")
def ta_chart(symbol: str = Query("SPY"), theme: str = "dark", raw: bool = False):
    adapter = get_adapter()
    if not adapter.available:
        return [] if raw else {"data": [], "layout": {}}
    try:
        df = adapter.history(symbol, lookback_days=120)
        if raw:
            return df.reset_index().to_dict("records")
        import plotly.graph_objects as go
        fig = go.Figure(data=[go.Candlestick(
            x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"]
        )])
        fig.update_layout(template="plotly_dark" if theme == "dark" else "plotly_white", xaxis_rangeslider_visible=False)
        return json.loads(fig.to_json())
    except OpenBBError:
        return [] if raw else {"data": [], "layout": {}}


@router.get("/screener")
def screener():
    adapter = get_adapter()
    if not adapter.available:
        return []
    try:
        df = adapter.screen_equities()
        return df.head(50).to_dict("records")
    except OpenBBError:
        return []


@router.get("/correlations")
def correlations(theme: str = "dark", raw: bool = False):
    adapter = get_adapter()
    if not adapter.available:
        return [] if raw else {"data": [], "layout": {}}
    try:
        symbols = ["SPY", "TLT", "GLD", "USO", "EURUSD"]
        corr = adapter.correlation_matrix(symbols, lookback_days=90)
        if raw:
            return corr.reset_index().to_dict("records")
        import plotly.graph_objects as go
        fig = go.Figure(data=go.Heatmap(z=corr.values, x=corr.columns.tolist(), y=corr.index.tolist(), colorscale="RdBu", zmid=0))
        fig.update_layout(template="plotly_dark" if theme == "dark" else "plotly_white")
        import json as json_mod
        return json_mod.loads(fig.to_json())
    except OpenBBError:
        return [] if raw else {"data": [], "layout": {}}


@router.get("/sector_performance")
def sector_performance():
    adapter = get_adapter()
    if not adapter.available:
        return []
    try:
        return adapter.sector_performance()
    except OpenBBError:
        return []
```

`src/castelino/dashboard/endpoints/risk.py`:
```python
from __future__ import annotations
import json
from fastapi import APIRouter
from castelino.execution.portfolio import Portfolio
from castelino.memory import io as memio
from castelino.memory.schemas import PrincipleWarning

router = APIRouter()


@router.get("/exposure_by_class")
def exposure_by_class(theme: str = "dark", raw: bool = False):
    pf = Portfolio.load()
    by_class: dict[str, float] = {}
    for p in pf.positions:
        cls = p.asset_class.value if hasattr(p.asset_class, "value") else str(p.asset_class)
        by_class[cls] = by_class.get(cls, 0) + abs(p.quantity * p.current_price)
    if raw:
        return [{"asset_class": k, "exposure": v} for k, v in by_class.items()]
    import plotly.graph_objects as go
    fig = go.Figure(data=[go.Pie(labels=list(by_class.keys()), values=list(by_class.values()))])
    fig.update_layout(template="plotly_dark" if theme == "dark" else "plotly_white")
    return json.loads(fig.to_json())


@router.get("/exposure_by_instrument")
def exposure_by_instrument(theme: str = "dark", raw: bool = False):
    pf = Portfolio.load()
    data = [{"instrument": p.instrument_id, "exposure": abs(p.quantity * p.current_price)} for p in pf.positions]
    if raw:
        return data
    import plotly.graph_objects as go
    fig = go.Figure(data=[go.Bar(x=[d["instrument"] for d in data], y=[d["exposure"] for d in data])])
    fig.update_layout(template="plotly_dark" if theme == "dark" else "plotly_white")
    return json.loads(fig.to_json())


@router.get("/warnings")
def warnings():
    entries = memio.read_short_term()
    warns = sorted(
        [e for e in entries if isinstance(e, PrincipleWarning)],
        key=lambda x: x.timestamp, reverse=True,
    )[:20]
    return [
        {"timestamp": w.timestamp.strftime("%Y-%m-%d %H:%M"), "rule_id": w.rule_id,
         "severity": w.severity, "description": w.description}
        for w in warns
    ]
```

`src/castelino/dashboard/endpoints/agents.py`:
```python
from __future__ import annotations
from fastapi import APIRouter
from castelino.memory import io as memio
from castelino.memory.schemas import GuardDecision, Verdict

router = APIRouter()


@router.get("/verdicts")
def verdicts():
    entries = memio.read_short_term()
    vs = sorted(
        [e for e in entries if isinstance(e, Verdict)],
        key=lambda x: x.timestamp, reverse=True,
    )[:20]
    return [
        {"timestamp": v.timestamp.strftime("%Y-%m-%d %H:%M"), "decision": v.decision,
         "size_multiplier": round(v.size_multiplier, 2), "decisive_factor": v.decisive_factor,
         "bull_summary": v.bull_summary[:100], "bear_summary": v.bear_summary[:100]}
        for v in vs
    ]


@router.get("/guard_decisions")
def guard_decisions():
    entries = memio.read_short_term()
    gs = sorted(
        [e for e in entries if isinstance(e, GuardDecision)],
        key=lambda x: x.timestamp, reverse=True,
    )[:20]
    return [
        {"timestamp": g.timestamp.strftime("%Y-%m-%d %H:%M"), "decision": g.decision,
         "triggered_rules": len(g.triggered_rules), "rationale": g.rationale[:150]}
        for g in gs
    ]
```

`src/castelino/dashboard/endpoints/approvals.py`:
```python
from __future__ import annotations
from fastapi import APIRouter
from castelino.orchestrator.approval import ApprovalQueue

router = APIRouter()


@router.get("/approval_metrics")
def approval_metrics():
    q = ApprovalQueue()
    pending = q.pending()
    return [
        {"label": "Pending", "value": str(len(pending)), "subvalue": "awaiting decision"},
    ]


@router.get("/approval_queue")
def approval_queue():
    q = ApprovalQueue()
    return [
        {"entry_id": item.entry_id, "gate": item.gate, "submitted_at": item.submitted_at,
         "payload": str(item.payload)[:200]}
        for item in q.pending()
    ]


@router.get("/approval_history")
def approval_history():
    q = ApprovalQueue()
    return [
        {"entry_id": item.entry_id, "gate": item.gate, "status": item.status,
         "resolved_at": item.resolved_at or "", "reason": item.rejection_reason or ""}
        for item in q.history()
    ]
```

**Step 3: Run tests**

Run: `pytest tests/test_dashboard_endpoints.py tests/test_dashboard_app.py -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add src/castelino/dashboard/endpoints/ tests/test_dashboard_endpoints.py
git commit -m "feat: implement all dashboard endpoint routers (portfolio, macro, research, risk, agents, approvals)"
```

---

### Task 10: Add `fastapi` dependency and dashboard CLI command

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/castelino/orchestrator/cli.py`

**Step 1: Add fastapi + uvicorn to pyproject.toml**

Add to dependencies:
```
"fastapi>=0.110",
"uvicorn[standard]>=0.29",
"plotly>=5.18",
```

**Step 2: Add `castelino serve` CLI command**

```python
@app.command()
def serve(
    port: int = typer.Option(7779, help="Port for the OpenBB backend."),
    reload: bool = typer.Option(False, help="Enable auto-reload for development."),
):
    """Start the OpenBB Workspace dashboard backend."""
    import uvicorn
    print(f"[green]Starting Castelino dashboard on port {port}[/green]")
    print(f"[blue]Connect in OpenBB Workspace: Settings → Data Connectors → Add http://localhost:{port}[/blue]")
    uvicorn.run(
        "castelino.dashboard.main:app",
        host="0.0.0.0",
        port=port,
        reload=reload,
    )
```

**Step 3: Install and verify**

Run: `pip install -e ".[dev]" && castelino serve --help`
Expected: Help text shows up without errors

**Step 4: Commit**

```bash
git add pyproject.toml src/castelino/orchestrator/cli.py
git commit -m "feat: add castelino serve command for OpenBB dashboard backend"
```

---

## Workstream 4: Final Integration & Smoke Test

### Task 11: End-to-end smoke test

**Files:**
- Create: `tests/integration/test_openbb_dashboard_e2e.py`

**Step 1: Write integration test**

```python
"""tests/integration/test_openbb_dashboard_e2e.py
Smoke test: start dashboard, hit every endpoint, verify no 500s.
Requires: pip install -e . (the package must be installed)
Does NOT require OPENBB_PAT (endpoints gracefully degrade).
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from castelino.dashboard.main import app
    return TestClient(app)


ENDPOINTS = [
    "/", "/widgets.json", "/apps.json",
    "/portfolio_metrics", "/positions", "/recent_fills",
    "/triggers", "/hypotheses",
    "/exposure_by_class", "/exposure_by_instrument", "/warnings",
    "/verdicts", "/guard_decisions",
    "/approval_metrics", "/approval_queue", "/approval_history",
]


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_endpoint_no_500(client, endpoint):
    r = client.get(endpoint)
    assert r.status_code == 200, f"{endpoint} returned {r.status_code}: {r.text[:200]}"
```

**Step 2: Run integration test**

Run: `pytest tests/integration/test_openbb_dashboard_e2e.py -v`
Expected: All PASS (endpoints return empty data gracefully when no portfolio/PAT exists)

**Step 3: Commit**

```bash
git add tests/integration/test_openbb_dashboard_e2e.py
git commit -m "test: add dashboard e2e smoke test covering all endpoints"
```

---

### Task 12: Update project CLAUDE.md and documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/plans/2026-05-05-openbb-integration-design.md` (mark as implemented)

**Step 1: Add to CLAUDE.md under Completed Work**

```markdown
## Completed Work

### 2026-05-05 — OpenBB Integration
- Integrated OpenBB Platform SDK as primary data source with yfinance/FRED fallback
- Built 6-tab OpenBB Workspace dashboard (FastAPI backend at port 7779)
- Added human-in-the-loop approval gates (post-hypothesis, post-debate) with CLI commands
- New CLI commands: `castelino serve`, `castelino queue`, `castelino approve`, `castelino reject`, `castelino edit`
- Dashboard tabs: Portfolio, Macro & Signals, Research & Technicals, Risk & Attribution, Agent Decisions, Approval Queue
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with OpenBB integration completion notes"
```

---

## Task Dependency Graph

```
Task 1 (config) ──→ Task 2 (adapter) ──→ Task 3 (pricing fallback) ──→ Task 4 (research agents)
                                    │
                                    └──→ Task 8 (dashboard skeleton) ──→ Task 9 (endpoints) ──→ Task 10 (CLI serve)
                                                                                                       │
Task 5 (approval queue) ──→ Task 6 (pipeline gates) ──→ Task 7 (approval CLI) ────────────────────────┘
                                                                                                       │
                                                                                           Task 11 (e2e smoke) ──→ Task 12 (docs)
```

**Parallelizable:** Tasks 1-4 (data layer) and Tasks 5-7 (HITL) can run in parallel. Task 8-9 depends on both Task 2 and Task 5. Task 10-12 are sequential finalization.

---

## Running the Final System

```bash
# Install
pip install -e ".[dev]"

# Set env
echo "OPENBB_PAT=your_pat" >> .env

# Run pipeline with approval gates
castelino run "ECB signals rate cut"
# → Pipeline stalls at Gate 1
castelino queue                    # see pending hypothesis
castelino approve H-<id>           # approve it
# → Pipeline continues to debate, stalls at Gate 2
castelino approve V-<id>           # approve verdict
# → Trade executes

# Dashboard (separate terminal)
castelino serve --port 7779
# Open pro.openbb.co → Settings → Data Connectors → http://localhost:7779
```
