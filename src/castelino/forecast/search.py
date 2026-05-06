"""Hit-and-trial indicator search for the regime nowcaster.

Given a target (`CPIAUCSL` for inflation, `ISM_MFG_PMI` / local ISM CSV for growth)
pool of `IndicatorSpec`s, runs **greedy forward selection**:

1. Start with target self-lags only.
2. For each candidate not yet selected, train an XGBoost classifier with
   walk-forward CV (`TimeSeriesSplit`).
3. Add the candidate that improves the chosen metric the most. Repeat until
   no candidate adds value, or `max_indicators` is reached.

Class-aware metrics
-------------------
For the user's "predict rises" framing, the search reports — and can be
optimized against — class-specific metrics on the **up** label as well as the
balanced accuracy (mean of recall on each class). This avoids the common
failure mode of always-predict-up.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd
from pydantic import BaseModel
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import TimeSeriesSplit

from castelino.forecast.regime import (
    SOURCE_FRED,
    SOURCE_YF_CLOSE,
    SOURCE_YF_RATIO,
    IndicatorListConfig,
    IndicatorSpec,
    SeriesProvider,
    TrainingConfig,
    _align,
    _build_feature_table,
    _build_targets,
    _default_series_provider,
    _make_model,
)

log = logging.getLogger(__name__)


# ───────────────────────── default candidate pools ───────────────────────


def growth_candidate_pool() -> list[IndicatorSpec]:
    """Candidate pool for the Growth (Industrial Production) forecaster.

    Kept fully **independent** from the inflation pool. Items are real-economy,
    cyclical, labor-market, housing, business-investment, and forward-looking
    market indicators.
    """
    return [
        # ── Already in YAML ──
        IndicatorSpec(id="T10Y3M", source=SOURCE_FRED, fred_id="T10Y3M",
                      name="10Y–3M Treasury spread"),
        IndicatorSpec(id="BAMLH0A0HYM2", source=SOURCE_FRED,
                      fred_id="BAMLH0A0HYM2", name="US High Yield OAS"),
        IndicatorSpec(id="PERMIT", source=SOURCE_FRED, fred_id="PERMIT",
                      name="Building permits"),
        IndicatorSpec(id="ICSA", source=SOURCE_FRED, fred_id="ICSA",
                      name="Initial jobless claims"),
        IndicatorSpec(id="CCSA", source=SOURCE_FRED, fred_id="CCSA",
                      name="Continuing jobless claims"),
        IndicatorSpec(id="AMTMNO", source=SOURCE_FRED, fred_id="AMTMNO",
                      name="Mfrs' new orders, total mfg"),
        IndicatorSpec(id="BUSINV", source=SOURCE_FRED, fred_id="BUSINV",
                      name="Total business inventories"),
        IndicatorSpec(id="NEWORDER", source=SOURCE_FRED, fred_id="NEWORDER",
                      name="New orders: nondefense capital goods ex-aircraft"),
        IndicatorSpec(id="UMCSENT", source=SOURCE_FRED, fred_id="UMCSENT",
                      name="UMich consumer sentiment"),
        IndicatorSpec(id="USSLIND", source=SOURCE_FRED, fred_id="USSLIND",
                      name="Leading Index (Phila Fed)"),
        IndicatorSpec(id="cyclicals_defensives", source=SOURCE_YF_RATIO,
                      yf_numerator="XLY", yf_denominator="XLP",
                      name="Cyclicals (XLY) / defensives (XLP)"),
        IndicatorSpec(id="copper_gold", source=SOURCE_YF_RATIO,
                      yf_numerator="HG=F", yf_denominator="GC=F",
                      name="Copper / gold ratio"),
        # ── Extras to test (drop if they don't help) ──
        IndicatorSpec(id="PAYEMS", source=SOURCE_FRED, fred_id="PAYEMS",
                      name="Total nonfarm payrolls"),
        IndicatorSpec(id="HOUST", source=SOURCE_FRED, fred_id="HOUST",
                      name="Housing starts"),
        IndicatorSpec(id="DGORDER", source=SOURCE_FRED, fred_id="DGORDER",
                      name="Durable goods orders"),
        IndicatorSpec(id="RSAFS", source=SOURCE_FRED, fred_id="RSAFS",
                      name="Retail sales (advance)"),
        IndicatorSpec(id="W875RX1", source=SOURCE_FRED, fred_id="W875RX1",
                      name="Real personal income ex transfers (NBER)"),
        IndicatorSpec(id="DSPIC96", source=SOURCE_FRED, fred_id="DSPIC96",
                      name="Real disposable personal income"),
        IndicatorSpec(id="PCEC96", source=SOURCE_FRED, fred_id="PCEC96",
                      name="Real personal consumption expenditures"),
        IndicatorSpec(id="DGS10", source=SOURCE_FRED, fred_id="DGS10",
                      name="10Y nominal Treasury yield"),
        IndicatorSpec(id="SP500", source=SOURCE_YF_CLOSE, yf_symbol="^GSPC",
                      name="S&P 500 (forward-looking on growth)"),
    ]


def inflation_candidate_pool() -> list[IndicatorSpec]:
    """Wider pool than the YAML — many of these are dropped by the search."""
    return [
        # ── Already in YAML ──
        IndicatorSpec(id="PPIACO", source=SOURCE_FRED, fred_id="PPIACO",
                      name="PPI All Commodities"),
        IndicatorSpec(id="DCOILWTICO", source=SOURCE_FRED, fred_id="DCOILWTICO",
                      name="WTI crude"),
        IndicatorSpec(id="BCOM", source=SOURCE_YF_CLOSE, yf_symbol="^BCOM",
                      name="Bloomberg Commodity Index"),
        IndicatorSpec(id="T5YIE", source=SOURCE_FRED, fred_id="T5YIE",
                      name="5Y breakeven"),
        IndicatorSpec(id="DTWEXBGS", source=SOURCE_FRED, fred_id="DTWEXBGS",
                      name="Trade-weighted USD (broad)"),
        IndicatorSpec(id="MICH", source=SOURCE_FRED, fred_id="MICH",
                      name="UMich 1Y inflation expectations"),
        IndicatorSpec(id="CUSR0000SEHA", source=SOURCE_FRED, fred_id="CUSR0000SEHA",
                      name="CPI rent of primary residence"),
        IndicatorSpec(id="AHETPI", source=SOURCE_FRED, fred_id="AHETPI",
                      name="Avg hourly earnings (prod & nonsupervisory)"),
        IndicatorSpec(id="T10YIE", source=SOURCE_FRED, fred_id="T10YIE",
                      name="10Y breakeven"),
        IndicatorSpec(id="DCOILBRENTEU", source=SOURCE_FRED, fred_id="DCOILBRENTEU",
                      name="Brent crude"),
        IndicatorSpec(id="CSUSHPISA", source=SOURCE_FRED, fred_id="CSUSHPISA",
                      name="Case-Shiller 20-city home prices"),
        # ── Extras to test (drop if they don't help) ──
        IndicatorSpec(id="PPIFIS", source=SOURCE_FRED, fred_id="PPIFIS",
                      name="PPI Final Demand: Services"),
        IndicatorSpec(id="UNRATE", source=SOURCE_FRED, fred_id="UNRATE",
                      name="Unemployment rate (Phillips curve)"),
        IndicatorSpec(id="ISRATIO", source=SOURCE_FRED, fred_id="ISRATIO",
                      name="Total Business Inventories/Sales Ratio"),
        IndicatorSpec(id="GASREGW", source=SOURCE_FRED, fred_id="GASREGW",
                      name="US Regular gasoline retail"),
        IndicatorSpec(id="DGS10", source=SOURCE_FRED, fred_id="DGS10",
                      name="10Y nominal yield"),
        IndicatorSpec(id="FEDFUNDS", source=SOURCE_FRED, fred_id="FEDFUNDS",
                      name="Federal funds rate"),
        IndicatorSpec(id="VIXCLS", source=SOURCE_FRED, fred_id="VIXCLS",
                      name="VIX (CBOE)"),
        IndicatorSpec(id="M2SL", source=SOURCE_FRED, fred_id="M2SL",
                      name="M2 money stock"),
        IndicatorSpec(id="PCEPI", source=SOURCE_FRED, fred_id="PCEPI",
                      name="PCE Price Index (alt to CPI)"),
        IndicatorSpec(id="HG_F", source=SOURCE_YF_CLOSE, yf_symbol="HG=F",
                      name="Copper futures"),
    ]


# ───────────────────────── richer evaluation ─────────────────────────────


@dataclass(frozen=True)
class ClassMetrics:
    accuracy: float
    balanced_accuracy: float
    brier: float
    precision_up: float
    recall_up: float       # MoM rise label
    f1_up: float
    precision_down: float
    recall_down: float     # MoM fall — tune for "inflation down" calls
    f1_down: float
    n_test: int

    def by_name(self, name: str) -> float:
        try:
            return float(getattr(self, name))
        except AttributeError as e:
            raise ValueError(
                f"Unknown metric {name!r}. Pick one of: accuracy, "
                "balanced_accuracy, brier, precision_up, recall_up, f1_up, "
                "precision_down, recall_down, f1_down."
            ) from e


def _walk_forward_class_eval(
    X: pd.DataFrame, y: pd.Series, training_cfg: TrainingConfig
) -> ClassMetrics:
    """Walk-forward CV that aggregates per-class metrics across folds."""
    if len(X) < training_cfg.cv_splits + 5:
        return ClassMetrics(
            accuracy=float("nan"), balanced_accuracy=float("nan"),
            brier=float("nan"), precision_up=float("nan"),
            recall_up=float("nan"), f1_up=float("nan"),
            precision_down=float("nan"), recall_down=float("nan"),
            f1_down=float("nan"), n_test=0,
        )

    tscv = TimeSeriesSplit(n_splits=training_cfg.cv_splits)
    accs, baccs, briers = [], [], []
    precs_up, recs_up, f1s_up = [], [], []
    precs_dn, recs_dn, f1s_dn = [], [], []
    n_test_total = 0
    for tr, te in tscv.split(X):
        Xtr, Xte = X.iloc[tr], X.iloc[te]
        ytr, yte = y.iloc[tr], y.iloc[te]
        if ytr.nunique() < 2 or yte.nunique() < 1:
            continue
        m = _make_model(training_cfg)
        m.fit(Xtr, ytr, verbose=False)
        proba = m.predict_proba(Xte)[:, 1]
        pred = (proba >= 0.5).astype(int)

        accs.append(float(accuracy_score(yte, pred)))
        baccs.append(float(balanced_accuracy_score(yte, pred)))
        briers.append(float(brier_score_loss(yte, proba)))
        precs_up.append(float(precision_score(yte, pred, zero_division=0.0, pos_label=1)))
        recs_up.append(float(recall_score(yte, pred, zero_division=0.0, pos_label=1)))
        f1s_up.append(float(f1_score(yte, pred, zero_division=0.0, pos_label=1)))
        precs_dn.append(float(precision_score(yte, pred, zero_division=0.0, pos_label=0)))
        recs_dn.append(float(recall_score(yte, pred, zero_division=0.0, pos_label=0)))
        f1s_dn.append(float(f1_score(yte, pred, zero_division=0.0, pos_label=0)))
        n_test_total += len(yte)

    if not accs:
        return ClassMetrics(
            accuracy=float("nan"), balanced_accuracy=float("nan"),
            brier=float("nan"), precision_up=float("nan"),
            recall_up=float("nan"), f1_up=float("nan"),
            precision_down=float("nan"), recall_down=float("nan"),
            f1_down=float("nan"), n_test=0,
        )
    return ClassMetrics(
        accuracy=float(np.mean(accs)),
        balanced_accuracy=float(np.mean(baccs)),
        brier=float(np.mean(briers)),
        precision_up=float(np.mean(precs_up)),
        recall_up=float(np.mean(recs_up)),
        f1_up=float(np.mean(f1s_up)),
        precision_down=float(np.mean(precs_dn)),
        recall_down=float(np.mean(recs_dn)),
        f1_down=float(np.mean(f1s_dn)),
        n_test=n_test_total,
    )


def _evaluate_indicator_set(
    *,
    target: IndicatorSpec,
    indicators: tuple[IndicatorSpec, ...],
    training_cfg: TrainingConfig,
    series_provider: SeriesProvider,
) -> ClassMetrics:
    cfg = IndicatorListConfig(target=target, indicators=indicators)
    specs = [cfg.target, *cfg.indicators]
    series_map = series_provider(specs)
    if cfg.target.id not in series_map:
        raise KeyError(f"Target {cfg.target.id} missing from provider output.")
    feats = _build_feature_table(series_map, training_cfg.n_lags, training_cfg.history_start)
    y = _build_targets(
        series_map[cfg.target.id],
        training_cfg.history_start,
        lead_months=training_cfg.lead_months,
    )
    X, y_aligned = _align(feats, y)
    return _walk_forward_class_eval(X, y_aligned, training_cfg)


# ───────────────────────── public search API ─────────────────────────────


class SearchStep(BaseModel):
    step: int
    added: str | None
    selected: list[str]
    accuracy: float
    balanced_accuracy: float
    brier: float
    precision_up: float
    recall_up: float
    f1_up: float
    precision_down: float
    recall_down: float
    f1_down: float
    n_test: int


class IndicatorSearchResult(BaseModel):
    target_id: str
    target_name: str
    metric: str
    history: list[SearchStep]

    @property
    def best_step(self) -> SearchStep:
        # Best by the chosen metric (higher is better, except brier).
        if self.metric == "brier":
            return min(self.history, key=lambda s: getattr(s, self.metric))
        return max(self.history, key=lambda s: getattr(s, self.metric))


def greedy_forward_search(
    *,
    target: IndicatorSpec,
    candidates: list[IndicatorSpec] | None = None,
    training_cfg: TrainingConfig | None = None,
    max_indicators: int = 6,
    metric: str = "balanced_accuracy",
    series_provider: SeriesProvider | None = None,
    on_step: Callable[[SearchStep], None] | None = None,
) -> IndicatorSearchResult:
    """Greedy forward selection of indicators that maximize `metric`.

    Walks through candidates and at each iteration adds the single indicator
    that yields the largest improvement on the OOS metric. Stops when no
    candidate strictly improves the score, or when `max_indicators` is hit.
    """
    cands = candidates if candidates is not None else inflation_candidate_pool()
    cands = [c for c in cands if c.id != target.id]
    training = training_cfg or TrainingConfig(lead_months=2)
    provider = series_provider or _default_series_provider

    higher_is_better = metric != "brier"

    selected: list[IndicatorSpec] = []
    history: list[SearchStep] = []

    base = _evaluate_indicator_set(
        target=target, indicators=(), training_cfg=training, series_provider=provider,
    )
    step0 = SearchStep(
        step=0, added=None, selected=[],
        accuracy=base.accuracy, balanced_accuracy=base.balanced_accuracy,
        brier=base.brier, precision_up=base.precision_up,
        recall_up=base.recall_up, f1_up=base.f1_up,
        precision_down=base.precision_down, recall_down=base.recall_down,
        f1_down=base.f1_down, n_test=base.n_test,
    )
    history.append(step0)
    if on_step:
        on_step(step0)

    def score_of(step: SearchStep) -> float:
        return float(getattr(step, metric))

    for step_n in range(1, max_indicators + 1):
        remaining = [c for c in cands if c not in selected]
        if not remaining:
            break

        best_choice: IndicatorSpec | None = None
        best_metrics: ClassMetrics | None = None
        for cand in remaining:
            try:
                m = _evaluate_indicator_set(
                    target=target,
                    indicators=tuple([*selected, cand]),
                    training_cfg=training,
                    series_provider=provider,
                )
            except Exception as e:
                log.warning("Eval failed for %s: %s", cand.id, e)
                continue
            score = float(getattr(m, metric))
            if best_metrics is None:
                best_choice, best_metrics = cand, m
                continue
            best_score = float(getattr(best_metrics, metric))
            if (higher_is_better and score > best_score) or (
                (not higher_is_better) and score < best_score
            ):
                best_choice, best_metrics = cand, m

        if best_choice is None or best_metrics is None:
            break

        prev = history[-1]
        improved = (
            (higher_is_better and float(getattr(best_metrics, metric)) > score_of(prev))
            or ((not higher_is_better) and float(getattr(best_metrics, metric)) < score_of(prev))
        )
        if not improved:
            log.info("No candidate improved %s past step %d; stopping.", metric, step_n - 1)
            break

        selected.append(best_choice)
        step = SearchStep(
            step=step_n,
            added=best_choice.id,
            selected=[s.id for s in selected],
            accuracy=best_metrics.accuracy,
            balanced_accuracy=best_metrics.balanced_accuracy,
            brier=best_metrics.brier,
            precision_up=best_metrics.precision_up,
            recall_up=best_metrics.recall_up,
            f1_up=best_metrics.f1_up,
            precision_down=best_metrics.precision_down,
            recall_down=best_metrics.recall_down,
            f1_down=best_metrics.f1_down,
            n_test=best_metrics.n_test,
        )
        history.append(step)
        if on_step:
            on_step(step)

    return IndicatorSearchResult(
        target_id=target.id,
        target_name=target.name or target.id,
        metric=metric,
        history=history,
    )
