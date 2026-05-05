"""Daily mark loop — runs after US close.

1. Mark every open position to market.
2. Append a NAV snapshot.
3. Detect stop-loss hits and execute synthetic close orders.
4. Write `data/exposure_snapshot.json` (read by Principles Guard).

The mark loop is purely deterministic. Stop-loss closes are emitted as
`STOP_LOSS` orders so the broker journals them; downstream the Portfolio Agent
can annotate the close with the kill criterion that fired.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from castelino.config import get_settings
from castelino.data.instruments import AssetClass
from castelino.execution.broker import (
    Fill,
    OrderType,
    Side,
    TradeOrder,
    execute,
    trade_event_from_fill,
)
from castelino.execution.portfolio import Portfolio
from castelino.execution.pricing import PricingError, latest
from castelino.memory import io as memio
from castelino.memory.io import WriterIdentity

log = logging.getLogger(__name__)


def mark_to_market(portfolio: Portfolio) -> tuple[Portfolio, list[str]]:
    """Update `current_price` on every open position. Returns (new_pf, warnings)."""
    new_pf = portfolio.deep_copy()
    warnings: list[str] = []
    for pos in new_pf.positions:
        try:
            px = latest(pos.instrument_id).price
            pos.current_price = px
        except PricingError as e:
            warnings.append(f"{pos.instrument_id}: {e}")
            log.warning("mark failed for %s: %s", pos.instrument_id, e)
    return new_pf, warnings


def detect_stops(portfolio: Portfolio) -> list[TradeOrder]:
    """Identify positions whose stop-loss has been crossed; return synthetic orders."""
    orders: list[TradeOrder] = []
    for pos in portfolio.positions:
        if pos.stop_loss is None:
            continue
        # Long stops on a downside cross; short stops on an upside cross.
        hit = (
            (pos.quantity > 0 and pos.current_price <= pos.stop_loss)
            or (pos.quantity < 0 and pos.current_price >= pos.stop_loss)
        )
        if not hit:
            continue
        side = Side.SELL if pos.quantity > 0 else Side.BUY
        orders.append(
            TradeOrder(
                order_id=f"stop-{pos.instrument_id}-{int(datetime.now(UTC).timestamp())}",
                instrument_id=pos.instrument_id,
                order_type=OrderType.STOP_LOSS,
                side=side,
                quantity=abs(pos.quantity),
                reference_price=pos.current_price,
                parent_hypothesis_id=pos.parent_hypothesis_id,
                parent_expression_id=pos.parent_expression_id,
                notes=f"Stop-loss hit at {pos.current_price:.4f} (stop={pos.stop_loss:.4f})",
            )
        )
    return orders


def write_exposure_snapshot(portfolio: Portfolio, path: Path | None = None) -> None:
    """Persist the exposure breakdown read by the Principles Guard."""
    cfg = get_settings()
    p = path or (cfg.resolved_paths.data / "exposure_snapshot.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    by_class = {ac.value: portfolio.exposure_by_class().get(ac, 0.0) for ac in AssetClass}
    snap = {
        "timestamp": datetime.now(UTC).isoformat(),
        "nav": portfolio.nav,
        "cash": portfolio.cash,
        "gross_exposure": portfolio.gross_exposure,
        "net_exposure": portfolio.net_exposure,
        "exposure_by_class": by_class,
        "gross_pct_nav": portfolio.gross_exposure / portfolio.nav if portfolio.nav > 0 else 0.0,
        "net_pct_nav": portfolio.net_exposure / portfolio.nav if portfolio.nav > 0 else 0.0,
        "exposure_pct_nav_by_class": {
            ac.value: (by_class[ac.value] / portfolio.nav if portfolio.nav > 0 else 0.0)
            for ac in AssetClass
        },
        "n_open_positions": len(portfolio.positions),
    }
    with p.open("w") as f:
        json.dump(snap, f, indent=2)


def run_mark_loop(portfolio: Portfolio | None = None) -> tuple[Portfolio, list[Fill], list[str]]:
    """Full mark-loop pass. Returns (new_portfolio, fills_from_stops, warnings).

    Caller is responsible for persisting `new_portfolio` and journalling fills.
    """
    pf = portfolio or Portfolio.load()
    pf, warnings = mark_to_market(pf)
    pf.nav_history.append(pf.snapshot())

    stop_orders = detect_stops(pf)
    fills: list[Fill] = []
    for order in stop_orders:
        # Re-check that the position still exists — defensive against any
        # future change that lets stops cascade within a single mark pass.
        if pf.position(order.instrument_id) is None:
            continue
        pf, fill = execute(order, pf)
        fills.append(fill)
        # Journal coherence: stop-loss closes must show up in ST so the trade
        # card / curator / attribution all see the close. The orchestrator
        # path journals fills via WriterIdentity.EXECUTION; the out-of-band
        # mark loop uses MARK_LOOP per the R/W matrix.
        memio.journal_trade_event(
            trade_event_from_fill(order, fill),
            who=WriterIdentity.MARK_LOOP,
        )

    write_exposure_snapshot(pf)
    return pf, fills, warnings
