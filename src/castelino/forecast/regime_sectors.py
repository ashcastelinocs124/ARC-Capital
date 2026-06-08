"""Map growth × inflation forecasts to regime labels and sector / ETF hints.

Loads `data/regime_sector_cheat_sheet.yaml`. Used to populate `FundState` and
agent prompts without LLM inference.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from castelino.config import ROOT
from castelino.data.instruments import INSTRUMENTS
from castelino.forecast.regime import RegimeForecast, read_forecast

CHEAT_PATH = ROOT / "data" / "regime_sector_cheat_sheet.yaml"


@lru_cache(maxsize=1)
def _load_yaml(path: str) -> dict[str, Any]:
    p = Path(path)
    with p.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_cheat_sheet(*, path: Path | None = None) -> dict[str, Any]:
    """Return parsed cheat sheet (quadrants keyed by growth_X_inflation_Y)."""
    return dict(_load_yaml(str(path or CHEAT_PATH)))


def quadrant_key(*, growth_up: bool, inflation_up: bool) -> str:
    g = "up" if growth_up else "down"
    i = "up" if inflation_up else "down"
    return f"growth_{g}_inflation_{i}"


def _filter_tradable(ids: list[str]) -> list[str]:
    out: list[str] = []
    for iid in ids:
        inst = INSTRUMENTS.get(iid)
        if inst is not None and inst.tradable:
            out.append(iid)
    return out


def resolve_regime_sector_bundle(
    *,
    growth_up: bool,
    inflation_up: bool,
    cheat: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve quadrant to label, sectors, instruments, and narrative blurb."""
    doc = cheat if cheat is not None else load_cheat_sheet()
    quadrants = doc.get("quadrants") or {}
    key = quadrant_key(growth_up=growth_up, inflation_up=inflation_up)
    row = quadrants.get(key) or {}
    label = str(row.get("label") or key.replace("_", " "))
    blurb = str(row.get("blurb") or "").strip()
    sectors = [str(s) for s in (row.get("sectors") or [])]
    raw_ids = [str(x) for x in (row.get("preferred_instrument_ids") or [])]
    instrument_ids = _filter_tradable(raw_ids)
    return {
        "macro_regime_key": key,
        "macro_regime_label": label,
        "preferred_sectors": sectors,
        "preferred_instrument_ids": instrument_ids,
        "macro_regime_blurb": blurb,
    }


def macro_fields_from_forecast(forecast: RegimeForecast) -> dict[str, Any]:
    """Dict of FundState macro_* fields from a saved or live `RegimeForecast`."""
    bundle = resolve_regime_sector_bundle(
        growth_up=bool(forecast.growth.up),
        inflation_up=bool(forecast.inflation.up),
    )
    return {
        **bundle,
        "growth_forecast_up": forecast.growth.up,
        "inflation_forecast_up": forecast.inflation.up,
        "growth_prob_up": float(forecast.growth.prob_up),
        "inflation_prob_up": float(forecast.inflation.prob_up),
        "regime_feature_month": forecast.growth.feature_month,
        "regime_target_month": forecast.growth.target_month,
        "regime_lead_months": int(forecast.growth.lead_months),
    }


def merge_forecast_into_state_kwargs(
    forecast: RegimeForecast | None = None,
) -> dict[str, Any]:
    """Keyword args to spread into `FundState` when building pipeline state."""
    fc = forecast if forecast is not None else read_forecast()
    if fc is None:
        return {
            "macro_regime_key": "",
            "macro_regime_label": "",
            "preferred_sectors": [],
            "preferred_instrument_ids": [],
            "macro_regime_blurb": "",
            "growth_forecast_up": None,
            "inflation_forecast_up": None,
            "growth_prob_up": None,
            "inflation_prob_up": None,
            "regime_feature_month": "",
            "regime_target_month": "",
            "regime_lead_months": 0,
        }
    return macro_fields_from_forecast(fc)


def format_macro_block_for_prompt(state_like: Any) -> str:
    """Single user-message section for agents (reads attributes from FundState)."""
    if not getattr(state_like, "macro_regime_key", ""):
        return (
            "Macro regime context (model-based, month-ahead): not loaded — "
            "run `ckm forecast-regime` or ensure data/regime_forecast.json exists."
        )
    sectors = getattr(state_like, "preferred_sectors", []) or []
    hints = getattr(state_like, "preferred_instrument_ids", []) or []
    g_up = getattr(state_like, "growth_forecast_up", None)
    i_up = getattr(state_like, "inflation_forecast_up", None)
    gp = getattr(state_like, "growth_prob_up", None)
    ip = getattr(state_like, "inflation_prob_up", None)
    lines = [
        f"Quadrant: {state_like.macro_regime_label} (`{state_like.macro_regime_key}`).",
    ]
    if state_like.macro_regime_blurb:
        lines.append(f"Playbook: {state_like.macro_regime_blurb}")
    if g_up is not None and gp is not None:
        lines.append(f"Growth nowcast: up={g_up}, P(up)={gp:.3f}.")
    if i_up is not None and ip is not None:
        lines.append(f"Inflation nowcast: up={i_up}, P(up)={ip:.3f}.")
    tgt = getattr(state_like, "regime_target_month", "") or ""
    if tgt:
        lines.append(f"Forecast target month (feature-aligned): {tgt}.")
    if sectors:
        lines.append("Preferred sectors: " + "; ".join(sectors) + ".")
    if hints:
        lines.append(
            "Preferred ETF / instrument hints (from cheat sheet): "
            + ", ".join(hints)
            + "."
        )
    return "\n".join(lines)
