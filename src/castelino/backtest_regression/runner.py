"""Per-component runners for the backtest regression suite."""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch as _patch

from castelino.backtest_regression.models import CaseResult
from castelino.forecast.risk_off import RiskOffForecast, read_forecast  # patched in tests
from castelino.triggers.figure_deviation.scorer import Scorer
from castelino.triggers.risk_gate import evaluate as evaluate_risk_gate

_FIXTURE_ROOT = Path(__file__).parent.parent.parent.parent / "tests" / "backtest" / "fixtures"


def _load_fixture_dir(subdir: str) -> list[dict]:
    path = _FIXTURE_ROOT / subdir
    if not path.is_dir():
        return []
    return [json.loads(f.read_text()) for f in sorted(path.glob("*.json"))]


@contextmanager
def with_stubbed_forecast(prob: float):
    """Stub `read_forecast` inside the runner module to return a
    fixture-driven prob. Used by the CLI; tests prefer `unittest.mock.patch`
    directly.

    Patches all three call sites (source module, runner, gate) so any caller —
    including `risk_gate.evaluate()` — sees the fixture's probability.
    """
    fake = RiskOffForecast(
        prob_risk_off=prob,
        as_of=datetime.now(UTC),
        feature_month="",
        target_month="",
    )
    with _patch(
        "castelino.forecast.risk_off.read_forecast",
        return_value=fake,
    ), _patch(
        "castelino.backtest_regression.runner.read_forecast",
        return_value=fake,
    ), _patch(
        "castelino.triggers.risk_gate.read_forecast",
        return_value=fake,
    ):
        yield


def run_risk_off_case(fixture: dict) -> CaseResult:
    """Run one risk-off gate case. Caller must stub `read_forecast` upstream
    (typically via `with_stubbed_forecast`) so the gate sees the fixture's
    `prob_risk_off` instead of whatever is on disk.
    """
    case_id = fixture["case_id"]
    inputs = fixture["inputs"]
    expected = fixture["expected"]

    # Fail fast if caller forgot to stub the forecast.
    forecast = read_forecast()
    if forecast is None or abs(forecast.prob_risk_off - inputs["prob_risk_off"]) > 1e-6:
        return CaseResult(
            case_id=case_id,
            component="risk_off",
            passed=False,
            actual={"error": "forecast not stubbed to fixture prob_risk_off"},
            expected=expected,
            notes="caller must patch read_forecast before invoking",
        )

    # The gate has its own bound import of read_forecast; mirror the
    # stub there so it sees the fixture's prob_risk_off rather than disk.
    with _patch(
        "castelino.triggers.risk_gate.read_forecast",
        return_value=forecast,
    ):
        decision = evaluate_risk_gate(inputs["instrument_id"])
    actual = {
        "action": decision.action,
        "size_multiplier": decision.size_multiplier,
    }
    passed = (
        actual["action"] == expected["action"]
        and abs(actual["size_multiplier"] - expected["size_multiplier"]) < 1e-6
    )
    return CaseResult(
        case_id=case_id,
        component="risk_off",
        passed=passed,
        actual=actual,
        expected=expected,
    )


def run_all_risk_off() -> list[CaseResult]:
    out: list[CaseResult] = []
    for fixture in _load_fixture_dir("risk_off"):
        with with_stubbed_forecast(fixture["inputs"]["prob_risk_off"]):
            out.append(run_risk_off_case(fixture))
    return out


# ────────────────────────── figure-deviation runner ──────────────────────────

_scorer = Scorer()


def run_figure_deviation_case(fixture: dict) -> CaseResult:
    """Score the transcript on the named lexicon and assert on the raw
    `LexiconScore.value` plus required term hits.

    Assertions supported in `expected`:
    - `value_sign`: "positive" | "negative" | "any"
    - `abs_value_min`: float — |value| must be ≥ this
    - `abs_value_max`: float — |value| must be ≤ this (negative-case test)
    - `must_hit_terms_any`: list[str] — at least one term must appear in `hits`
    """
    case_id = fixture["case_id"]
    expected = fixture["expected"]

    score = _scorer.score_post(
        text=fixture["transcript_excerpt"],
        lexicon_name=fixture["lexicon"],
    )
    actual = {
        "value": score.value,
        "hits": dict(score.hits),
        "lexicon_version": fixture["lexicon"],
    }

    failures: list[str] = []
    if "value_sign" in expected:
        sign = expected["value_sign"]
        if sign == "positive" and not (score.value > 0):
            failures.append(f"value {score.value:.3f} not positive")
        elif sign == "negative" and not (score.value < 0):
            failures.append(f"value {score.value:.3f} not negative")
    if "abs_value_min" in expected and abs(score.value) < expected["abs_value_min"]:
        failures.append(
            f"|value|={abs(score.value):.3f} < min {expected['abs_value_min']}"
        )
    if "abs_value_max" in expected and abs(score.value) > expected["abs_value_max"]:
        failures.append(
            f"|value|={abs(score.value):.3f} > max {expected['abs_value_max']}"
        )
    if "must_hit_terms_any" in expected:
        terms = expected["must_hit_terms_any"]
        if not any(t in score.hits for t in terms):
            failures.append(f"none of {terms} matched (hits={list(score.hits)})")

    return CaseResult(
        case_id=case_id,
        component="figure_deviation",
        passed=len(failures) == 0,
        actual=actual,
        expected=expected,
        notes="; ".join(failures) if failures else None,
    )


def run_all_figure_deviation() -> list[CaseResult]:
    return [
        run_figure_deviation_case(f) for f in _load_fixture_dir("figure_deviation")
    ]
