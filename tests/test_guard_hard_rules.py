"""Guard hard-rule tests — every constitutional veto must fire.

Hard rules are pure-Python; no LLM is needed. Pricing is monkeypatched so VIX
checks are deterministic.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from castelino.agents.guard import check_hard_rules
from castelino.config import get_settings
from castelino.data.instruments import AssetClass, get_instrument
from castelino.execution import pricing as pricing_mod
from castelino.execution.portfolio import NavSnapshot, Portfolio, Position
from castelino.execution.pricing import Price
from castelino.memory.schemas import (
    Direction,
    TradeExpression,
    Verdict,
)


def _trade(instrument="TLT", size=0.03, parent_hyp="hyp-test"):
    """Build a TradeExpression. Uses model_construct when size > schema cap so we
    can exercise the guard's defense even on bad inputs the schema would block.
    """
    fields = dict(
        parent_hypothesis_id=parent_hyp,
        instrument_id=instrument,
        direction=Direction.LONG,
        rationale="r",
        expected_holding_days=14,
        target_size_pct_nav=size,
        initial_stop_pct=0.04,
    )
    if size > 0.05 or size <= 0.0:
        return TradeExpression.model_construct(**fields)
    return TradeExpression(**fields)


def _verdict(mult=1.0):
    return Verdict(
        parent_expression_id="exp-test",
        parent_bull_id="bul-test",
        parent_bear_id="ber-test",
        decision="proceed",
        decisive_factor="test",
        size_multiplier=mult,
    )


def _empty_pf():
    cfg = get_settings()
    return Portfolio(cash=cfg.fund.initial_nav, initial_nav=cfg.fund.initial_nav)


@pytest.fixture
def calm_vix(monkeypatch):
    """Patch VIX to 12 so the H3 circuit breaker is dormant in baseline tests."""

    def _latest(iid):
        if iid == "VIX":
            return Price(instrument_id="VIX", price=12.0, asof=datetime.now(UTC),
                         source=pricing_mod.PriceSource.YFINANCE)
        return Price(instrument_id=iid, price=100.0, asof=datetime.now(UTC),
                     source=pricing_mod.PriceSource.YFINANCE)

    from castelino.agents import guard as guard_mod
    monkeypatch.setattr(guard_mod, "latest", _latest)


# ─────────────────────────── H1 — sizing ──────────────────────────────────


def test_h1_position_max_violated(calm_vix):
    """5%+ proposed size must veto."""
    pf = _empty_pf()
    warnings = check_hard_rules(_trade(size=0.06), _verdict(), pf)
    assert any(w.rule_id == "H1" and "exceeds" in w.description for w in warnings)


def test_h1_with_verdict_multiplier(calm_vix):
    """Size = 4% but verdict multiplier 1.5 → 6% effective. Still vetoes."""
    pf = _empty_pf()
    warnings = check_hard_rules(_trade(size=0.04), _verdict(mult=1.5), pf)
    assert any(w.rule_id == "H1" for w in warnings)


def test_h1_clean_passes(calm_vix):
    """3% size with mult 1.0 should be clean."""
    pf = _empty_pf()
    warnings = check_hard_rules(_trade(size=0.03), _verdict(), pf)
    assert warnings == []


def test_h1_asset_class_concentration(calm_vix):
    """Adding a bond ETF position when bonds already at 38% triggers veto at 40% cap."""
    pf = _empty_pf()
    # Manually plant 38% of NAV in TLT
    inst = get_instrument("TLT")
    target_value = 0.38 * pf.cash
    qty = target_value / 100.0  # fake price 100
    pf.cash -= target_value
    pf.positions.append(
        Position(
            instrument_id="TLT", quantity=qty, avg_entry_price=100.0,
            current_price=100.0, asset_class=inst.asset_class,
            opened_at=datetime.now(UTC),
        )
    )
    warnings = check_hard_rules(_trade(instrument="IEF", size=0.03), _verdict(), pf)
    assert any(w.rule_id == "H1" and "concentration" in w.description for w in warnings)


def test_h1_drawdown_freeze(calm_vix):
    """Drawdown > 10% blocks new opens."""
    pf = _empty_pf()
    pf.cash = pf.initial_nav  # NAV = 1M
    # Inject a peak NAV history so drawdown reads as 12%
    pf.nav_history = [
        NavSnapshot(timestamp=datetime.now(UTC), nav=1_140_000, cash=1_140_000,
                    gross_exposure=0, net_exposure=0),
    ]
    pf.cash = 1_000_000  # 12.3% drawdown from peak
    warnings = check_hard_rules(_trade(size=0.03), _verdict(), pf)
    assert any(w.rule_id == "H1" and "Drawdown" in w.description for w in warnings)


# ─────────────────────────── H2 — liquidity ──────────────────────────────


def test_h2_low_adv_blocks(calm_vix, monkeypatch):
    """Instrument with ADV < $50M is rejected. Patch one to pretend."""
    inst = get_instrument("AAPL")
    original_adv = inst.avg_daily_volume_usd
    # Use a low-ADV-flagged trade
    inst.avg_daily_volume_usd = 10_000_000
    try:
        pf = _empty_pf()
        warnings = check_hard_rules(_trade(instrument="AAPL", size=0.01), _verdict(), pf)
        assert any(w.rule_id == "H2" and "ADV" in w.description for w in warnings)
    finally:
        inst.avg_daily_volume_usd = original_adv


def test_h2_too_large_for_adv(calm_vix, monkeypatch):
    """Position notional > 1% of ADV blocks even if ADV is fine."""
    inst = get_instrument("XLI")  # $700M ADV
    pf = _empty_pf()
    # 5% of $1M NAV = $50K. 1% of $700M ADV = $7M. So 5% size is within ADV cap.
    # To trigger H2, need notional > 1% ADV. Bump NAV via cash so 1% size = $7M+ notional.
    # Easier: monkeypatch ADV down.
    original = inst.avg_daily_volume_usd
    inst.avg_daily_volume_usd = 51_000_000  # passes the >$50M floor
    try:
        # 1% of 51M = 510k. Want to exceed that. Need NAV * size > 510k.
        # 5% of 11M NAV = 550k. So make NAV 11M.
        pf2 = Portfolio(cash=11_000_000, initial_nav=11_000_000)
        warnings = check_hard_rules(_trade(instrument="XLI", size=0.05), _verdict(), pf2)
        assert any(w.rule_id == "H2" and "ADV" in w.description for w in warnings)
    finally:
        inst.avg_daily_volume_usd = original


# ─────────────────────────── H3 — circuit breakers ───────────────────────


def test_h3_vix_circuit_breaker(monkeypatch):
    """VIX > 40 caps gross at 50% NAV — adding new exposure that breaches vetoes."""
    def _latest(iid):
        if iid == "VIX":
            return Price(instrument_id="VIX", price=42.0, asof=datetime.now(UTC),
                         source=pricing_mod.PriceSource.YFINANCE)
        return Price(instrument_id=iid, price=100.0, asof=datetime.now(UTC),
                     source=pricing_mod.PriceSource.YFINANCE)

    from castelino.agents import guard as guard_mod
    monkeypatch.setattr(guard_mod, "latest", _latest)

    pf = _empty_pf()
    inst = get_instrument("SPY")
    # Plant 49% gross
    target = 0.49 * pf.cash
    qty = target / 100.0
    pf.cash -= target
    pf.positions.append(
        Position(
            instrument_id="SPY", quantity=qty, avg_entry_price=100.0,
            current_price=100.0, asset_class=inst.asset_class,
            opened_at=datetime.now(UTC),
        )
    )
    # Try to add 3% in TLT → would push gross to ~52%
    warnings = check_hard_rules(_trade(size=0.03), _verdict(), pf)
    assert any(w.rule_id == "H3" and "VIX" in w.description for w in warnings)


def test_h3_five_day_pnl_freeze(calm_vix):
    """5-day P&L < -5% freezes new positions."""
    pf = _empty_pf()
    # Build a drawdown sequence — 6 snapshots descending
    snaps = []
    for i, nav in enumerate([1_000_000, 990_000, 980_000, 970_000, 960_000, 940_000, 920_000]):
        snaps.append(NavSnapshot(
            timestamp=datetime.now(UTC), nav=nav, cash=nav,
            gross_exposure=0, net_exposure=0,
        ))
    pf.nav_history = snaps
    # 5d return = (920k - 990k)/990k ≈ -7%
    warnings = check_hard_rules(_trade(size=0.03), _verdict(), pf)
    assert any(w.rule_id == "H3" and "5-day" in w.description for w in warnings)


# ─────────────────────────── H5 — linkage ─────────────────────────────────


def test_h5_missing_parent_hypothesis(calm_vix):
    """Trade with empty parent_hypothesis_id is rejected."""
    pf = _empty_pf()
    bad = _trade(parent_hyp="")
    warnings = check_hard_rules(bad, _verdict(), pf)
    assert any(w.rule_id == "H5" for w in warnings)


def test_h3_skips_when_vix_unavailable(monkeypatch, caplog):
    """If VIX pricing fails, the H3 circuit breaker is skipped (with a warning),
    not silently masked. Other hard rules still run.
    """
    from castelino.execution.pricing import PricingError

    def _latest(iid):
        if iid == "VIX":
            raise PricingError("yfinance down")
        return Price(instrument_id=iid, price=100.0, asof=datetime.now(UTC),
                     source=pricing_mod.PriceSource.YFINANCE)

    from castelino.agents import guard as guard_mod
    monkeypatch.setattr(guard_mod, "latest", _latest)

    import logging
    pf = _empty_pf()
    with caplog.at_level(logging.WARNING):
        warnings = check_hard_rules(_trade(size=0.03), _verdict(), pf)
    # H3 absent (pricing failed) but the other rules ran — clean trade is clean.
    assert all(w.rule_id != "H3" for w in warnings)
    # And the logger flagged the skip
    assert any("VIX" in record.message for record in caplog.records)
