"""Phase-5: backtest execution + portfolio bookkeeping.

Three responsibilities:

1. **Daily snapshot persistence** — append (date, nav, cash, gross, net,
   realized_pnl, n_positions) to a parquet under
   `data/backtest_runs/<run_id>/portfolio_history.parquet` after every
   business-day close.

2. **Mark loop driver** — wraps `execution.mark_loop.run_mark_loop` so the
   backtest can re-price open positions and journal stop-loss closes
   (which use `WriterIdentity.MARK_LOOP` per the R/W matrix).

3. **Pipeline-fire callable** — builds a `FundState` from a trigger and the
   live `Portfolio`, invokes the LangGraph DAG, and returns whether the
   pipeline ran end-to-end. The real LLM calls happen here (Phase 7).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Callable

import pandas as pd

from castelino.backtest.runner import HeadlineScore, TriggerCandidate
from castelino.config import get_settings
from castelino.execution.mark_loop import run_mark_loop
from castelino.execution.portfolio import Portfolio
from castelino.memory.schemas import TriggerRecord, TriggerSource
from castelino.orchestrator.state import FundState

log = logging.getLogger(__name__)


PORTFOLIO_HISTORY_FILENAME = "portfolio_history.parquet"


# ───────────────────────── snapshot persistence ──────────────────────────


@dataclass(frozen=True)
class DailyNavRow:
    date: date
    nav: float
    cash: float
    gross_exposure: float
    net_exposure: float
    realized_pnl: float
    n_positions: int


def portfolio_history_path(run_id: str) -> Path:
    cfg = get_settings()
    p = Path(cfg.root) / cfg.backtest.runs_dir / run_id
    p.mkdir(parents=True, exist_ok=True)
    return p / PORTFOLIO_HISTORY_FILENAME


def snapshot_row(d: date, portfolio: Portfolio) -> DailyNavRow:
    return DailyNavRow(
        date=d,
        nav=portfolio.nav,
        cash=portfolio.cash,
        gross_exposure=portfolio.gross_exposure,
        net_exposure=portfolio.net_exposure,
        realized_pnl=portfolio.realized_pnl,
        n_positions=len(portfolio.positions),
    )


def append_daily_snapshot(run_id: str, row: DailyNavRow) -> Path:
    """Append a single row to the parquet history. Idempotent on (date) —
    re-running the same date overwrites that row, never duplicates."""
    path = portfolio_history_path(run_id)
    new = pd.DataFrame([{
        "date": pd.Timestamp(row.date),
        "nav": row.nav,
        "cash": row.cash,
        "gross_exposure": row.gross_exposure,
        "net_exposure": row.net_exposure,
        "realized_pnl": row.realized_pnl,
        "n_positions": row.n_positions,
    }])
    if path.exists():
        existing = pd.read_parquet(path)
        # Drop any prior row for this date so we get clean upsert semantics
        existing = existing[existing["date"] != pd.Timestamp(row.date)]
        merged = pd.concat([existing, new], ignore_index=True)
    else:
        merged = new
    merged = merged.sort_values("date").reset_index(drop=True)
    merged.to_parquet(path)
    return path


def load_history(run_id: str) -> pd.DataFrame:
    p = portfolio_history_path(run_id)
    if not p.exists():
        return pd.DataFrame(columns=[
            "date", "nav", "cash", "gross_exposure", "net_exposure",
            "realized_pnl", "n_positions",
        ])
    return pd.read_parquet(p).sort_values("date").reset_index(drop=True)


# ───────────────────────── mark loop driver ──────────────────────────────


def run_daily_mark(portfolio: Portfolio) -> Portfolio:
    """Run the production mark loop. `latest()` already respects
    `BACKTEST_AS_OF`, so prices are historical. Stop-loss closes are
    journalled with `WriterIdentity.MARK_LOOP`.
    """
    pf, fills, warnings = run_mark_loop(portfolio)
    if fills:
        log.info("[backtest mark] %d stop-loss fill(s)", len(fills))
    if warnings:
        log.debug("[backtest mark] warnings: %s", warnings[:3])
    return pf


# ───────────────────────── pipeline-fire callable ────────────────────────


def make_fire_fn(
    portfolio_holder: "PortfolioHolder",
    *,
    graph_builder: Callable | None = None,
):
    """Return a `fire_fn` for `BacktestRunner` that wires the LangGraph DAG.

    `portfolio_holder` is a mutable wrapper so the runner can thread the
    same `Portfolio` instance across days. `graph_builder` defaults to
    `castelino.orchestrator.graph.build_graph` (deferred import keeps the
    test path light).
    """
    def _fire(d: date, trigger: TriggerCandidate, scores: list[HeadlineScore]) -> bool:
        if graph_builder is None:
            from castelino.orchestrator.graph import build_graph as _gb
            graph = _gb()
        else:
            graph = graph_builder()

        # Build a TriggerRecord that the graph's CurrentEvent agent expects
        bt_to_prod = {
            "black_swan": TriggerSource.NEWS,
            "news": TriggerSource.NEWS,
            "calendar": TriggerSource.CALENDAR,
            "regime": TriggerSource.REGIME_SHIFT,
            "conviction": TriggerSource.CONVICTION,
            "cron": TriggerSource.CRON_FALLBACK,
        }
        record = TriggerRecord(
            source=bt_to_prod.get(trigger.path, TriggerSource.NEWS),
            headline=trigger.headline,
            significance=trigger.materiality,
            asset_classes_affected=[],
            raw_event_data={
                "trigger_path": trigger.path,
                "backtest_as_of": d.isoformat(),
            },
            one_sentence_reason=f"backtest fire: {trigger.path}",
        )

        recent = [s.headline for s in scores][:30]
        state = FundState(
            trigger=record,
            recent_headlines=recent,
            source_summaries=[],
            portfolio=portfolio_holder.get(),
        )

        try:
            final = graph.invoke(state)
        except Exception as e:
            log.warning("[backtest fire] graph failed for %s: %s", d, e)
            return False

        # The graph returns a dict-like state; pull the final portfolio out
        if isinstance(final, dict):
            new_pf = final.get("portfolio", None)
        else:
            new_pf = getattr(final, "portfolio", None)
        if isinstance(new_pf, Portfolio):
            portfolio_holder.set(new_pf)
        return True

    return _fire


# ───────────────────────── helpers ───────────────────────────────────────


class PortfolioHolder:
    """Mutable wrapper so the runner threads the same Portfolio across days
    without exposing module-level state. Tests construct one explicitly;
    production paths build one from `Portfolio.load()`."""

    def __init__(self, portfolio: Portfolio) -> None:
        self._pf = portfolio

    def get(self) -> Portfolio:
        return self._pf

    def set(self, pf: Portfolio) -> None:
        self._pf = pf


def initial_portfolio() -> Portfolio:
    """Fresh portfolio sized at `cfg.backtest.initial_nav`."""
    cfg = get_settings()
    initial = cfg.backtest.initial_nav
    return Portfolio(cash=initial, initial_nav=initial)


def assert_nav_invariant(
    before: Portfolio, after: Portfolio, *,
    slippage_total: float, commission_total: float,
    tolerance: float = 1e-6,
) -> None:
    """Assert NAV_after == NAV_before − slippage − commission (modulo unrealized
    P&L from the mark step, which is captured separately).

    This is a direct check — used in tests; the production mark loop has its
    own invariant tests in `tests/test_accounting_invariant.py`.
    """
    expected = before.nav - slippage_total - commission_total
    drift = abs(after.nav - expected)
    if drift > tolerance:
        raise AssertionError(
            f"NAV invariant violated: "
            f"before={before.nav:.4f} after={after.nav:.4f} "
            f"slippage={slippage_total:.4f} commission={commission_total:.4f} "
            f"expected={expected:.4f} drift={drift:.6f}"
        )
