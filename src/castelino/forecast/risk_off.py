"""Risk-off forward classifier.

Predicts P(SPY draws down >5% peak-to-trough in the next 30 days) using
credit spreads, vol, dollar, and risk-appetite features. Independent from
the growth/inflation regime classifiers — this measures fragility, not regime.

Output drives the Risk-Off Gate (`triggers/risk_gate.py`), which sits between
the Constitutional Guard and Portfolio Agent in the pipeline.

Pattern mirrors `forecast/regime.py`: deterministic, no LLM, walk-forward
trained, output written to `data/risk_off_forecast.json`.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from castelino.config import ROOT, get_settings

log = logging.getLogger(__name__)

# Reuse FRED helper from the regime nowcaster — same pattern, same caching.
from castelino.forecast.regime import _fetch_fred_series, _to_month_end


FORECAST_PATH = ROOT / "data" / "risk_off_forecast.json"

FRED_FEATURES: list[tuple[str, str]] = [
    ("BAMLH0A0HYM2", "hy_oas"),       # ICE BofA US High Yield OAS
    ("BAMLC0A0CM", "ig_oas"),         # ICE BofA US IG OAS
    ("VIXCLS", "vix"),                # CBOE VIX
    ("DTWEXBGS", "dxy"),              # Trade-weighted USD broad
]

DRAWDOWN_THRESHOLD = -0.05  # 5% drop = positive label
WINDOW_DAYS = 30
HISTORY_START = "2000-01-01"


@dataclass(frozen=True)
class RiskOffForecast:
    prob_risk_off: float
    as_of: datetime
    feature_month: str
    target_month: str
    model_version: str = "v1"


def _fetch_yf_series(symbol: str, start: str = HISTORY_START) -> pd.Series:
    df = yf.download(symbol, start=start, progress=False, auto_adjust=True)
    if df is None or df.empty:
        raise RuntimeError(f"yfinance returned empty for {symbol!r}")
    return df["Close"].squeeze()


def _build_features() -> pd.DataFrame:
    """Pull all features, align to month-end, build lag-1/2/3 columns."""
    cols: dict[str, pd.Series] = {}

    for fred_id, alias in FRED_FEATURES:
        try:
            s = _to_month_end(_fetch_fred_series(fred_id))
            cols[alias] = s
        except Exception as e:
            log.warning("FRED %s unavailable: %s — skipping", fred_id, e)

    try:
        move = _to_month_end(_fetch_yf_series("^MOVE"))
        cols["move"] = move
    except Exception as e:
        log.warning("MOVE unavailable: %s — skipping", e)

    try:
        hyg = _to_month_end(_fetch_yf_series("HYG"))
        ief = _to_month_end(_fetch_yf_series("IEF"))
        cols["hyg_ief_ratio"] = hyg / ief
    except Exception as e:
        log.warning("HYG/IEF ratio unavailable: %s — skipping", e)

    df = pd.DataFrame(cols).sort_index()
    lagged: dict[str, pd.Series] = {}
    for col in df.columns:
        for lag in (1, 2, 3):
            lagged[f"{col}_lag{lag}"] = df[col].shift(lag)
    return pd.DataFrame(lagged, index=df.index).dropna(how="all")


def _build_label() -> pd.Series:
    """For each month-end t, label=1 if SPY drawdown < -5% in next 30 days."""
    spy = _fetch_yf_series("SPY")
    spy = spy.dropna()
    monthly_idx = pd.date_range(spy.index.min(), spy.index.max(), freq="ME")
    labels: dict[pd.Timestamp, int] = {}
    for t in monthly_idx:
        window_end = t + pd.Timedelta(days=WINDOW_DAYS)
        window = spy.loc[t:window_end]
        if len(window) < 5:
            continue
        peak = window.expanding().max()
        drawdown = (window / peak - 1).min()
        labels[t] = int(drawdown < DRAWDOWN_THRESHOLD)
    return pd.Series(labels, name="label").sort_index()


def train_and_predict() -> RiskOffForecast:
    """Train classifier on full history; predict current month."""
    try:
        from xgboost import XGBClassifier
    except ImportError as e:
        raise ImportError("xgboost required for risk_off forecaster") from e

    log.info("risk_off: building features + label")
    X_all = _build_features()
    y_all = _build_label()

    common_idx = X_all.index.intersection(y_all.index)
    X = X_all.loc[common_idx].copy()
    y = y_all.loc[common_idx].copy()

    train_mask = ~y.isna()
    train_mask &= ~X.isna().all(axis=1)
    X_train = X.loc[train_mask]
    y_train = y.loc[train_mask].astype(int)

    if len(X_train) < 60:
        raise RuntimeError(
            f"insufficient training data ({len(X_train)} rows) for risk_off"
        )

    pos = int(y_train.sum())
    neg = int((1 - y_train).sum())
    scale_pos = max(1.0, neg / max(pos, 1))

    model = XGBClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.05,
        scale_pos_weight=scale_pos,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        eval_metric="logloss",
    )
    model.fit(X_train.values, y_train.values)

    latest = X.iloc[[-1]].fillna(method="ffill").fillna(0)
    prob = float(model.predict_proba(latest.values)[0, 1])

    feature_month = X.index[-1].strftime("%Y-%m")
    target_month = (X.index[-1] + pd.offsets.MonthEnd(1)).strftime("%Y-%m")

    forecast = RiskOffForecast(
        prob_risk_off=round(prob, 4),
        as_of=datetime.now(UTC),
        feature_month=feature_month,
        target_month=target_month,
    )

    payload = {
        "prob_risk_off": forecast.prob_risk_off,
        "as_of": forecast.as_of.isoformat(),
        "feature_month": forecast.feature_month,
        "target_month": forecast.target_month,
        "model_version": forecast.model_version,
    }
    FORECAST_PATH.parent.mkdir(parents=True, exist_ok=True)
    FORECAST_PATH.write_text(json.dumps(payload, indent=2))
    log.info(
        "risk_off forecast: P=%.4f for %s (trained on %d samples, pos=%d)",
        prob, target_month, len(X_train), pos,
    )
    return forecast


def read_forecast() -> RiskOffForecast | None:
    """Read the latest forecast from disk. None if not yet generated."""
    if not FORECAST_PATH.exists():
        return None
    try:
        data = json.loads(FORECAST_PATH.read_text())
        return RiskOffForecast(
            prob_risk_off=float(data["prob_risk_off"]),
            as_of=datetime.fromisoformat(data["as_of"]),
            feature_month=data.get("feature_month", ""),
            target_month=data.get("target_month", ""),
            model_version=data.get("model_version", "v1"),
        )
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        log.warning("risk_off forecast unreadable: %s", e)
        return None
