"""Phase-4: rolling classifier retrain — no-lookahead invariant.

The regime nowcasters (growth, inflation) and the risk-off classifier are
all trained on macro time-series. To avoid information leakage during the
historical backtest, each must be retrained at simulated time `as_of`
using ONLY data with `index < as_of`.

This module wraps the production training functions with an as-of-cutoff
series provider so neither the core training code nor the agents need to
know about the backtest. Trained artifacts are persisted as pickles per
simulated Sunday under:

    data/backtest_runs/<run_id>/models/<YYYY-MM-DD>/{growth,inflation,risk_off}.pkl

`load_nearest()` finds the most-recent retrain on or before a given date,
which is what the live regime forecaster will read during a backtest run.
"""

from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from castelino.config import get_settings
from castelino.forecast.regime import (
    GROWTH_INDICATORS_YAML,
    INFLATION_INDICATORS_YAML,
    IndicatorListConfig,
    SeriesProvider,
    TrainingConfig,
    _default_series_provider,
    train_growth_forecast,
    train_inflation_forecast,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetrainArtifact:
    as_of: date
    growth_path: Path
    inflation_path: Path


def make_as_of_provider(
    as_of: date, base: SeriesProvider | None = None,
) -> SeriesProvider:
    """Wrap a series provider so every returned series is truncated to
    `index < as_of`. The strict `<` cutoff prevents leakage of the
    `as_of` day's data into training.
    """
    base = base or _default_series_provider

    def _wrapped(specs):
        raw = base(specs)
        cutoff = pd.Timestamp(as_of)
        out: dict[str, pd.Series] = {}
        for k, s in raw.items():
            if s is None or len(s) == 0:
                out[k] = s
                continue
            idx = pd.to_datetime(s.index)
            if idx.tz is not None:
                idx = idx.tz_localize(None)
            mask = idx < cutoff
            out[k] = s.iloc[mask]
        return out
    return _wrapped


def models_dir(run_id: str, as_of: date) -> Path:
    cfg = get_settings()
    p = (
        Path(cfg.root) / cfg.backtest.runs_dir / run_id
        / "models" / as_of.isoformat()
    )
    p.mkdir(parents=True, exist_ok=True)
    return p


def retrain_classifiers(
    *, as_of: date, run_id: str,
    base_provider: SeriesProvider | None = None,
    training_cfg: TrainingConfig | None = None,
) -> RetrainArtifact:
    """Retrain growth + inflation classifiers using only data < as_of.

    Pickled forecast artifacts are written so a downstream `load_nearest()`
    call returns the same object the live forecaster would see.
    """
    provider = make_as_of_provider(as_of, base_provider)

    growth = train_growth_forecast(
        indicator_cfg=IndicatorListConfig.from_yaml(GROWTH_INDICATORS_YAML),
        training_cfg=training_cfg,
        series_provider=provider,
    )
    inflation = train_inflation_forecast(
        indicator_cfg=IndicatorListConfig.from_yaml(INFLATION_INDICATORS_YAML),
        training_cfg=training_cfg,
        series_provider=provider,
    )

    out = models_dir(run_id, as_of)
    g_path = out / "growth.pkl"
    i_path = out / "inflation.pkl"
    g_path.write_bytes(pickle.dumps(growth))
    i_path.write_bytes(pickle.dumps(inflation))
    log.info("retrained classifiers as_of=%s → %s", as_of, out)

    return RetrainArtifact(as_of=as_of, growth_path=g_path, inflation_path=i_path)


def load_nearest(run_id: str, on_or_before: date) -> RetrainArtifact | None:
    """Return the most-recent retrain artifact on or before `on_or_before`.

    None when no retrain has been written yet (e.g. day-1 of the run).
    """
    cfg = get_settings()
    base = Path(cfg.root) / cfg.backtest.runs_dir / run_id / "models"
    if not base.exists():
        return None
    candidates: list[date] = []
    for child in base.iterdir():
        if not child.is_dir():
            continue
        try:
            candidates.append(date.fromisoformat(child.name))
        except ValueError:
            continue
    eligible = [d for d in candidates if d <= on_or_before]
    if not eligible:
        return None
    nearest = max(eligible)
    out = base / nearest.isoformat()
    return RetrainArtifact(
        as_of=nearest,
        growth_path=out / "growth.pkl",
        inflation_path=out / "inflation.pkl",
    )
