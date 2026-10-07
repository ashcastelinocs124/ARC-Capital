"""Refit Pulse/Pressure when a newer month of target data exists; promote behind the gate.

Run by the `model_refit` Refresh job. Moved out of the Update Agent on 2026-10-07.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import pandas as pd

from castelino.agents.update.gate import run_gate
from castelino.agents.update.models import Decision
from castelino.agents.update.registry import MODELS, ModelRegistry
from castelino.forecast.regime import RegimeForecast

log = logging.getLogger(__name__)


def latest_months() -> dict[str, str]:
    from castelino.forecast import regime as r

    out: dict[str, str] = {}
    for name, yaml in (
        ("growth", r.GROWTH_INDICATORS_YAML),
        ("inflation", r.INFLATION_INDICATORS_YAML),
    ):
        target = r.IndicatorListConfig.from_yaml(yaml).target
        s = r._to_month_end(r._resolve_spec(target)).dropna()
        out[name] = pd.Timestamp(s.index.max()).strftime("%Y-%m")
    return out


def _new_data(
    champion: RegimeForecast | None, latest_month_fn: Callable[[], dict[str, str]]
) -> bool:
    if champion is None:
        return True
    try:
        latest = latest_month_fn()
    except Exception:  # noqa: BLE001 — if we cannot tell, attempt the refit
        log.warning("new-data check failed; attempting refit", exc_info=True)
        return True
    return any(latest[m] > getattr(champion, m).feature_month[:7] for m in MODELS)


def run_refit(
    *,
    registry: ModelRegistry,
    tolerance: float,
    refit_fn: Callable[[], RegimeForecast],
    latest_month_fn: Callable[[], dict[str, str]],
) -> str | None:
    """None when there is no new data; otherwise what happened."""
    champion = registry.current()
    if not _new_data(champion, latest_month_fn):
        return None
    challenger = refit_fn()
    registry.save_history(challenger)  # chart data, saved whether or not anything is promoted
    gate = run_gate(challenger, champion, tolerance)
    promoted = [m for m in MODELS if getattr(gate, m).decision == Decision.PROMOTED]
    if promoted:
        version = registry.save_version(challenger)
        for m in promoted:
            registry.set_pointer(m, version)
        return "promoted: " + ", ".join(promoted)
    return "refit kept the champions"
