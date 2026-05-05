"""Broker behavior — fills, slippage direction, position math."""

from __future__ import annotations

import math

import pytest

from castelino.config import get_settings
from castelino.execution.broker import OrderType, Side, TradeOrder, execute
from castelino.execution.portfolio import Portfolio


def _pf() -> Portfolio:
    cfg = get_settings()
    return Portfolio(cash=cfg.fund.initial_nav, initial_nav=cfg.fund.initial_nav)


def test_buy_slippage_lifts_fill_price():
    pf = _pf()
    _, fill = execute(
        TradeOrder(
            order_id="b1", instrument_id="TLT", order_type=OrderType.MARKET_OPEN,
            side=Side.BUY, quantity=10, reference_price=100.0,
        ),
        pf,
    )
    assert fill.fill_price > 100.0
    # 5 bps for bond ETF → 100 * 1.0005 = 100.05
    assert math.isclose(fill.fill_price, 100.05, abs_tol=1e-9)


def test_sell_slippage_drops_fill_price():
    pf = _pf()
    _, fill = execute(
        TradeOrder(
            order_id="s1", instrument_id="TLT", order_type=OrderType.MARKET_OPEN,
            side=Side.SELL, quantity=10, reference_price=100.0,
        ),
        pf,
    )
    assert fill.fill_price < 100.0
    assert math.isclose(fill.fill_price, 99.95, abs_tol=1e-9)


def test_average_entry_price_on_extending_long():
    pf = _pf()
    pf, _ = execute(
        TradeOrder(
            order_id="o1", instrument_id="SPY", order_type=OrderType.MARKET_OPEN,
            side=Side.BUY, quantity=100, reference_price=500.0,
        ),
        pf,
    )
    pf, _ = execute(
        TradeOrder(
            order_id="o2", instrument_id="SPY", order_type=OrderType.MARKET_OPEN,
            side=Side.BUY, quantity=100, reference_price=520.0,
        ),
        pf,
    )
    pos = pf.position("SPY")
    assert pos is not None
    assert pos.quantity == 200
    # Slipped fills: 500.25 and 520.26; vol-weighted avg
    expected = (500.25 * 100 + 520.26 * 100) / 200
    assert math.isclose(pos.avg_entry_price, expected, abs_tol=1e-3)


def test_close_more_than_held_caps_to_position_size():
    """Over-close caps to held quantity AND drives slippage/commission/cash off
    the actual closed quantity — not the requested quantity. The latter would
    credit phantom cash and silently break the accounting invariant."""
    pf = _pf()
    pf, _ = execute(
        TradeOrder(
            order_id="o1", instrument_id="SPY", order_type=OrderType.MARKET_OPEN,
            side=Side.BUY, quantity=100, reference_price=500.0,
        ),
        pf,
    )
    pre_close_nav = pf.nav
    pf, fill = execute(
        TradeOrder(
            order_id="o2", instrument_id="SPY", order_type=OrderType.MARKET_CLOSE,
            side=Side.SELL, quantity=500, reference_price=500.0,
        ),
        pf,
    )
    assert pf.position("SPY") is None
    # `fill.quantity` is now the actual closed quantity, not the request.
    assert fill.quantity == 100
    # And — crucially — the sacred invariant still holds at the over-close.
    expected = pre_close_nav - fill.slippage_cost - fill.commission_cost
    assert math.isclose(pf.nav, expected, abs_tol=1e-6), (
        f"over-close violated invariant: pre={pre_close_nav} post={pf.nav} "
        f"slip={fill.slippage_cost} comm={fill.commission_cost}"
    )


def test_opposite_direction_market_open_rejected():
    """Reverse-via-MARKET_OPEN was a quiet bug surface; now it must raise."""
    pf = _pf()
    pf, _ = execute(
        TradeOrder(
            order_id="o1", instrument_id="SPY", order_type=OrderType.MARKET_OPEN,
            side=Side.BUY, quantity=100, reference_price=500.0,
        ),
        pf,
    )
    with pytest.raises(ValueError, match="would reverse"):
        execute(
            TradeOrder(
                order_id="o2", instrument_id="SPY", order_type=OrderType.MARKET_OPEN,
                side=Side.SELL, quantity=50, reference_price=500.0,
            ),
            pf,
        )


def test_close_with_no_position_raises():
    pf = _pf()
    with pytest.raises(ValueError, match="no open position"):
        execute(
            TradeOrder(
                order_id="x1", instrument_id="SPY", order_type=OrderType.MARKET_CLOSE,
                side=Side.SELL, quantity=10, reference_price=500.0,
            ),
            pf,
        )


def test_close_with_wrong_side_raises():
    pf = _pf()
    pf, _ = execute(
        TradeOrder(
            order_id="o1", instrument_id="SPY", order_type=OrderType.MARKET_OPEN,
            side=Side.BUY, quantity=100, reference_price=500.0,
        ),
        pf,
    )
    with pytest.raises(ValueError, match="Close-side mismatch"):
        execute(
            TradeOrder(
                order_id="bad", instrument_id="SPY", order_type=OrderType.MARKET_CLOSE,
                # Wrong side: holding long, but trying to BUY to close
                side=Side.BUY, quantity=50, reference_price=500.0,
            ),
            pf,
        )


def test_pure_function_does_not_mutate_input():
    pf_before = _pf()
    nav_before = pf_before.nav
    cash_before = pf_before.cash

    new_pf, _ = execute(
        TradeOrder(
            order_id="p1", instrument_id="SPY", order_type=OrderType.MARKET_OPEN,
            side=Side.BUY, quantity=10, reference_price=500.0,
        ),
        pf_before,
    )
    # Input portfolio unchanged
    assert pf_before.nav == nav_before
    assert pf_before.cash == cash_before
    assert pf_before.position("SPY") is None
    # Output is fresh
    assert new_pf.position("SPY") is not None


def test_trim_realizes_pnl():
    pf = _pf()
    pf, _ = execute(
        TradeOrder(
            order_id="o1", instrument_id="GLD", order_type=OrderType.MARKET_OPEN,
            side=Side.BUY, quantity=100, reference_price=200.0,
        ),
        pf,
    )
    # Mark up before trimming
    pos = pf.position("GLD")
    pos.current_price = 220.0

    initial_realized = pf.realized_pnl
    pf, _ = execute(
        TradeOrder(
            order_id="o2", instrument_id="GLD", order_type=OrderType.TRIM,
            side=Side.SELL, quantity=50, reference_price=220.0,
        ),
        pf,
    )
    # Half closed; remaining qty = 50
    assert pf.position("GLD").quantity == 50
    # Realized should be > 0 (price went up; commodities at 10bps slippage)
    assert pf.realized_pnl - initial_realized > 0
