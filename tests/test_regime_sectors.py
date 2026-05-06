"""Tests for growth×inflation quadrant → sector / ETF mapping."""

from __future__ import annotations

from types import SimpleNamespace

from castelino.forecast.regime import GrowthForecast, InflationForecast, RegimeForecast
from castelino.forecast.regime_sectors import (
    format_macro_block_for_prompt,
    macro_fields_from_forecast,
    merge_forecast_into_state_kwargs,
    quadrant_key,
    resolve_regime_sector_bundle,
)


def test_quadrant_key():
    assert quadrant_key(growth_up=True, inflation_up=True) == "growth_up_inflation_up"
    assert quadrant_key(growth_up=False, inflation_up=True) == "growth_down_inflation_up"


def test_resolve_filters_nontradable_hints():
    cheat = {
        "quadrants": {
            "growth_up_inflation_up": {
                "label": "Test",
                "sectors": ["Energy"],
                "preferred_instrument_ids": ["VIX", "SPY"],
            },
        },
    }
    b = resolve_regime_sector_bundle(
        growth_up=True, inflation_up=True, cheat=cheat,
    )
    assert b["macro_regime_label"] == "Test"
    assert b["preferred_instrument_ids"] == ["SPY"]


def test_merge_when_no_saved_forecast(monkeypatch):
    monkeypatch.setattr(
        "castelino.forecast.regime_sectors.read_forecast",
        lambda path=None: None,
    )
    k = merge_forecast_into_state_kwargs()
    assert k["macro_regime_key"] == ""
    assert k["preferred_sectors"] == []
    assert k["growth_forecast_up"] is None


def test_macro_fields_from_forecast():
    g = GrowthForecast(
        target_id="INDPRO",
        target_name="Industrial Production",
        feature_month="2026-03-01",
        target_month="2026-05-01",
        lead_months=2,
        up=False,
        prob_up=0.31,
        indicators_used=[],
        train_metrics=None,
        history_start="2000-01-01",
        n_obs=100,
    )
    inf = InflationForecast(
        target_id="CPI",
        target_name="CPI",
        feature_month="2026-03-01",
        target_month="2026-05-01",
        lead_months=2,
        up=False,
        prob_up=0.43,
        indicators_used=[],
        train_metrics=None,
        history_start="2000-01-01",
        n_obs=100,
    )
    fc = RegimeForecast(growth=g, inflation=inf)
    fields = macro_fields_from_forecast(fc)
    assert fields["macro_regime_key"] == "growth_down_inflation_down"
    assert fields["growth_prob_up"] == 0.31
    assert "TLT" in fields["preferred_instrument_ids"]


def test_format_macro_block():
    empty = SimpleNamespace(macro_regime_key="")
    assert "not loaded" in format_macro_block_for_prompt(empty)

    s = SimpleNamespace(
        macro_regime_key="growth_down_inflation_down",
        macro_regime_label="Disinflation / slowdown",
        macro_regime_blurb="Duration can work.",
        preferred_sectors=["Health care"],
        preferred_instrument_ids=["TLT", "XLV"],
        growth_forecast_up=False,
        inflation_forecast_up=False,
        growth_prob_up=0.2,
        inflation_prob_up=0.3,
        regime_target_month="2026-05-01",
    )
    text = format_macro_block_for_prompt(s)
    assert "Disinflation" in text
    assert "TLT" in text
    assert "P(up)=0.200" in text or "0.2" in text
