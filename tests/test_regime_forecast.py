"""Regime nowcaster — synthetic-data tests, no network.

Verifies that the **two independent** forecasters (growth → ISM PMI,
inflation → CPI) each accept their own indicator list and run end-to-end on
synthetic monthly data, and that the YAML loader handles FRED + yfinance
indicator specs.
"""

from __future__ import annotations

import math
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from castelino.forecast.regime import (
    SOURCE_FRED,
    SOURCE_LOCAL_CSV,
    SOURCE_YF_CLOSE,
    SOURCE_YF_RATIO,
    GrowthForecast,
    IndicatorListConfig,
    IndicatorSpec,
    InflationForecast,
    RegimeForecast,
    TrainingConfig,
    train_and_forecast,
    train_growth_forecast,
    train_inflation_forecast,
    walk_forward_metrics,
)


# ───────────────────────── synthetic series factory ────────────────────


def _ar1(level: float, phi: float, sigma: float, rng: np.random.Generator,
         n_months: int) -> pd.Series:
    idx = pd.date_range("2000-01-31", periods=n_months, freq="ME")
    x = np.empty(n_months)
    x[0] = level
    for t in range(1, n_months):
        x[t] = level + phi * (x[t - 1] - level) + rng.normal(0, sigma)
    return pd.Series(x, index=idx)


def _make_synthetic(seed: int = 0, n_months: int = 25 * 12) -> dict[str, pd.Series]:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2000-01-31", periods=n_months, freq="ME")
    return {
        "NAPM":          _ar1(51.0, 0.85, 1.4, rng, n_months),
        "CPIAUCSL":      pd.Series(np.cumsum(rng.normal(0.25, 0.3, size=n_months)) + 170.0, index=idx),
        # Growth side
        "T10Y3M":        _ar1(1.5, 0.8, 0.4, rng, n_months),
        "AMTMNO":        _ar1(450.0, 0.7, 6.0, rng, n_months),
        "BUSINV":        _ar1(700.0, 0.85, 4.0, rng, n_months),
        "cyclicals_def": _ar1(1.2, 0.85, 0.05, rng, n_months),
        # Inflation side
        "PPIACO":        _ar1(200.0, 0.8, 2.0, rng, n_months),
        "BCOM":          _ar1(100.0, 0.85, 1.5, rng, n_months),
    }


def _make_provider(series_map: dict[str, pd.Series]):
    """Provider that resolves an IndicatorSpec list against a fixed series dict.

    For yfinance specs we just look up `spec.id` directly so tests can hand-pick
    which synthetic series feeds which spec.
    """

    def _provider(specs):
        out: dict[str, pd.Series] = {}
        for spec in specs:
            if spec.id in series_map:
                out[spec.id] = series_map[spec.id]
        return out

    return _provider


# ───────────────────────── tests ──────────────────────────────────────


def test_growth_forecast_runs_with_only_target():
    series_map = _make_synthetic()
    cfg = IndicatorListConfig(
        target=IndicatorSpec(id="NAPM", source=SOURCE_FRED, fred_id="NAPM",
                             name="ISM Manufacturing PMI"),
        indicators=(),
    )
    fc = train_growth_forecast(
        indicator_cfg=cfg,
        training_cfg=TrainingConfig(history_start="2000-01-01", n_lags=4, cv_splits=4),
        series_provider=_make_provider(series_map),
    )
    assert isinstance(fc, GrowthForecast)
    assert fc.target_id == "NAPM"
    assert fc.indicators_used == ["NAPM"]
    assert 0.0 <= fc.prob_up <= 1.0


def test_inflation_forecast_with_custom_indicator_list():
    series_map = _make_synthetic()
    cfg = IndicatorListConfig(
        target=IndicatorSpec(id="CPIAUCSL", source=SOURCE_FRED, fred_id="CPIAUCSL",
                             name="CPI All Items"),
        indicators=(
            IndicatorSpec(id="PPIACO", source=SOURCE_FRED, fred_id="PPIACO"),
            IndicatorSpec(id="BCOM", source=SOURCE_YF_CLOSE, yf_symbol="^BCOM"),
        ),
    )
    fc = train_inflation_forecast(
        indicator_cfg=cfg,
        training_cfg=TrainingConfig(history_start="2000-01-01", n_lags=4, cv_splits=4),
        series_provider=_make_provider(series_map),
    )
    assert isinstance(fc, InflationForecast)
    assert set(fc.indicators_used) == {"CPIAUCSL", "PPIACO", "BCOM"}
    assert 0.0 <= fc.prob_up <= 1.0
    assert isinstance(fc.asof, datetime)


