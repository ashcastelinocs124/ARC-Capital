"""OpenBB Platform adapter — optional enrichment layer for pricing, TA, fundamentals, and macro.

Wraps the OpenBB SDK with lazy initialization: if the `openbb` package is not
installed or `OPENBB_PAT` is missing, the adapter degrades gracefully
(``adapter.available == False``). All public methods raise ``OpenBBError`` on
failure so callers can catch and fall back to yfinance/FRED.

Usage:
    from castelino.data.openbb_adapter import get_adapter, OpenBBError

    adapter = get_adapter()
    if adapter.available:
        price = adapter.latest_price("AAPL")
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, date
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public exception
# ---------------------------------------------------------------------------


class OpenBBError(RuntimeError):
    """Raised when an OpenBB SDK call fails or the adapter is unavailable."""


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OBBPrice:
    """A single price point returned by the adapter."""

    instrument_id: str
    price: float
    asof: datetime


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class OpenBBAdapter:
    """Thin wrapper around the OpenBB Platform SDK.

    Lazily imports ``openbb`` only on first use to avoid import-time failures
    when the package is not installed. If the PAT (Personal Access Token) is not
    configured, all methods will raise ``OpenBBError``.
    """

    def __init__(self) -> None:
        self._sdk: Any | None = None
        self._available: bool | None = None  # tri-state: None = not checked yet

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        """True if the OpenBB SDK is importable and a PAT is configured."""
        if self._available is None:
            self._available = self._try_init()
        return self._available

    def _try_init(self) -> bool:
        """Attempt to import and authenticate with OpenBB. Returns success."""
        pat = os.environ.get("OPENBB_PAT", "").strip()
        if not pat:
            log.info("OpenBB adapter disabled: OPENBB_PAT not set")
            return False
        try:
            from openbb import obb  # type: ignore[import-untyped]

            obb.account.login(pat=pat)  # type: ignore[attr-defined]
            self._sdk = obb
            log.info("OpenBB adapter initialized successfully")
            return True
        except ImportError:
            log.info("OpenBB adapter disabled: openbb package not installed")
            return False
        except Exception as exc:  # noqa: BLE001
            log.warning("OpenBB adapter initialization failed: %s", exc)
            return False

    def _ensure_available(self) -> Any:
        """Return the SDK instance or raise ``OpenBBError``."""
        if not self.available:
            raise OpenBBError(
                "OpenBB SDK is not available. Install `openbb` and set OPENBB_PAT."
            )
        return self._sdk

    # ------------------------------------------------------------------
    # Pricing
    # ------------------------------------------------------------------

    def latest_price(self, symbol: str) -> OBBPrice:
        """Fetch the most recent price for *symbol*.

        Returns an ``OBBPrice`` dataclass.
        """
        obb = self._ensure_available()
        try:
            result = obb.equity.price.quote(symbol=symbol)
            data = self._extract_results(result)
            if not data:
                raise OpenBBError(f"No quote data returned for {symbol}")
            record = data[0] if isinstance(data, list) else data
            price = float(record.get("last_price") or record.get("close") or record.get("price", 0))
            asof_raw = record.get("date") or record.get("timestamp") or datetime.utcnow()
            asof = self._parse_datetime(asof_raw)
            return OBBPrice(instrument_id=symbol, price=price, asof=asof)
        except OpenBBError:
            raise
        except Exception as exc:
            raise OpenBBError(f"Failed to fetch latest price for {symbol}: {exc}") from exc

    def history(self, symbol: str, lookback_days: int = 252) -> pd.DataFrame:
        """Fetch OHLCV history for *symbol* over *lookback_days*.

        Returns a DataFrame with columns: open, high, low, close, volume,
        indexed by date.
        """
        obb = self._ensure_available()
        try:
            end = date.today()
            start = end - pd.Timedelta(days=lookback_days)
            result = obb.equity.price.historical(
                symbol=symbol,
                start_date=start.isoformat(),
                end_date=end.isoformat(),
            )
            data = self._extract_results(result)
            if not data:
                raise OpenBBError(f"No history data returned for {symbol}")
            df = pd.DataFrame(data)
            # Normalize columns
            col_map = {c: c.lower() for c in df.columns}
            df = df.rename(columns=col_map)
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date")
            cols = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
            return df[cols]
        except OpenBBError:
            raise
        except Exception as exc:
            raise OpenBBError(f"Failed to fetch history for {symbol}: {exc}") from exc

    # ------------------------------------------------------------------
    # Technical analysis
    # ------------------------------------------------------------------

    def technical_indicators(
        self, symbol: str, indicators: list[str] | None = None
    ) -> dict[str, Any]:
        """Compute technical indicators for *symbol*.

        *indicators* defaults to ``["rsi", "macd", "bbands"]``.
        Returns a dict mapping indicator name to its computed values.
        """
        obb = self._ensure_available()
        if indicators is None:
            indicators = ["rsi", "macd", "bbands"]

        results: dict[str, Any] = {}
        try:
            for ind in indicators:
                ind_lower = ind.lower()
                if ind_lower == "rsi":
                    r = obb.technical.rsi(symbol=symbol)
                    results["rsi"] = self._extract_results(r)
                elif ind_lower == "macd":
                    r = obb.technical.macd(symbol=symbol)
                    results["macd"] = self._extract_results(r)
                elif ind_lower == "bbands":
                    r = obb.technical.bbands(symbol=symbol)
                    results["bbands"] = self._extract_results(r)
                else:
                    log.warning("Unknown technical indicator: %s", ind)
            return results
        except OpenBBError:
            raise
        except Exception as exc:
            raise OpenBBError(
                f"Failed to compute technical indicators for {symbol}: {exc}"
            ) from exc

    def moving_averages(
        self, symbol: str, windows: list[int] | None = None
    ) -> pd.DataFrame:
        """Compute simple moving averages for *symbol*.

        *windows* defaults to ``[20, 50, 200]``.
        Returns a DataFrame with columns ``sma_<N>`` for each window.
        """
        if windows is None:
            windows = [20, 50, 200]

        try:
            df = self.history(symbol, lookback_days=max(windows) + 50)
            result = pd.DataFrame(index=df.index)
            for w in windows:
                result[f"sma_{w}"] = df["close"].rolling(window=w).mean()
            return result
        except OpenBBError:
            raise
        except Exception as exc:
            raise OpenBBError(
                f"Failed to compute moving averages for {symbol}: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Fundamentals
    # ------------------------------------------------------------------

    def income_statement(self, symbol: str) -> pd.DataFrame:
        """Fetch income statement data for *symbol*."""
        obb = self._ensure_available()
        try:
            result = obb.equity.fundamental.income(symbol=symbol)
            data = self._extract_results(result)
            if not data:
                raise OpenBBError(f"No income statement data for {symbol}")
            return pd.DataFrame(data)
        except OpenBBError:
            raise
        except Exception as exc:
            raise OpenBBError(
                f"Failed to fetch income statement for {symbol}: {exc}"
            ) from exc

    def balance_sheet(self, symbol: str) -> pd.DataFrame:
        """Fetch balance sheet data for *symbol*."""
        obb = self._ensure_available()
        try:
            result = obb.equity.fundamental.balance(symbol=symbol)
            data = self._extract_results(result)
            if not data:
                raise OpenBBError(f"No balance sheet data for {symbol}")
            return pd.DataFrame(data)
        except OpenBBError:
            raise
        except Exception as exc:
            raise OpenBBError(
                f"Failed to fetch balance sheet for {symbol}: {exc}"
            ) from exc

    def analyst_estimates(self, symbol: str) -> list[dict[str, Any]]:
        """Fetch analyst estimates for *symbol*."""
        obb = self._ensure_available()
        try:
            result = obb.equity.estimates.consensus(symbol=symbol)
            data = self._extract_results(result)
            if not data:
                return []
            return data if isinstance(data, list) else [data]
        except OpenBBError:
            raise
        except Exception as exc:
            raise OpenBBError(
                f"Failed to fetch analyst estimates for {symbol}: {exc}"
            ) from exc

    def earnings_calendar(
        self, start: str | None = None, end: str | None = None
    ) -> list[dict[str, Any]]:
        """Fetch upcoming earnings calendar."""
        obb = self._ensure_available()
        try:
            kwargs: dict[str, Any] = {}
            if start:
                kwargs["start_date"] = start
            if end:
                kwargs["end_date"] = end
            result = obb.equity.calendar.earnings(**kwargs)
            data = self._extract_results(result)
            if not data:
                return []
            return data if isinstance(data, list) else [data]
        except OpenBBError:
            raise
        except Exception as exc:
            raise OpenBBError(f"Failed to fetch earnings calendar: {exc}") from exc

    # ------------------------------------------------------------------
    # Screening
    # ------------------------------------------------------------------

    def screen_equities(self, **filters: Any) -> pd.DataFrame:
        """Screen equities using provided *filters*."""
        obb = self._ensure_available()
        try:
            result = obb.equity.screener(provider="fmp", **filters)
            data = self._extract_results(result)
            if not data:
                return pd.DataFrame()
            return pd.DataFrame(data)
        except OpenBBError:
            raise
        except Exception as exc:
            raise OpenBBError(f"Failed to screen equities: {exc}") from exc

    def sector_performance(self) -> list[dict[str, Any]]:
        """Fetch sector performance data."""
        obb = self._ensure_available()
        try:
            result = obb.equity.performance.sector()
            data = self._extract_results(result)
            if not data:
                return []
            return data if isinstance(data, list) else [data]
        except OpenBBError:
            raise
        except Exception as exc:
            raise OpenBBError(f"Failed to fetch sector performance: {exc}") from exc

    # ------------------------------------------------------------------
    # Quantitative
    # ------------------------------------------------------------------

    def correlation_matrix(
        self, symbols: list[str], lookback_days: int = 90
    ) -> pd.DataFrame:
        """Compute correlation matrix for *symbols* over *lookback_days*.

        Uses close prices from history. Returns a square DataFrame.
        """
        try:
            frames: dict[str, pd.Series] = {}
            for sym in symbols:
                df = self.history(sym, lookback_days=lookback_days)
                if not df.empty:
                    frames[sym] = df["close"]
            if not frames:
                raise OpenBBError("No data available for correlation computation")
            combined = pd.DataFrame(frames)
            return combined.pct_change().dropna().corr()
        except OpenBBError:
            raise
        except Exception as exc:
            raise OpenBBError(f"Failed to compute correlation matrix: {exc}") from exc

    # ------------------------------------------------------------------
    # Macro / Economy
    # ------------------------------------------------------------------

    def economic_indicators(self, series_ids: list[str]) -> pd.DataFrame:
        """Fetch economic indicator series (e.g., GDP, CPI, unemployment)."""
        obb = self._ensure_available()
        try:
            frames: list[pd.DataFrame] = []
            for sid in series_ids:
                result = obb.economy.indicators(symbol=sid)
                data = self._extract_results(result)
                if data:
                    df = pd.DataFrame(data)
                    if "date" in df.columns:
                        df["date"] = pd.to_datetime(df["date"])
                        df = df.set_index("date")
                    df = df.rename(columns={"value": sid})
                    frames.append(df[[sid]] if sid in df.columns else df)
            if not frames:
                raise OpenBBError(f"No data for series: {series_ids}")
            return pd.concat(frames, axis=1)
        except OpenBBError:
            raise
        except Exception as exc:
            raise OpenBBError(
                f"Failed to fetch economic indicators: {exc}"
            ) from exc

    def economic_calendar(
        self, start: str | None = None, end: str | None = None
    ) -> list[dict[str, Any]]:
        """Fetch economic calendar events."""
        obb = self._ensure_available()
        try:
            kwargs: dict[str, Any] = {}
            if start:
                kwargs["start_date"] = start
            if end:
                kwargs["end_date"] = end
            result = obb.economy.calendar(**kwargs)
            data = self._extract_results(result)
            if not data:
                return []
            return data if isinstance(data, list) else [data]
        except OpenBBError:
            raise
        except Exception as exc:
            raise OpenBBError(f"Failed to fetch economic calendar: {exc}") from exc

    def yield_curve(self) -> pd.DataFrame:
        """Fetch the current US Treasury yield curve."""
        obb = self._ensure_available()
        try:
            result = obb.fixedincome.rate.treasury(provider="federal_reserve")
            data = self._extract_results(result)
            if not data:
                raise OpenBBError("No yield curve data returned")
            return pd.DataFrame(data)
        except OpenBBError:
            raise
        except Exception as exc:
            raise OpenBBError(f"Failed to fetch yield curve: {exc}") from exc

    # ------------------------------------------------------------------
    # News
    # ------------------------------------------------------------------

    def news(self, query: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        """Fetch financial news, optionally filtered by *query*."""
        obb = self._ensure_available()
        try:
            kwargs: dict[str, Any] = {"limit": limit}
            if query:
                kwargs["query"] = query
            result = obb.news.world(**kwargs)
            data = self._extract_results(result)
            if not data:
                return []
            return data if isinstance(data, list) else [data]
        except OpenBBError:
            raise
        except Exception as exc:
            raise OpenBBError(f"Failed to fetch news: {exc}") from exc

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_results(result: Any) -> list[dict[str, Any]]:
        """Normalize an OBBject result to a list of dicts.

        The OpenBB SDK returns ``OBBject`` instances. We extract data via
        ``.results`` (list of model instances) or ``.to_dict()`` depending on
        SDK version.
        """
        if result is None:
            return []
        # OBBject.results is the canonical accessor
        if hasattr(result, "results"):
            results = result.results
            if results is None:
                return []
            if isinstance(results, list):
                return [
                    r.model_dump() if hasattr(r, "model_dump") else dict(r)
                    for r in results
                ]
            if hasattr(results, "model_dump"):
                return [results.model_dump()]
            return [dict(results)]
        # Fallback: to_df / to_dict
        if hasattr(result, "to_df"):
            return result.to_df().to_dict("records")
        return []

    @staticmethod
    def _parse_datetime(value: Any) -> datetime:
        """Best-effort parse of a datetime value from SDK responses."""
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime(value.year, value.month, value.day)
        if isinstance(value, str):
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
        return datetime.utcnow()


# ---------------------------------------------------------------------------
# Singleton management
# ---------------------------------------------------------------------------

_adapter: OpenBBAdapter | None = None


def get_adapter() -> OpenBBAdapter:
    """Return the module-level singleton adapter instance."""
    global _adapter  # noqa: PLW0603
    if _adapter is None:
        _adapter = OpenBBAdapter()
    return _adapter


def reset_adapter() -> None:
    """Reset the singleton — useful in tests or after config changes."""
    global _adapter  # noqa: PLW0603
    _adapter = None
