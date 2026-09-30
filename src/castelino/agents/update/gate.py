from __future__ import annotations

from castelino.agents.update.models import Decision, GateResult, ModelGate
from castelino.forecast.regime import RegimeForecast


def decide(champion_brier: float | None, challenger_brier: float | None,
           tolerance: float) -> ModelGate:
    if challenger_brier is None:
        return ModelGate(decision=Decision.KEPT, champion_brier=champion_brier,
                         reason="challenger has no metrics")
    if champion_brier is None:
        return ModelGate(decision=Decision.PROMOTED, challenger_brier=challenger_brier,
                         reason="no champion yet")
    worse = round(challenger_brier - champion_brier, 6)
    if worse > tolerance:
        return ModelGate(
            decision=Decision.KEPT, champion_brier=champion_brier,
            challenger_brier=challenger_brier,
            reason=f"worse by {worse:.3f}, over the {tolerance:.2f} tolerance")
    return ModelGate(
        decision=Decision.PROMOTED, champion_brier=champion_brier,
        challenger_brier=challenger_brier, reason="not worse than champion beyond tolerance")


def _brier(fc) -> float | None:
    return fc.train_metrics.brier if fc is not None and fc.train_metrics else None


def run_gate(challenger: RegimeForecast, champion: RegimeForecast | None,
             tolerance: float) -> GateResult:
    return GateResult(
        growth=decide(_brier(champion.growth) if champion else None,
                      _brier(challenger.growth), tolerance),
        inflation=decide(_brier(champion.inflation) if champion else None,
                         _brier(challenger.inflation), tolerance),
    )
