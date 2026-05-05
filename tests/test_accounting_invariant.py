"""The sacred test.

NAV_after_trade == NAV_before_trade − slippage_cost − commission_cost

Run on every state transition. If this drifts, the book is lying.
"""

from __future__ import annotations

import math

import pytest

from castelino.config import get_settings
from castelino.data.instruments import AssetClass
from castelino.execution.broker import OrderType, Side, TradeOrder, execute
from castelino.execution.portfolio import Portfolio


def _empty_portfolio() -> Portfolio:
    cfg = get_settings()
    return Portfolio(cash=cfg.fund.initial_nav, initial_nav=cfg.fund.initial_nav)


def _assert_invariant(pre_nav: float, fill, post_nav: float) -> None:
    expected = pre_nav - fill.slippage_cost - fill.commission_cost
    assert math.isclose(post_nav, expected, abs_tol=1e-6), (
        f"Invariant violation: pre_nav={pre_nav} post_nav={post_nav} "
        f"slippage={fill.slippage_cost} commission={fill.commission_cost} "
        f"expected={expected}"
    )


@pytest.mark.parametrize(
    "iid,qty,ref_px,side,otype",
    [
        # Equity open long
        ("SPY", 100, 500.0, Side.BUY, OrderType.MARKET_OPEN),
        # Equity open short
        ("AAPL", 50, 200.0, Side.SELL, OrderType.MARKET_OPEN),
        # Bond ETF open long
        ("TLT", 200, 90.0, Side.BUY, OrderType.MARKET_OPEN),
        # Commodity ETF open
        ("GLD", 75, 220.0, Side.BUY, OrderType.MARKET_OPEN),
        # Front-month future open (commission per contract)
        ("CL_F", 2, 78.0, Side.BUY, OrderType.MARKET_OPEN),
        # FX open
        ("EURUSD", 100_000, 1.08, Side.BUY, OrderType.MARKET_OPEN),
    ],
)
def test_open_invariant(iid, qty, ref_px, side, otype):
    pf = _empty_portfolio()
    pre_nav = pf.nav
    order = TradeOrder(
        order_id=f"test-{iid}",
        instrument_id=iid,
        order_type=otype,
        side=side,
        quantity=qty,
        reference_price=ref_px,
    )
    new_pf, fill = execute(order, pf)
    _assert_invariant(pre_nav, fill, new_pf.nav)


def test_close_invariant_at_breakeven():
    """At t=0 immediately after the open, current_price == fill_price.
    Closing at the same reference_price should still satisfy the invariant
    (slippage + commission burned twice — once each direction)."""
    pf = _empty_portfolio()

    open_order = TradeOrder(
        order_id="o1",
        instrument_id="SPY",
        order_type=OrderType.MARKET_OPEN,
        side=Side.BUY,
        quantity=100,
        reference_price=500.0,
    )
    pf, open_fill = execute(open_order, pf)
    _assert_invariant(open_fill.pre_trade_nav, open_fill, pf.nav)

    pre_close_nav = pf.nav
    close_order = TradeOrder(
        order_id="o2",
        instrument_id="SPY",
        order_type=OrderType.MARKET_CLOSE,
        side=Side.SELL,
        quantity=100,
        reference_price=500.0,
    )
    pf, close_fill = execute(close_order, pf)
    _assert_invariant(pre_close_nav, close_fill, pf.nav)


def test_full_round_trip_loses_only_friction():
    """Open at $500, close at $500 → final NAV = initial − 2× friction."""
    pf = _empty_portfolio()
    initial = pf.nav

    pf, _ = execute(
        TradeOrder(
            order_id="o1",
            instrument_id="SPY",
            order_type=OrderType.MARKET_OPEN,
            side=Side.BUY,
            quantity=100,
            reference_price=500.0,
        ),
        pf,
    )
    pf, _ = execute(
        TradeOrder(
            order_id="o2",
            instrument_id="SPY",
            order_type=OrderType.MARKET_CLOSE,
            side=Side.SELL,
            quantity=100,
            reference_price=500.0,
        ),
        pf,
    )
    # Two open-equivalent slippage hits at 5bps on $50k notional + zero commission
    # = 2 * 50000 * 5/10000 = $50 total
    expected_friction = 2 * 50_000 * 5 / 10_000
    assert math.isclose(initial - pf.nav, expected_friction, abs_tol=1e-6)
    assert pf.position("SPY") is None


def test_futures_commission_per_contract():
    """Futures commission is per contract, not flat."""
    pf = _empty_portfolio()
    pre_nav = pf.nav
    order = TradeOrder(
        order_id="cl1",
        instrument_id="CL_F",
        order_type=OrderType.MARKET_OPEN,
        side=Side.BUY,
        quantity=3,
        reference_price=80.0,
    )
    new_pf, fill = execute(order, pf)
    assert fill.commission_cost == 3 * 2.0  # 3 contracts * $2/contract
    _assert_invariant(pre_nav, fill, new_pf.nav)


@pytest.mark.parametrize(
    "iid,held,requested",
    [
        ("SPY", 100, 500),       # equity over-close
        ("TLT", 200, 1000),      # bond ETF over-close
        ("GLD", 75, 300),        # commodity ETF over-close
        ("CL_F", 2, 10),         # futures over-close (commission per contract!)
        ("EURUSD", 100_000, 500_000),  # FX over-close
    ],
)
def test_over_close_invariant(iid, held, requested):
    """Over-close must obey the sacred invariant — slippage and commission
    drive off the *actual* closed quantity, not the requested quantity. This
    is the bug the original sacred test missed."""
    pf = _empty_portfolio()
    pf, _ = execute(
        TradeOrder(
            order_id=f"open-{iid}",
            instrument_id=iid,
            order_type=OrderType.MARKET_OPEN,
            side=Side.BUY,
            quantity=held,
            reference_price=100.0,
        ),
        pf,
    )
    pre_close_nav = pf.nav
    pf, fill = execute(
        TradeOrder(
            order_id=f"close-{iid}",
            instrument_id=iid,
            order_type=OrderType.MARKET_CLOSE,
            side=Side.SELL,
            quantity=requested,  # > held on purpose
            reference_price=100.0,
        ),
        pf,
    )
    _assert_invariant(pre_close_nav, fill, pf.nav)
    assert pf.position(iid) is None
    assert fill.quantity == held


def test_short_open_then_close():
    """Short SPY at $500, cover at $480 → realized gain = 20 * 100 * 1 − friction."""
    pf = _empty_portfolio()
    initial = pf.nav

    pf, _ = execute(
        TradeOrder(
            order_id="s1",
            instrument_id="SPY",
            order_type=OrderType.MARKET_OPEN,
            side=Side.SELL,
            quantity=100,
            reference_price=500.0,
        ),
        pf,
    )
    pos = pf.position("SPY")
    assert pos is not None and pos.quantity == -100

    # Mark down so cover is profitable
    pos.current_price = 480.0

    pf, _ = execute(
        TradeOrder(
            order_id="s2",
            instrument_id="SPY",
            order_type=OrderType.MARKET_CLOSE,
            side=Side.BUY,
            quantity=100,
            reference_price=480.0,
        ),
        pf,
    )
    assert pf.position("SPY") is None
    # Gross gain = (500 - 480) * 100 = $2000. Slippage on $50k @ 5bps + $48k @ 5bps.
    slippage_open = 500.0 * (5 / 10_000) * 100  # $25
    slippage_close = 480.0 * (5 / 10_000) * 100  # $24
    expected_pnl = 2000 - slippage_open - slippage_close
    assert math.isclose(pf.nav - initial, expected_pnl, abs_tol=1e-6)
