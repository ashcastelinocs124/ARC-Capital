"""Curator (deterministic prune) + report generators smoke tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from castelino.agents import curator as curator_mod
from castelino.execution.portfolio import NavSnapshot, Portfolio, Position
from castelino.memory import io as memio
from castelino.memory.io import WriterIdentity
from castelino.memory.schemas import (
    Conviction,
    Hypothesis,
    KillCriterion,
    PrincipleWarning,
    Regime,
    TradeEvent,
    TriggerRecord,
    TriggerSource,
)


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
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
    # Redirect reports + data dirs into tmp
    from castelino import config as config_mod
    settings = config_mod.load_settings.cache_clear  # noqa: F841 just to access
    config_mod.load_settings.cache_clear()
    s = config_mod.get_settings()
    monkeypatch.setattr(s.paths, "data_dir", str(tmp_path))
    monkeypatch.setattr(s.paths, "reports_dir", str(tmp_path / "reports"))
    monkeypatch.setattr(s.paths, "cache_dir", str(tmp_path / "cache"))
    s.root = tmp_path  # type: ignore[misc]
    yield


def test_capacity_filter_keeps_open_trades_and_recent():
    """Closed trades older than capacity should not be in the keep set; opens stay."""
    now = datetime.now(UTC)

    # Append 25 closed trades (older + newer)
    closed = []
    for i in range(25):
        ev = TradeEvent(
            timestamp=now - timedelta(days=120 + i),  # older
            event_type="close",
            instrument_id=f"X{i}",
            quantity=10,
            fill_price=100.0,
            slippage_cost=1.0,
            commission_cost=0.0,
            pre_trade_nav=1_000_000,
            post_trade_nav=999_999,
        )
        closed.append(ev)
        memio.append_short_term(ev, WriterIdentity.EXECUTION)

    # 1 open + recent
    open_ev = TradeEvent(
        timestamp=now,
        event_type="open",
        instrument_id="TLT",
        quantity=10,
        fill_price=90.0,
        slippage_cost=0.5,
        commission_cost=0.0,
        pre_trade_nav=1_000_000,
        post_trade_nav=999_999,
    )
    memio.append_short_term(open_ev, WriterIdentity.EXECUTION)

    # Recent hypothesis
    hyp = Hypothesis(
        timestamp=now - timedelta(days=2),
        parent_trigger_id="t", parent_world_state_id="w",
        thesis="t", regime=Regime.RISK_ON, horizon_days=10,
        conviction=Conviction.LOW,
        kill_criteria=[KillCriterion(description="x")],
        rationale="r",
    )
    memio.append_short_term(hyp, WriterIdentity.HYPOTHESIS_AGENT)

    # Old hypothesis (40 days back, beyond window)
    old_hyp = Hypothesis(
        timestamp=now - timedelta(days=45),
        parent_trigger_id="t", parent_world_state_id="w",
        thesis="t", regime=Regime.RISK_ON, horizon_days=10,
        conviction=Conviction.LOW,
        kill_criteria=[KillCriterion(description="x")],
        rationale="r",
    )
    memio.append_short_term(old_hyp, WriterIdentity.HYPOTHESIS_AGENT)

    keep = curator_mod._capacity_filter(memio.read_short_term())
    # Open trade kept
    assert open_ev.entry_id in keep
    # Recent hypothesis kept; old not
    assert hyp.entry_id in keep
    assert old_hyp.entry_id not in keep
    # ≤ 20 closed trades retained
    closed_kept = [e for e in closed if e.entry_id in keep]
    assert len(closed_kept) <= 20


def test_prune_only_drops_trimmed_entries():
    now = datetime.now(UTC)
    keep_target = []
    drop_target = []

    # 2 recent triggers (kept); 2 ancient (dropped)
    for i in range(2):
        t = TriggerRecord(
            timestamp=now,
            source=TriggerSource.NEWS,
            headline=f"recent-{i}",
            significance=0.5,
        )
        memio.append_short_term(t, WriterIdentity.TRIGGER_RUNNER)
        keep_target.append(t.entry_id)
    for i in range(2):
        t = TriggerRecord(
            timestamp=now - timedelta(days=120),
            source=TriggerSource.NEWS,
            headline=f"old-{i}",
            significance=0.5,
        )
        memio.append_short_term(t, WriterIdentity.TRIGGER_RUNNER)
        drop_target.append(t.entry_id)

    out = curator_mod.prune_only()
    remaining = {e.entry_id for e in memio.read_short_term()}
    for eid in keep_target:
        assert eid in remaining
    for eid in drop_target:
        assert eid not in remaining
    assert out["n_entries_trimmed"] == 2


def test_reports_generate_with_seeded_state(tmp_path):
    """End-to-end smoke: with a seeded portfolio + a fake fill, regenerate_all returns paths."""
    from castelino.config import get_settings
    from castelino.reporting import regenerate_all

    cfg = get_settings()

    # Seed: NAV history + 1 open position + 1 closed trade event
    pf = Portfolio(cash=950_000, initial_nav=1_000_000)
    pf.nav_history = [
        NavSnapshot(
            timestamp=datetime.now(UTC) - timedelta(days=i),
            nav=1_000_000 + i * 200,
            cash=950_000,
            gross_exposure=50_000,
            net_exposure=50_000,
        )
        for i in range(10, 0, -1)
    ]
    pf.positions = [
        Position(
            instrument_id="TLT", quantity=100, avg_entry_price=90.0,
            current_price=92.0, asset_class="bond_etf",
            opened_at=datetime.now(UTC),
        )
    ]
    pf.save()

    # Closed trade event
    memio.append_short_term(
        TradeEvent(
            event_type="close", instrument_id="GLD",
            parent_hypothesis_id="hyp-x",
            quantity=-50, fill_price=215.0, slippage_cost=11, commission_cost=0,
            realized_pnl=400.0, pre_trade_nav=999_000, post_trade_nav=999_400,
        ),
        WriterIdentity.EXECUTION,
    )

    paths = regenerate_all()
    assert len(paths) >= 4
    for p in paths:
        assert Path(p).exists(), f"missing report file: {p}"