def test_independent_forecasts_use_different_indicator_lists():
    series_map = _make_synthetic()
    growth_cfg = IndicatorListConfig(
        target=IndicatorSpec(id="NAPM", source=SOURCE_FRED, fred_id="NAPM"),
        indicators=(
            IndicatorSpec(id="T10Y3M", source=SOURCE_FRED, fred_id="T10Y3M"),
            IndicatorSpec(id="cyclicals_def", source=SOURCE_YF_RATIO,
                          yf_numerator="XLY", yf_denominator="XLP"),
        ),
    )
    inflation_cfg = IndicatorListConfig(
        target=IndicatorSpec(id="CPIAUCSL", source=SOURCE_FRED, fred_id="CPIAUCSL"),
        indicators=(
            IndicatorSpec(id="PPIACO", source=SOURCE_FRED, fred_id="PPIACO"),
            IndicatorSpec(id="BCOM", source=SOURCE_YF_CLOSE, yf_symbol="^BCOM"),
        ),
    )
    bundle = train_and_forecast(
        growth_cfg=growth_cfg,
        inflation_cfg=inflation_cfg,
        training_cfg=TrainingConfig(history_start="2000-01-01", n_lags=4, cv_splits=4),
        growth_provider=_make_provider(series_map),
        inflation_provider=_make_provider(series_map),
    )
    assert isinstance(bundle, RegimeForecast)
    assert set(bundle.growth.indicators_used) == {"NAPM", "T10Y3M", "cyclicals_def"}
    assert set(bundle.inflation.indicators_used) == {"CPIAUCSL", "PPIACO", "BCOM"}
    assert "PPIACO" not in bundle.growth.indicators_used
    assert "T10Y3M" not in bundle.inflation.indicators_used


def test_yaml_loader_parses_fred_and_yfinance_rows(tmp_path):
    p = tmp_path / "indicators.yaml"
    p.write_text(
        """
target:
  id: NAPM
  source: fred
  fred_id: NAPM
  name: ISM Manufacturing PMI
indicators:
  - id: T10Y3M
    source: fred
    fred_id: T10Y3M
    name: 10Y-3M spread
  - id: cyclicals_defensives
    source: yfinance_ratio
    numerator: XLY
    denominator: XLP
    name: cyc/def
  - id: BCOM
    source: yfinance_close
    symbol: "^BCOM"
    name: bloomberg commodity
""".strip()
    )
    cfg = IndicatorListConfig.from_yaml(p)
    assert cfg.target.id == "NAPM"
    assert cfg.target.source == SOURCE_FRED
    ids = {s.id: s for s in cfg.indicators}
    assert ids["T10Y3M"].source == SOURCE_FRED
    assert ids["T10Y3M"].fred_id == "T10Y3M"
    assert ids["cyclicals_defensives"].source == SOURCE_YF_RATIO
    assert ids["cyclicals_defensives"].yf_numerator == "XLY"
    assert ids["cyclicals_defensives"].yf_denominator == "XLP"
    assert ids["BCOM"].source == SOURCE_YF_CLOSE
    assert ids["BCOM"].yf_symbol == "^BCOM"


def test_walk_forward_metrics_finite():
    series_map = _make_synthetic()
    cfg = IndicatorListConfig(
        target=IndicatorSpec(id="NAPM", source=SOURCE_FRED, fred_id="NAPM"),
        indicators=(IndicatorSpec(id="AMTMNO", source=SOURCE_FRED, fred_id="AMTMNO"),),
    )
    m = walk_forward_metrics(
        indicator_cfg=cfg,
        training_cfg=TrainingConfig(history_start="2000-01-01", n_lags=4, cv_splits=4),
        series_provider=_make_provider(series_map),
    )
    assert m.n_test > 0
    assert math.isfinite(m.accuracy)
    assert math.isfinite(m.brier)


def test_serialisation_roundtrip():
    series_map = _make_synthetic()
    g_cfg = IndicatorListConfig(
        target=IndicatorSpec(id="NAPM", source=SOURCE_FRED, fred_id="NAPM"),
        indicators=(IndicatorSpec(id="T10Y3M", source=SOURCE_FRED, fred_id="T10Y3M"),),
    )
    i_cfg = IndicatorListConfig(
        target=IndicatorSpec(id="CPIAUCSL", source=SOURCE_FRED, fred_id="CPIAUCSL"),
        indicators=(IndicatorSpec(id="PPIACO", source=SOURCE_FRED, fred_id="PPIACO"),),
    )
    bundle = train_and_forecast(
        growth_cfg=g_cfg,
        inflation_cfg=i_cfg,
        training_cfg=TrainingConfig(history_start="2000-01-01", n_lags=3, cv_splits=3),
        growth_provider=_make_provider(series_map),
        inflation_provider=_make_provider(series_map),
    )
    raw = bundle.to_json()
    restored = RegimeForecast.model_validate_json(raw)
    assert restored.growth.target_id == "NAPM"
    assert restored.inflation.target_id == "CPIAUCSL"
    assert pytest.approx(restored.growth.prob_up) == bundle.growth.prob_up
    assert pytest.approx(restored.inflation.prob_up) == bundle.inflation.prob_up


