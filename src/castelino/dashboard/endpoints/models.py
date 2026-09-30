"""Models page: current state of the ML forecasters, read from their saved JSON."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter

from castelino.forecast import regime, risk_off

router = APIRouter()

_PROVIDER = {
    regime.SOURCE_FRED: "FRED",
    regime.SOURCE_YF_CLOSE: "Yahoo Finance",
    regime.SOURCE_YF_RATIO: "Yahoo Finance (ratio)",
    regime.SOURCE_LOCAL_CSV: "Local CSV",
}
_MODELS = {
    "growth": ("Growth nowcaster", "P(growth up)", regime.GROWTH_INDICATORS_YAML),
    "inflation": ("Inflation nowcaster", "P(inflation up)", regime.INFLATION_INDICATORS_YAML),
}


def _registry_forecast():
    """The forecast the Update Agent's registry serves (None until its first refit)."""
    from castelino.agents.update.registry import ModelRegistry
    from castelino.config import get_settings

    cfg = get_settings()
    return ModelRegistry(cfg.root / cfg.update_agent.data_dir / "models").current()


def _regime_parameters() -> list[dict]:
    t = regime.TrainingConfig()  # the refit always uses these defaults; nothing is tuned at runtime
    return [
        {"name": "n_estimators", "value": t.n_estimators, "note": "boosted trees"},
        {"name": "max_depth", "value": t.max_depth, "note": "tree depth"},
        {"name": "learning_rate", "value": t.learning_rate, "note": "shrinkage per tree"},
        {"name": "n_lags", "value": t.n_lags, "note": "monthly lags per indicator"},
        {"name": "lead_months", "value": t.lead_months, "note": "months ahead predicted"},
        {"name": "cv_splits", "value": t.cv_splits, "note": "walk-forward test folds"},
        {"name": "history_start", "value": t.history_start, "note": "training window start"},
        {
            "name": "random_state",
            "value": t.random_state,
            "note": "fixed seed (deterministic refit)",
        },
        {"name": "objective", "value": "binary:logistic", "note": "up vs not-up classifier"},
    ]


def _spec_ref(spec) -> str:
    return (
        spec.fred_id
        or spec.yf_symbol
        or spec.csv_relpath
        or (f"{spec.yf_numerator}/{spec.yf_denominator}" if spec.yf_numerator else spec.id)
    )


def _regime_sources(yaml_path, used: list[str] | None) -> list[dict]:
    cfg = regime.IndicatorListConfig.from_yaml(yaml_path)
    rows = [("target", cfg.target)] + [("indicator", s) for s in cfg.indicators]
    return [
        {
            "id": s.id,
            "name": s.name or s.id,
            "role": role,
            "provider": _PROVIDER.get(s.source, s.source),
            "ref": _spec_ref(s),
            "used": used is None or s.id in used,
        }
        for role, s in rows
    ]


def _regime_predicts(model_id: str, fc) -> dict:
    name = (
        fc.target_name
        if fc
        else regime.IndicatorListConfig.from_yaml(_MODELS[model_id][2]).target.name
    )
    month = fc.target_month[:7] if fc else "next month"
    name = name.split(" (")[0]  # drop source notes like "(composite index; see CSV header ...)"
    return {
        "question": f"Will {name} rise month-over-month in {month}?",
        "output": 'Probability of "up" (0–1); the call is up when it is 50% or higher',
    }


