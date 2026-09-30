from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

import castelino.dashboard.endpoints.models as ep
from castelino.dashboard.main import app
from castelino.forecast.regime import GrowthForecast, InflationForecast, RegimeForecast
from castelino.forecast.risk_off import RiskOffForecast


def _dir(cls, asof, **kw):
    return cls(
        asof=asof,
        target_id="X",
        target_name="ISM Manufacturing PMI (composite)",
        feature_month="2026-03-01",
        target_month="2026-04-01",
        up=True,
        prob_up=0.76,
        indicators_used=["DGS10", "ICSA"],
        train_metrics={"accuracy": 0.515, "brier": 0.32, "n_test": 260},
        history_start="2000-01-01",
        n_obs=314,
        **kw,
    )


def test_models_reports_fresh_stale_and_missing(monkeypatch):
    now = datetime.now(UTC)
    rf = RegimeForecast(
        asof=now,
        growth=_dir(GrowthForecast, now),
        inflation=_dir(InflationForecast, now - timedelta(days=2)),
    )
    monkeypatch.setattr(ep, "_registry_forecast", lambda: None)
    monkeypatch.setattr(ep.regime, "read_forecast", lambda: rf)
    monkeypatch.setattr(ep.risk_off, "read_forecast", lambda: None)

    cards = {c["id"]: c for c in TestClient(app).get("/models").json()}

    assert cards["growth"]["status"] == "fresh"
    assert cards["growth"]["accuracy"] == 0.515
    assert cards["growth"]["feature_month"] == "2026-03"
    assert cards["growth"]["kind"] == "XGBoost · ISM Manufacturing PMI, 1-month lead"
    assert cards["inflation"]["status"] == "stale"
    assert cards["risk_off"]["status"] == "missing"


def test_models_risk_off_card(monkeypatch):
    monkeypatch.setattr(ep, "_registry_forecast", lambda: None)
    monkeypatch.setattr(ep.regime, "read_forecast", lambda: None)
    monkeypatch.setattr(
        ep.risk_off,
        "read_forecast",
        lambda: RiskOffForecast(
            prob_risk_off=0.18,
            as_of=datetime.now(UTC),
            feature_month="2026-09",
            target_month="2026-10",
        ),
    )

    cards = {c["id"]: c for c in TestClient(app).get("/models").json()}

    assert cards["growth"]["status"] == "missing"
    assert cards["risk_off"]["status"] == "fresh"
    assert cards["risk_off"]["up"] is False
    assert cards["risk_off"]["features"] == ["hy_oas", "ig_oas", "vix", "dxy"]


def test_registry_forecast_wins_over_legacy_file(monkeypatch):
    now = datetime.now(UTC)
    served = RegimeForecast(
        asof=now, growth=_dir(GrowthForecast, now), inflation=_dir(InflationForecast, now)
    )
    served.growth.prob_up = 0.83
    monkeypatch.setattr(ep, "_registry_forecast", lambda: served)
    monkeypatch.setattr(ep.regime, "read_forecast", lambda: None)
    cards = {c["id"]: c for c in TestClient(app).get("/models").json()}
    assert cards["growth"]["prob"] == 0.83


def test_cards_carry_prediction_parameters_and_sources(monkeypatch):
    now = datetime.now(UTC)
    rf = RegimeForecast(
        asof=now, growth=_dir(GrowthForecast, now), inflation=_dir(InflationForecast, now)
    )
    monkeypatch.setattr(ep, "_registry_forecast", lambda: rf)
    monkeypatch.setattr(ep.risk_off, "read_forecast", lambda: None)
    cards = {c["id"]: c for c in TestClient(app).get("/models").json()}

    g = cards["growth"]
    assert (
        "ISM Manufacturing PMI" in g["predicts"]["question"]
        and "2026-04" in g["predicts"]["question"]
    )
    params = {p["name"]: p["value"] for p in g["parameters"]}
    assert params["n_estimators"] == 400 and params["max_depth"] == 3 and params["lead_months"] == 1
    roles = {s["role"] for s in g["sources"]}
    assert roles == {"target", "indicator"}
    assert all(s["provider"] and s["ref"] for s in g["sources"])
    assert {s["id"] for s in g["sources"] if s["used"]} <= {"DGS10", "ICSA", "X"}

    ro = cards["risk_off"]  # missing model still documents what it would predict and read
    assert "30 days" in ro["predicts"]["question"]
    assert {s["ref"] for s in ro["sources"]} >= {"BAMLH0A0HYM2", "VIXCLS", "^MOVE", "SPY"}
    assert {p["name"] for p in ro["parameters"]} >= {"n_estimators", "drawdown_threshold"}
