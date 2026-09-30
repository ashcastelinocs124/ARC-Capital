"""Models page: current state of the ML forecasters, read from their saved JSON."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter

from castelino.forecast import regime, risk_off

router = APIRouter()

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
    }


@router.get("/models")
def models():
    """One card per model. Read-only: never triggers a retrain."""
    cards: list[dict] = []

    rf = regime.read_forecast()
    if rf:
        cards.append(_direction_card("growth", "Growth nowcaster", "P(growth up)", rf.growth))
        cards.append(_direction_card("inflation", "Inflation nowcaster", "P(inflation up)", rf.inflation))
    else:
        cards += [
            {"id": "growth", "name": "Growth nowcaster", "kind": "XGBoost · growth direction", "status": "missing"},
            {"id": "inflation", "name": "Inflation nowcaster", "kind": "XGBoost · inflation direction", "status": "missing"},
        ]

    ro = risk_off.read_forecast()
    base = {"id": "risk_off", "name": "Risk-off classifier", "kind": "XGBoost · next-month risk-off regime"}
    if ro:
        cards.append({
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
        })
    else:
        cards.append({**base, "status": "missing"})

    return cards
