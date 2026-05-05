"""Pure-function fill simulator.

`execute(order, portfolio) -> (Portfolio, Fill)` — no I/O, no globals, no LLMs.
Every monetary number that affects the book is computed here in deterministic
Python so it is provably right. The accounting invariant test pins this:

    NAV_after_trade == NAV_before_trade − slippage_cost − commission_cost

(Holds at the moment of the fill — current_price for the new position equals
the entry price, so the only delta is fees.)
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field

from castelino.config import get_settings
from castelino.data.instruments import AssetClass, get_instrument
from castelino.execution.portfolio import Portfolio, Position


class OrderType(str, Enum):
    MARKET_OPEN = "market_open"
    MARKET_CLOSE = "market_close"
    TRIM = "trim"
    STOP_LOSS = "stop_loss"


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class TradeOrder(BaseModel):
    """An execution-ready order. No options, no GTC, no OCO — by design."""

    order_id: str
    instrument_id: str
    order_type: OrderType
    side: Side
    quantity: float = Field(gt=0)            # always positive; side carries direction
    reference_price: float = Field(gt=0)     # the agent's expected fill (pre-slippage)
    parent_hypothesis_id: str | None = None
    parent_expression_id: str | None = None
    stop_loss: float | None = None
    notes: str = ""


class Fill(BaseModel):
    """Receipt of a single execution. Append to ST journal as a Trade event."""

    order_id: str
    instrument_id: str
    side: Side
    quantity: float
    fill_price: float            # post-slippage
    slippage_cost: float         # USD lost to slippage on this fill
    commission_cost: float       # USD commission
    asset_class: AssetClass
    timestamp: datetime
    pre_trade_nav: float
    post_trade_nav: float
    realized_pnl: float = 0.0    # only set on partial/full close
    notes: str = ""


# ─────────────────────────── public entry point ───────────────────────────


def execute(order: TradeOrder, portfolio: Portfolio) -> tuple[Portfolio, Fill]:
    """Apply an order to a portfolio. Returns (new_portfolio, fill).

    Pure function — does not mutate `portfolio`. Caller is responsible for
    persisting the new state and journalling the fill.
    """
    inst = get_instrument(order.instrument_id)
    cfg = get_settings().execution
    pre_nav = portfolio.nav

    # 1. Compute slippage-adjusted fill price.
    bps = _slippage_bps(inst.asset_class, cfg.slippage_bps)
    if order.side == Side.BUY:
        fill_price = order.reference_price * (1 + bps / 10_000)
    else:
        fill_price = order.reference_price * (1 - bps / 10_000)

    new_pf = portfolio.deep_copy()
    realized = 0.0

    # 2. Apply to book and learn the *actual* filled quantity. For OPEN we use
    #    the requested qty; for CLOSE/TRIM/STOP the broker caps at held size.
    #    Slippage, commission, and cash all key off `actual_qty` — using
    #    `order.quantity` instead would credit phantom cash on over-closes
    #    and silently violate the sacred accounting invariant.
    if order.order_type == OrderType.MARKET_OPEN:
        _apply_open(new_pf, order, inst, fill_price)
        actual_qty = order.quantity
    else:
        actual_qty, realized = _apply_close(new_pf, order, inst, fill_price)

    # 3. Friction costs computed on actual_qty.
    slippage_cost = abs(fill_price - order.reference_price) * actual_qty * inst.contract_multiplier
    commission_cost = _commission(inst.asset_class, actual_qty, cfg.commission)

    # 4. Cash side. Slippage is already baked into fill_price; commission is
    #    a separate debit.
    notional = fill_price * actual_qty * inst.contract_multiplier
    if order.side == Side.BUY:
        new_pf.cash -= notional
    else:
        new_pf.cash += notional
    new_pf.cash -= commission_cost
    new_pf.realized_pnl += realized

    # 5. Mark the position to the *mid* (reference_price), not the fill_price.
    #    This is what makes the accounting invariant hold:
    #        NAV_after = NAV_before − slippage_cost − commission_cost
    #    Cost basis is what you paid (fill_price), but the position's
    #    current_price is the mid — so unrealized P&L immediately equals
    #    -slippage, which is the real economic loss to the spread-taker.
    pos = new_pf.position(order.instrument_id)
    if pos is not None:
        pos.current_price = order.reference_price

    post_nav = new_pf.nav

    fill = Fill(
        order_id=order.order_id,
        instrument_id=order.instrument_id,
        side=order.side,
        quantity=actual_qty,
        fill_price=fill_price,
        slippage_cost=slippage_cost,
        commission_cost=commission_cost,
        asset_class=inst.asset_class,
        timestamp=datetime.now(UTC),
        pre_trade_nav=pre_nav,
        post_trade_nav=post_nav,
        realized_pnl=realized,
        notes=order.notes,
    )
    return new_pf, fill


# ─────────────────────────── helpers ──────────────────────────────────────


_ORDER_TYPE_TO_EVENT = {
    OrderType.MARKET_OPEN: "open",
    OrderType.MARKET_CLOSE: "close",
    OrderType.TRIM: "trim",
    OrderType.STOP_LOSS: "stop_loss",
}


def trade_event_from_fill(order: "TradeOrder", fill: "Fill"):
    """Build a journal-ready TradeEvent from a fill. Used by both the
    orchestrator path and the mark loop so journal coherence is identical
    regardless of who triggered the close.
    """
    from castelino.memory.schemas import TradeEvent

    return TradeEvent(
        event_type=_ORDER_TYPE_TO_EVENT[order.order_type],
        instrument_id=order.instrument_id,
        parent_hypothesis_id=order.parent_hypothesis_id,
        parent_expression_id=order.parent_expression_id,
        quantity=fill.quantity if order.side == Side.BUY else -fill.quantity,
        fill_price=fill.fill_price,
        slippage_cost=fill.slippage_cost,
        commission_cost=fill.commission_cost,
        realized_pnl=fill.realized_pnl,
        pre_trade_nav=fill.pre_trade_nav,
        post_trade_nav=fill.post_trade_nav,
        notes=fill.notes,
    )


def _slippage_bps(ac: AssetClass, table: dict[str, float]) -> float:
    return float(table[ac.value])


def _commission(ac: AssetClass, qty: float, table: dict[str, float]) -> float:
    """Per-contract for futures, flat-zero for everything else in v1."""
    rate = float(table[ac.value])
    if ac == AssetClass.FUTURES:
        return rate * qty
    return rate


def _apply_open(pf: Portfolio, order: TradeOrder, inst, fill_price: float) -> None:
    pos = pf.position(order.instrument_id)
    signed_qty = order.quantity if order.side == Side.BUY else -order.quantity
    if pos is None:
        pf.positions.append(
            Position(
                instrument_id=order.instrument_id,
                quantity=signed_qty,
                avg_entry_price=fill_price,
                current_price=fill_price,
                asset_class=inst.asset_class,
                opened_at=datetime.now(UTC),
                parent_hypothesis_id=order.parent_hypothesis_id,
                parent_expression_id=order.parent_expression_id,
                stop_loss=order.stop_loss,
                notes=order.notes,
            )
        )
        return

    # Extending existing position. Same direction → weighted-average the entry.
    # Opposite direction is rejected: agents must emit MARKET_CLOSE or TRIM
    # explicitly. Allowing implicit reversals here meant the cash leg was
    # computed against the full notional even though the position was reduced —
    # a quiet accounting bug. Fail loudly instead.
    if (pos.quantity > 0) != (signed_qty > 0):
        raise ValueError(
            f"MARKET_OPEN on {order.instrument_id} would reverse an existing "
            f"position (held qty={pos.quantity:+g}, requested signed_qty={signed_qty:+g}). "
            "Emit MARKET_CLOSE or TRIM first."
        )
    new_qty = pos.quantity + signed_qty
    if new_qty == 0:
        pos.quantity = 0.0
        pos.avg_entry_price = fill_price
    else:
        pos.avg_entry_price = (
            pos.avg_entry_price * pos.quantity + fill_price * signed_qty
        ) / new_qty
        pos.quantity = new_qty


def _apply_close(
    pf: Portfolio, order: TradeOrder, inst, fill_price: float
) -> tuple[float, float]:
    """Close / trim / stop-out. Returns (actual_qty_closed, realized_pnl).

    Caller MUST use `actual_qty_closed` for slippage/commission/cash legs;
    using `order.quantity` when it exceeds the held position credits phantom
    cash and breaks the accounting invariant.
    """
    pos = pf.position(order.instrument_id)
    if pos is None:
        raise ValueError(
            f"Cannot {order.order_type.value} {order.instrument_id}: no open position"
        )

    close_qty = min(order.quantity, abs(pos.quantity))
    sign = 1 if pos.quantity > 0 else -1  # long=+, short=-

    # Validate side aligns with the close direction.
    expected_side = Side.SELL if sign > 0 else Side.BUY
    if order.side != expected_side:
        raise ValueError(
            f"Close-side mismatch on {order.instrument_id}: "
            f"holding qty={pos.quantity}, order.side={order.side}"
        )

    realized = (fill_price - pos.avg_entry_price) * close_qty * sign * inst.contract_multiplier

    # Reduce or remove the position.
    pos.quantity -= sign * close_qty
    if abs(pos.quantity) < 1e-9:
        pf.positions = [p for p in pf.positions if p.instrument_id != pos.instrument_id]

    return close_qty, realized
