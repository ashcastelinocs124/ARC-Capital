"""Mark-loop coherence tests — stop-out journalling, short-stops, dedupe."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from castelino.config import get_settings
from castelino.data.instruments import AssetClass
from castelino.execution import mark_loop, pricing as pricing_mod
from castelino.execution.mark_loop import detect_stops, run_mark_loop
from castelino.execution.portfolio import Portfolio, Position
from castelino.execution.pricing import Price
from castelino.memory import io as memio
from castelino.memory.schemas import TradeEvent


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    def fake_paths():
        return memio.JournalPaths(
            short_term_md=tmp_path / "st.md",
            short_term_index=tmp_path / "st_idx.json",
            long_term_md=tmp_path / "lt.md",
            principles_md=tmp_path / "p.md",
        )

    monkeypatch.setattr(memio, "_paths", fake_paths)
    monkeypatch.setattr(
        Portfolio, "default_path", classmethod(lambda cls: tmp_path / "portfolio.json")
    )
    monkeypatch.setattr(mark_loop, "write_exposure_snapshot", lambda pf, path=None: None)


@pytest.fixture
def fixed_price(monkeypatch):
    """latest() returns 80 — below the long stop (90) so the long is taken out,
    above the short's stop (70) so the short is also taken out."""

    def _latest(iid):
        return Price(
            instrument_id=iid, price=80.0,
            asof=datetime.now(UTC),
            source=pricing_mod.PriceSource.YFINANCE,
        )

    monkeypatch.setattr(mark_loop, "latest", _latest)
    return _latest


def _pf_with_long_stopped() -> Portfolio:
    cfg = get_settings()
    pf = Portfolio(cash=cfg.fund.initial_nav - 9_000, initial_nav=cfg.fund.initial_nav)
    pf.positions.append(
        Position(
            instrument_id="TLT", quantity=100, avg_entry_price=100.0,
            current_price=90.0, asset_class=AssetClass.BOND_ETF,
            opened_at=datetime.now(UTC),
            stop_loss=90.0,           # crossed below
            parent_hypothesis_id="hyp-x",
            parent_expression_id="exp-x",
        )
    )
    return pf


def test_long_stop_journals_trade_event(fixed_price):
    """Stop-out closes write a TradeEvent — the previous bug missed this."""
    pf = _pf_with_long_stopped()
    pf, fills, warns = run_mark_loop(pf)
    assert len(fills) == 1
    assert pf.position("TLT") is None
    counts = memio.journal_summary()
    assert counts.get("TradeEvent", 0) == 1
    # The journal entry is a stop-loss, not an open/close
    events = [e for e in memio.read_short_term() if isinstance(e, TradeEvent)]
    assert len(events) == 1
    assert events[0].event_type == "stop_loss"
    assert events[0].parent_hypothesis_id == "hyp-x"


def test_short_stop_detected_on_upside_break(fixed_price, monkeypatch):
    """Short positions stop out on UPSIDE crosses."""

    def _latest(iid):  # mark to 75 — above short's stop_loss=70
        return Price(
            instrument_id=iid, price=75.0,
            asof=datetime.now(UTC),
            source=pricing_mod.PriceSource.YFINANCE,
        )

    monkeypatch.setattr(mark_loop, "latest", _latest)
    pf = Portfolio(cash=1_000_000, initial_nav=1_000_000)
    pf.positions.append(
        Position(
            instrument_id="TLT", quantity=-50, avg_entry_price=80.0,
            current_price=75.0, asset_class=AssetClass.BOND_ETF,
            opened_at=datetime.now(UTC), stop_loss=70.0,
        )
    )
    # detect_stops looks at current_price; mark first
    pf, _ = mark_loop.mark_to_market(pf)
    orders = detect_stops(pf)
    assert len(orders) == 1
    assert orders[0].side.value == "buy"
    assert orders[0].quantity == 50


def test_no_stop_when_position_intact(fixed_price):
    pf = Portfolio(cash=1_000_000, initial_nav=1_000_000)
    pf.positions.append(
        Position(
            instrument_id="TLT", quantity=10, avg_entry_price=100.0,
            current_price=95.0, asset_class=AssetClass.BOND_ETF,
            opened_at=datetime.now(UTC),
            stop_loss=85.0,  # well below current
        )
    )
    orders = detect_stops(pf)
    assert orders == []


def test_mark_loop_writer_identity_is_mark_loop(fixed_price):
    """The R/W matrix must accept MARK_LOOP for these writes."""
    pf = _pf_with_long_stopped()
    # If we passed the wrong identity here, append_short_term would raise.
    pf, fills, _ = run_mark_loop(pf)
    assert len(fills) == 1
