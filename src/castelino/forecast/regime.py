"""Macro regime nowcaster — TWO independent month-ahead direction forecasters.

1. **Growth forecaster** — predicts:
       P( ISM_PMI(t+1) > ISM_PMI(t) | growth-specific features through t )
   Indicators: `data/growth_leading_indicators.yaml` (team-curated).

2. **Inflation forecaster** — predicts:
       P( CPI(t+1) > CPI(t) | inflation-specific features through t )      # MoM, level
   Indicators: `data/inflation_leading_indicators.yaml` (team-curated).

Each forecaster has its **own indicator list** and trains an **independent
XGBoost classifier**. The two are then combined by a downstream regime mapper
(authored separately) into a 4-quadrant label.

Indicators may come from FRED **or** yfinance:

- `source: fred`              → `fred_id` (e.g., `T10Y3M`, `BAMLH0A0HYM2`)
- `source: yfinance_close`    → `symbol`  (e.g., `^BCOM`)
- `source: yfinance_ratio`    → `numerator` / `denominator` (e.g., XLY/XLP)

Design rules
------------
- **Deterministic, no LLM math.** Outputs feed agents as facts.
- **Strict no-lookahead.** Features are lags (k≥1) of monthly-aggregated
  series. Target uses `value(t+1) > value(t)`; rows lacking either side
  are dropped before training.
- **Walk-forward CV** via `TimeSeriesSplit` for honest validation.
- **History start: 2000-01-01** (configurable).
- **Self-lags always included.** The target's own lagged values are
  appended automatically; user-supplied indicators are extra.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd
import requests
import yaml
from pydantic import BaseModel, Field
from sklearn.metrics import accuracy_score, brier_score_loss
from sklearn.model_selection import TimeSeriesSplit

try:
    from xgboost import XGBClassifier
except ImportError as e:  # pragma: no cover - exercised only if dep is missing
    raise ImportError(
        "xgboost is required for forecast.regime; pip install xgboost"
    ) from e

from castelino.config import ROOT, get_settings

log = logging.getLogger(__name__)


# ───────────────────────── default indicator-list paths ─────────────────


GROWTH_INDICATORS_YAML = ROOT / "data" / "growth_leading_indicators.yaml"
INFLATION_INDICATORS_YAML = ROOT / "data" / "inflation_leading_indicators.yaml"


# ───────────────────────── indicator spec ─────────────────────────────────


SOURCE_FRED = "fred"
SOURCE_YF_CLOSE = "yfinance_close"
SOURCE_YF_RATIO = "yfinance_ratio"


@dataclass(frozen=True)
class IndicatorSpec:
    """One indicator's identity + how to resolve it.

    `id` is the canonical alias used in feature column names + outputs. It
    must be unique inside an indicator list.
    """

    id: str
    source: str
    name: str = ""
    fred_id: Optional[str] = None
    yf_symbol: Optional[str] = None
    yf_numerator: Optional[str] = None
    yf_denominator: Optional[str] = None

    def validate(self) -> None:
        if self.source == SOURCE_FRED:
            if not self.fred_id:
                raise ValueError(f"{self.id}: fred source requires fred_id")
        elif self.source == SOURCE_YF_CLOSE:
            if not self.yf_symbol:
                raise ValueError(f"{self.id}: yfinance_close requires yf_symbol")
        elif self.source == SOURCE_YF_RATIO:
            if not (self.yf_numerator and self.yf_denominator):
                raise ValueError(f"{self.id}: yfinance_ratio requires numerator + denominator")
        else:
            raise ValueError(f"{self.id}: unknown source {self.source!r}")


# ───────────────────────── configuration / outputs ───────────────────────


@dataclass(frozen=True)
class IndicatorListConfig:
    """One target + a list of leading-indicator specs feeding it."""

    target: IndicatorSpec
    indicators: tuple[IndicatorSpec, ...]
    yaml_path: Path | None = None

    @classmethod
    def from_yaml(cls, path: str | Path) -> "IndicatorListConfig":
        p = Path(path)
        with p.open("r", encoding="utf-8") as f:
            doc = yaml.safe_load(f) or {}
        target_doc = dict(doc.get("target") or {})
        if not target_doc.get("fred_id") and not target_doc.get("yf_symbol"):
            raise ValueError(f"{p}: target must define fred_id or yf_symbol")
        target_doc.setdefault(
            "id",
            target_doc.get("fred_id") or target_doc.get("yf_symbol"),
        )
        target_spec = _row_to_spec(
            row=target_doc,
            default_source=SOURCE_FRED if target_doc.get("fred_id") else SOURCE_YF_CLOSE,
        )
        target_spec.validate()

        rows = doc.get("indicators") or []
        seen_ids: set[str] = set()
        specs: list[IndicatorSpec] = []
        for row in rows:
            if isinstance(row, str):
                # Bare-string short-form: FRED id
                row = {"id": row, "source": SOURCE_FRED, "fred_id": row}
            spec = _row_to_spec(row, default_source=SOURCE_FRED)
            spec.validate()
            if spec.id == target_spec.id:
                # Don't double-add the target as an indicator; self-lags are added by feature builder.
                continue
            if spec.id in seen_ids:
                raise ValueError(f"{p}: duplicate indicator id {spec.id!r}")
            seen_ids.add(spec.id)
            specs.append(spec)
        return cls(target=target_spec, indicators=tuple(specs), yaml_path=p)


def _row_to_spec(row: dict, default_source: str) -> IndicatorSpec:
    src = row.get("source") or default_source
    iid = row.get("id")
    if not iid:
        # Fall back to FRED id, then yf_symbol, then ratio.
        iid = row.get("fred_id") or row.get("symbol") or row.get("yf_symbol")
        if not iid and row.get("numerator") and row.get("denominator"):
            iid = f"{row['numerator']}_div_{row['denominator']}"
    if not iid:
        raise ValueError(f"Indicator row missing id and identifier: {row}")
    return IndicatorSpec(
        id=str(iid),
        source=str(src),
        name=str(row.get("name") or ""),
        fred_id=row.get("fred_id"),
        yf_symbol=row.get("symbol") or row.get("yf_symbol"),
        yf_numerator=row.get("numerator") or row.get("yf_numerator"),
        yf_denominator=row.get("denominator") or row.get("yf_denominator"),
    )


@dataclass(frozen=True)
class TrainingConfig:
    history_start: str = "2000-01-01"
    n_lags: int = 6
    cv_splits: int = 5
    random_state: int = 0
    n_estimators: int = 400
    max_depth: int = 3
    learning_rate: float = 0.05
    # Forecast horizon. lead_months=1 → predict next month MoM direction
    # (`value(t+1) > value(t)`). lead_months=2 → predict month-after-next
    # (`value(t+2) > value(t+1)`). Increasing the lead drops more recent rows
    # from the training set since their labels live further in the future.
    lead_months: int = 1


class _ModelMetrics(BaseModel):
    accuracy: float
    brier: float
    n_test: int


class _DirectionForecast(BaseModel):
    """Shared shape for both growth and inflation outputs."""

    asof: datetime = Field(default_factory=lambda: datetime.now(UTC))
    target_id: str
    target_name: str
    feature_month: str
    target_month: str
    lead_months: int = 1
    up: bool
    prob_up: float = Field(ge=0.0, le=1.0)
    indicators_used: list[str]
    train_metrics: _ModelMetrics | None = None
    history_start: str
    n_obs: int

    def to_json(self, indent: int | None = 2) -> str:
        return self.model_dump_json(indent=indent)


class GrowthForecast(_DirectionForecast):
    pass


class InflationForecast(_DirectionForecast):
    pass


class RegimeForecast(BaseModel):
    """Bundle of the two independent forecasts; consumed by the regime mapper."""

    asof: datetime = Field(default_factory=lambda: datetime.now(UTC))
    growth: GrowthForecast
    inflation: InflationForecast

    def to_json(self, indent: int | None = 2) -> str:
        return self.model_dump_json(indent=indent)


# ───────────────────────── data fetch ────────────────────────────────────


def _fetch_fred_series(series_id: str) -> pd.Series:
    """Date-indexed (monotonic) float Series for a FRED id.

    JSON API with key when present, else keyless CSV endpoint.
    """
    key = get_settings().fred_api_key
    if key:
        url = (
            "https://api.stlouisfed.org/fred/series/observations"
            f"?series_id={series_id}&api_key={key}&file_type=json"
        )
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        rows = payload.get("observations", [])
        if not rows:
            raise RuntimeError(f"FRED returned no observations for {series_id}")
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna(subset=["value"]).set_index("date").sort_index()
        return df["value"].astype(float).rename(series_id)

    # Force full history; default endpoint truncates some series (e.g. HY OAS).
    url = (
        "https://fred.stlouisfed.org/graph/fredgraph.csv"
        f"?id={series_id}&cosd=1900-01-01&coed=2030-12-31"
    )
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    df = pd.read_csv(StringIO(resp.text))
    date_col, val_col = df.columns[0], df.columns[1]
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.set_index(date_col).sort_index()
    df[val_col] = pd.to_numeric(df[val_col], errors="coerce")
    return df[val_col].dropna().astype(float).rename(series_id)


def _fetch_yf_close(symbol: str) -> pd.Series:
    """Daily close series from yfinance (full available history)."""
    import yfinance as yf
    t = yf.Ticker(symbol)
    df = t.history(period="max", auto_adjust=True)
    if df is None or df.empty:
        raise RuntimeError(f"yfinance returned empty for {symbol}")
    s = df["Close"].copy()
    s.index = pd.to_datetime(s.index).tz_localize(None)
    return s.astype(float).rename(symbol)


def _to_month_end(s: pd.Series) -> pd.Series:
    """Resample to month-end mean."""
    return s.resample("ME").mean()


SeriesProvider = Callable[[list[IndicatorSpec]], dict[str, pd.Series]]


def _default_series_provider(specs: list[IndicatorSpec]) -> dict[str, pd.Series]:
    out: dict[str, pd.Series] = {}
    for spec in specs:
        try:
            out[spec.id] = _resolve_spec(spec)
        except Exception as e:
            log.warning("Skipping indicator %s (%s): %s", spec.id, spec.source, e)
    return out


def _resolve_spec(spec: IndicatorSpec) -> pd.Series:
    if spec.source == SOURCE_FRED:
        assert spec.fred_id is not None
        return _fetch_fred_series(spec.fred_id).rename(spec.id)
    if spec.source == SOURCE_YF_CLOSE:
        assert spec.yf_symbol is not None
        return _fetch_yf_close(spec.yf_symbol).rename(spec.id)
    if spec.source == SOURCE_YF_RATIO:
        assert spec.yf_numerator and spec.yf_denominator
        num = _fetch_yf_close(spec.yf_numerator)
        den = _fetch_yf_close(spec.yf_denominator)
        # Align by date intersection so the ratio uses concurrent observations.
        joined = pd.concat([num, den], axis=1, join="inner").dropna()
        ratio = joined.iloc[:, 0] / joined.iloc[:, 1]
        return ratio.rename(spec.id)
    raise ValueError(f"Unknown source: {spec.source}")


# ───────────────────────── feature engineering ───────────────────────────


def _build_feature_table(
    series_map: dict[str, pd.Series],
    n_lags: int,
    history_start: str,
) -> pd.DataFrame:
    """Pure-lag feature matrix. Columns: `<id>_lag_<k>` for k in 1..n_lags."""
    monthly: dict[str, pd.Series] = {}
    for sid, s in series_map.items():
        s = s.copy()
        s.index = pd.to_datetime(s.index)
        if not s.index.is_monotonic_increasing:
            s = s.sort_index()
        s = _to_month_end(s)
        monthly[sid] = s
    if not monthly:
        return pd.DataFrame()

    df = pd.DataFrame(monthly)
    df = df.loc[df.index >= pd.Timestamp(history_start)]
    df = df.dropna(how="all")

    feats = pd.DataFrame(index=df.index)
    for sid in df.columns:
        for k in range(1, n_lags + 1):
            feats[f"{sid}_lag_{k}"] = df[sid].shift(k)
    return feats


def _build_targets(
    primary: pd.Series,
    history_start: str,
    lead_months: int = 1,
) -> pd.Series:
    """Binary label at month `t`: `value(t + lead) > value(t + lead - 1)`.

    For `lead=1` this collapses to the standard "next-month MoM up?" target.
    For `lead=2` (used when current-month data hasn't been published) the
    label asks "will MoM be up two months from now?" — features at `t` are
    used to predict the move from `t+1` to `t+2`.
    """
    if lead_months < 1:
        raise ValueError("lead_months must be >= 1")
    p = primary.copy()
    p.index = pd.to_datetime(p.index)
    p = _to_month_end(p)
    p = p.loc[p.index >= pd.Timestamp(history_start)]
    next_change = p.shift(-lead_months) - p.shift(-(lead_months - 1))
    return (next_change > 0).astype(int).rename("y")


# ───────────────────────── modelling helpers ─────────────────────────────


def _make_model(cfg: TrainingConfig) -> XGBClassifier:
    return XGBClassifier(
        n_estimators=cfg.n_estimators,
        max_depth=cfg.max_depth,
        learning_rate=cfg.learning_rate,
        objective="binary:logistic",
        eval_metric="logloss",
        tree_method="hist",
        random_state=cfg.random_state,
    )


def _walk_forward_eval(
    X: pd.DataFrame, y: pd.Series, cfg: TrainingConfig
) -> _ModelMetrics:
    if len(X) < cfg.cv_splits + 5:
        return _ModelMetrics(accuracy=float("nan"), brier=float("nan"), n_test=0)

    tscv = TimeSeriesSplit(n_splits=cfg.cv_splits)
    accs: list[float] = []
    briers: list[float] = []
    n_test_total = 0
    for tr, te in tscv.split(X):
        Xtr, Xte = X.iloc[tr], X.iloc[te]
        ytr, yte = y.iloc[tr], y.iloc[te]
        if ytr.nunique() < 2 or yte.nunique() < 1:
            continue
        m = _make_model(cfg)
        m.fit(Xtr, ytr, verbose=False)
        proba = m.predict_proba(Xte)[:, 1]
        pred = (proba >= 0.5).astype(int)
        accs.append(float(accuracy_score(yte, pred)))
        briers.append(float(brier_score_loss(yte, proba)))
        n_test_total += len(yte)
    if not accs:
        return _ModelMetrics(accuracy=float("nan"), brier=float("nan"), n_test=0)
    return _ModelMetrics(
        accuracy=float(np.mean(accs)),
        brier=float(np.mean(briers)),
        n_test=n_test_total,
    )


def _align(feats: pd.DataFrame, y: pd.Series) -> tuple[pd.DataFrame, pd.Series]:
    """Drop rows where the target is missing OR every feature is NaN.

    XGBoost handles missing feature values natively; we only need the label
    and at least one non-NaN feature for the row to be useful for training.
    Letting XGBoost see NaN keeps rows where some indicators have been
    discontinued (e.g. USSLIND after 2020) without throwing them away.
    """
    df = feats.join(y, how="inner")
    df = df.dropna(subset=["y"])
    if df.empty:
        return df.drop(columns=["y"]), df["y"].astype(int) if not df.empty else df.get("y", pd.Series(dtype=int))
    feat_cols = [c for c in df.columns if c != "y"]
    has_any_feature = df[feat_cols].notna().any(axis=1)
    df = df.loc[has_any_feature]
    return df[feat_cols], df["y"].astype(int)


# ───────────────────────── core trainer ──────────────────────────────────


def _train_independent(
    *,
    indicator_cfg: IndicatorListConfig,
    training_cfg: TrainingConfig,
    series_provider: SeriesProvider,
) -> dict:
    specs: list[IndicatorSpec] = [indicator_cfg.target, *indicator_cfg.indicators]
    series_map = series_provider(specs)

    if indicator_cfg.target.id not in series_map:
        raise KeyError(
            f"Required target series {indicator_cfg.target.id} missing from provider output."
        )

    feats = _build_feature_table(series_map, training_cfg.n_lags, training_cfg.history_start)
    y = _build_targets(
        series_map[indicator_cfg.target.id],
        training_cfg.history_start,
        lead_months=training_cfg.lead_months,
    )
    X, y_aligned = _align(feats, y)

    metrics = _walk_forward_eval(X, y_aligned, training_cfg)

    target_monthly = _to_month_end(series_map[indicator_cfg.target.id]).dropna()
    if target_monthly.empty:
        raise RuntimeError(f"Target {indicator_cfg.target.id} produced no monthly observations.")
    last_month = pd.Timestamp(target_monthly.index.max())
    target_month = (last_month + pd.offsets.MonthEnd(training_cfg.lead_months))

    if y_aligned.nunique() < 2:
        log.warning("Single-class target for %s; cannot train classifier.", indicator_cfg.target.id)
        prob = float(y_aligned.mean()) if len(y_aligned) else 0.5
        return dict(
            up=bool(prob >= 0.5),
            prob_up=prob,
            metrics=metrics,
            n_obs=int(len(y_aligned)),
            indicators_used=list(series_map.keys()),
            feature_month=last_month.strftime("%Y-%m-01"),
            target_month=target_month.strftime("%Y-%m-01"),
        )

    model = _make_model(training_cfg)
    model.fit(X, y_aligned, verbose=False)

    # XGBoost handles NaN features natively, so we predict on the most recent
    # feature row (where the target itself is the t+1 we want to forecast).
    if feats.empty:
        log.warning("No feature rows for %s; falling back to base rate.", indicator_cfg.target.id)
        prob = float(y_aligned.mean())
    else:
        last_row = feats.iloc[[-1]]
        prob = float(model.predict_proba(last_row)[0, 1])

    return dict(
        up=bool(prob >= 0.5),
        prob_up=prob,
        metrics=metrics,
        n_obs=int(len(y_aligned)),
        indicators_used=list(series_map.keys()),
        feature_month=last_month.strftime("%Y-%m-01"),
        target_month=target_month.strftime("%Y-%m-01"),
    )


# ───────────────────────── public entrypoints ────────────────────────────


def train_growth_forecast(
    *,
    indicator_cfg: IndicatorListConfig | None = None,
    training_cfg: TrainingConfig | None = None,
    series_provider: SeriesProvider | None = None,
) -> GrowthForecast:
    cfg = indicator_cfg or IndicatorListConfig.from_yaml(GROWTH_INDICATORS_YAML)
    training = training_cfg or TrainingConfig()
    provider = series_provider or _default_series_provider
    res = _train_independent(indicator_cfg=cfg, training_cfg=training, series_provider=provider)
    return GrowthForecast(
        target_id=cfg.target.id,
        target_name=cfg.target.name or cfg.target.id,
        feature_month=res["feature_month"],
        target_month=res["target_month"],
        lead_months=training.lead_months,
        up=res["up"],
        prob_up=res["prob_up"],
        indicators_used=res["indicators_used"],
        train_metrics=res["metrics"],
        history_start=training.history_start,
        n_obs=res["n_obs"],
    )


def train_inflation_forecast(
    *,
    indicator_cfg: IndicatorListConfig | None = None,
    training_cfg: TrainingConfig | None = None,
    series_provider: SeriesProvider | None = None,
) -> InflationForecast:
    cfg = indicator_cfg or IndicatorListConfig.from_yaml(INFLATION_INDICATORS_YAML)
    training = training_cfg or TrainingConfig()
    provider = series_provider or _default_series_provider
    res = _train_independent(indicator_cfg=cfg, training_cfg=training, series_provider=provider)
    return InflationForecast(
        target_id=cfg.target.id,
        target_name=cfg.target.name or cfg.target.id,
        feature_month=res["feature_month"],
        target_month=res["target_month"],
        lead_months=training.lead_months,
        up=res["up"],
        prob_up=res["prob_up"],
        indicators_used=res["indicators_used"],
        train_metrics=res["metrics"],
        history_start=training.history_start,
        n_obs=res["n_obs"],
    )


def train_and_forecast(
    *,
    growth_cfg: IndicatorListConfig | None = None,
    inflation_cfg: IndicatorListConfig | None = None,
    training_cfg: TrainingConfig | None = None,
    growth_provider: SeriesProvider | None = None,
    inflation_provider: SeriesProvider | None = None,
) -> RegimeForecast:
    """Run the two forecasters independently and bundle their outputs."""
    growth = train_growth_forecast(
        indicator_cfg=growth_cfg,
        training_cfg=training_cfg,
        series_provider=growth_provider,
    )
    inflation = train_inflation_forecast(
        indicator_cfg=inflation_cfg,
        training_cfg=training_cfg,
        series_provider=inflation_provider,
    )
    return RegimeForecast(growth=growth, inflation=inflation)


def walk_forward_metrics(
    *,
    indicator_cfg: IndicatorListConfig,
    training_cfg: TrainingConfig | None = None,
    series_provider: SeriesProvider | None = None,
) -> _ModelMetrics:
    training = training_cfg or TrainingConfig()
    provider = series_provider or _default_series_provider
    specs = [indicator_cfg.target, *indicator_cfg.indicators]
    series_map = provider(specs)
    feats = _build_feature_table(series_map, training.n_lags, training.history_start)
    y = _build_targets(
        series_map[indicator_cfg.target.id],
        training.history_start,
        lead_months=training.lead_months,
    )
    X, y_aligned = _align(feats, y)
    return _walk_forward_eval(X, y_aligned, training)


# ───────────────────────── persistence helpers ───────────────────────────


def write_forecast(
    forecast: RegimeForecast,
    path: Path | None = None,
) -> Path:
    cfg = get_settings()
    out_dir = cfg.resolved_paths.data
    out_dir.mkdir(parents=True, exist_ok=True)
    out = path or (out_dir / "regime_forecast.json")
    out.write_text(forecast.to_json())
    return out


def read_forecast(path: Path | None = None) -> RegimeForecast | None:
    cfg = get_settings()
    p = path or (cfg.resolved_paths.data / "regime_forecast.json")
    if not p.is_file():
        return None
    return RegimeForecast.model_validate_json(p.read_text())