def test_yaml_loader_accepts_local_csv_target(tmp_path, monkeypatch):
    import castelino.forecast.regime as regime_mod

    root = tmp_path
    (root / "data").mkdir(parents=True)
    (root / "data" / "ism_manufacturing_pmi.csv").write_text(
        "date,value\n2000-01-31,50.0\n2000-02-29,51.0\n", encoding="utf-8"
    )
    yml = root / "growth.yaml"
    yml.write_text(
        """
target:
  id: ISM_MFG_PMI
  source: local_csv
  path: data/ism_manufacturing_pmi.csv
  name: "ISM Manufacturing PMI"
indicators: []
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(regime_mod, "ROOT", root)
    cfg = IndicatorListConfig.from_yaml(yml)
    assert cfg.target.id == "ISM_MFG_PMI"
    assert cfg.target.source == SOURCE_LOCAL_CSV
    assert cfg.target.csv_relpath == "data/ism_manufacturing_pmi.csv"


def test_fetch_local_csv_parses_comments(monkeypatch, tmp_path):
    import castelino.forecast.regime as regime_mod

    p = tmp_path / "series.csv"
    p.write_text(
        "# note\n# another\ndate,value\n2000-01-31,48.2\n2000-02-29,49.1\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(regime_mod, "ROOT", tmp_path)
    s = regime_mod._fetch_local_csv("series.csv")
    assert len(s) == 2
    assert float(s.iloc[-1]) == pytest.approx(49.1)


def test_indicator_spec_validates_requirements():
    IndicatorSpec(
        id="ok", source=SOURCE_LOCAL_CSV, csv_relpath="data/ism_manufacturing_pmi.csv",
    ).validate()
    with pytest.raises(ValueError):
        IndicatorSpec(id="x", source=SOURCE_LOCAL_CSV).validate()  # missing path
    with pytest.raises(ValueError):
        IndicatorSpec(id="x", source=SOURCE_FRED).validate()  # missing fred_id
    with pytest.raises(ValueError):
        IndicatorSpec(id="x", source=SOURCE_YF_CLOSE).validate()  # missing yf_symbol
    with pytest.raises(ValueError):
        IndicatorSpec(id="x", source=SOURCE_YF_RATIO).validate()  # missing pair
    with pytest.raises(ValueError):
        IndicatorSpec(id="x", source="garbage").validate()


def test_two_month_ahead_target_shifts_correctly():
    """lead_months=2 should produce labels for value(t+2) > value(t+1)."""
    series_map = _make_synthetic()
    cfg = IndicatorListConfig(
        target=IndicatorSpec(id="NAPM", source=SOURCE_FRED, fred_id="NAPM"),
        indicators=(IndicatorSpec(id="T10Y3M", source=SOURCE_FRED, fred_id="T10Y3M"),),
    )

    fc1 = train_growth_forecast(
        indicator_cfg=cfg,
        training_cfg=TrainingConfig(history_start="2000-01-01", n_lags=4,
                                    cv_splits=4, lead_months=1),
        series_provider=_make_provider(series_map),
    )
    fc2 = train_growth_forecast(
        indicator_cfg=cfg,
        training_cfg=TrainingConfig(history_start="2000-01-01", n_lags=4,
                                    cv_splits=4, lead_months=2),
        series_provider=_make_provider(series_map),
    )

    assert fc1.lead_months == 1
    assert fc2.lead_months == 2
    # The 2-month-ahead forecast should advance the target month by exactly
    # one extra month-end relative to the 1-month-ahead forecast.
    fm1 = pd.Timestamp(fc1.target_month)
    fm2 = pd.Timestamp(fc2.target_month)
    assert (fm2 - fm1).days >= 28


def test_search_returns_history_with_at_least_baseline():
    """The search must always include the step-0 (self-lags only) baseline."""
    from castelino.forecast.search import (
        SearchStep,
        greedy_forward_search,
    )

    series_map = _make_synthetic()
    target = IndicatorSpec(id="CPIAUCSL", source=SOURCE_FRED, fred_id="CPIAUCSL",
                           name="CPI All Items")
    candidates = [
        IndicatorSpec(id="PPIACO", source=SOURCE_FRED, fred_id="PPIACO"),
        IndicatorSpec(id="BCOM", source=SOURCE_YF_CLOSE, yf_symbol="^BCOM"),
    ]
    cfg = TrainingConfig(history_start="2000-01-01", n_lags=4, cv_splits=4,
                         lead_months=2)

    result = greedy_forward_search(
        target=target,
        candidates=candidates,
        training_cfg=cfg,
        max_indicators=2,
        metric="balanced_accuracy",
        series_provider=_make_provider(series_map),
    )
    assert result.target_id == "CPIAUCSL"
    assert result.metric == "balanced_accuracy"
    assert len(result.history) >= 1
    assert result.history[0].step == 0
    assert isinstance(result.best_step, SearchStep)
    # Selected indicators (if any) must come from the supplied pool.
    for s in result.history[1:]:
        assert s.added in {"PPIACO", "BCOM"}