def _risk_off_extras() -> dict:
    return {
        "predicts": {
            "question": f"Will SPY fall more than {abs(risk_off.DRAWDOWN_THRESHOLD):.0%} peak-to-trough "
            f"in the {risk_off.WINDOW_DAYS} days after month-end?",
            "output": "Probability of a risk-off drawdown (0–1)",
        },
        "parameters": [
            {"name": "n_estimators", "value": 200, "note": "boosted trees"},
            {"name": "max_depth", "value": 4, "note": "tree depth"},
            {"name": "learning_rate", "value": 0.05, "note": "shrinkage per tree"},
            {"name": "subsample", "value": 0.8, "note": "row sampling"},
            {"name": "colsample_bytree", "value": 0.8, "note": "feature sampling"},
            {"name": "scale_pos_weight", "value": "neg/pos", "note": "rebalances rare drawdowns"},
            {
                "name": "drawdown_threshold",
                "value": risk_off.DRAWDOWN_THRESHOLD,
                "note": "label: SPY drop beyond this",
            },
            {"name": "window_days", "value": risk_off.WINDOW_DAYS, "note": "look-ahead window"},
            {"name": "lags", "value": "1, 2, 3", "note": "monthly lags per feature"},
            {
                "name": "history_start",
                "value": risk_off.HISTORY_START,
                "note": "training window start",
            },
        ],
        "sources": [
            {
                "id": alias,
                "name": alias,
                "role": "indicator",
                "provider": "FRED",
                "ref": fred_id,
                "used": True,
            }
            for fred_id, alias in risk_off.FRED_FEATURES
        ]
        + [
            {
                "id": "move",
                "name": "MOVE bond-vol index",
                "role": "indicator",
                "provider": "Yahoo Finance",
                "ref": "^MOVE",
                "used": True,
            },
            {
                "id": "hyg_ief_ratio",
                "name": "HYG / IEF credit ratio",
                "role": "indicator",
                "provider": "Yahoo Finance (ratio)",
                "ref": "HYG/IEF",
                "used": True,
            },
            {
                "id": "spy",
                "name": "S&P 500 ETF (label)",
                "role": "target",
                "provider": "Yahoo Finance",
                "ref": "SPY",
                "used": True,
            },
        ],
    }


STALE_AFTER = timedelta(hours=24)  # same freshness bar the Macro page uses for the regime nowcast


def _status(trained_at: datetime) -> str:
    return "stale" if datetime.now(UTC) - trained_at > STALE_AFTER else "fresh"


def _direction_card(model_id: str, name: str, label: str, fc) -> dict:
    m = fc.train_metrics
    return {
        "id": model_id,
        "name": name,
        "kind": f"XGBoost · {fc.target_name.split(' (')[0]}, {fc.lead_months}-month lead",
        "status": _status(fc.asof),
        "trained_at": fc.asof.isoformat(),
        "prob": fc.prob_up,
        "up": fc.up,
        "prob_label": label,
        "feature_month": fc.feature_month[:7],
        "target_month": fc.target_month[:7],
        "accuracy": m.accuracy if m else None,
        "brier": m.brier if m else None,
        "n_test": m.n_test if m else None,
        "features": fc.indicators_used,
        "model_version": None,
        "predicts": _regime_predicts(model_id, fc),
        "parameters": _regime_parameters(),
        "sources": _regime_sources(_MODELS[model_id][2], fc.indicators_used),
    }


@router.get("/models")
def models():
    """One card per model. Read-only: never triggers a retrain."""
    cards: list[dict] = []

    rf = _registry_forecast() or regime.read_forecast()  # legacy file until the first refit
    for mid, (name, label, yaml_path) in _MODELS.items():
        if rf:
            cards.append(_direction_card(mid, name, label, getattr(rf, mid)))
        else:
            cards.append(
                {
                    "id": mid,
                    "name": name,
                    "kind": f"XGBoost · {mid} direction",
                    "status": "missing",
                    "predicts": _regime_predicts(mid, None),
                    "parameters": _regime_parameters(),
                    "sources": _regime_sources(yaml_path, None),
                }
            )

    ro = risk_off.read_forecast()
    base = {
        "id": "risk_off",
        "name": "Risk-off classifier",
        "kind": "XGBoost · next-month risk-off regime",
        **_risk_off_extras(),
    }
    if ro:
        cards.append(
            {
                **base,
                "status": _status(ro.as_of),
                "trained_at": ro.as_of.isoformat(),
                "prob": ro.prob_risk_off,
                "up": ro.prob_risk_off >= 0.5,
                "prob_label": "P(risk-off)",
                "feature_month": ro.feature_month,
                "target_month": ro.target_month,
                "accuracy": None,  # risk_off.py doesn't persist eval metrics
                "brier": None,
                "n_test": None,
                "features": [name for _, name in risk_off.FRED_FEATURES],
                "model_version": ro.model_version,
            }
        )
    else:
        cards.append({**base, "status": "missing"})

    return cards
