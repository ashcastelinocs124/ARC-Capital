"""Memory R/W asymmetry — every writer-identity gate enforced.

This is the structural guarantee that the design's read/write matrix isn't
just documented but actively prevents out-of-band journal writes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from castelino.memory import io as memio
from castelino.memory.io import (
    Journal,
    WriteForbidden,
    WriterIdentity,
    append_long_term,
    append_short_term,
    find_by_id,
    journal_summary,
    latest_n,
    read_long_term,
    read_short_term,
    reset_journals,
    trim_short_term,
)
from castelino.memory.schemas import (
    Hypothesis,
    KillCriterion,
    LongTermLesson,
    Regime,
    TradeEvent,
    TriggerRecord,
    TriggerSource,
)


@pytest.fixture(autouse=True)
def _isolated_journals(tmp_path, monkeypatch):
    """Redirect every journal path into a tmp dir for each test."""

    def fake_paths():
        return memio.JournalPaths(
            short_term_md=tmp_path / "st.md",
            short_term_index=tmp_path / "st_index.json",
            long_term_md=tmp_path / "lt.md",
            principles_md=tmp_path / "principles.md",
        )

    monkeypatch.setattr(memio, "_paths", fake_paths)
    yield


# ─────────────────── matrix enforcement ───────────────────


def test_only_curator_can_write_long_term():
    lesson = LongTermLesson(
        category="vehicle_preference",
        title="TLT outperforms IEF in disinflation regimes",
        body="...",
    )
    # Permitted writer
    append_long_term(lesson, WriterIdentity.CURATOR_AGENT)
    assert len(read_long_term()) == 1


@pytest.mark.parametrize(
    "who",
    [
        WriterIdentity.PORTFOLIO_AGENT,
        WriterIdentity.HYPOTHESIS_AGENT,
        WriterIdentity.GUARD_AGENT,
        WriterIdentity.EXECUTION,
        WriterIdentity.HUMAN,
        WriterIdentity.RESEARCH_AGENT,
    ],
)
def test_long_term_blocks_non_curator(who):
    lesson = LongTermLesson(category="recurring_bias", title="t", body="b")
    with pytest.raises(WriteForbidden):
        append_long_term(lesson, who)


def test_curator_cannot_freely_append_to_short_term():
    """Curator may TRIM short-term, but appending to it is forbidden."""
    trg = TriggerRecord(
        source=TriggerSource.MANUAL, headline="t", significance=0.5,
    )
    with pytest.raises(WriteForbidden, match="only TRIM"):
        append_short_term(trg, WriterIdentity.CURATOR_AGENT)


def test_portfolio_agent_can_write_short_term():
    trg = TriggerRecord(
        source=TriggerSource.CALENDAR, headline="FOMC", significance=0.9,
    )
    append_short_term(trg, WriterIdentity.PORTFOLIO_AGENT)
    assert len(read_short_term()) == 1


def test_unknown_writer_blocked():
    trg = TriggerRecord(source=TriggerSource.MANUAL, headline="x", significance=0.1)
    # Construct an "unauthorized" identity via the enum — humans aren't on the
    # ST writer list.
    with pytest.raises(WriteForbidden):
        append_short_term(trg, WriterIdentity.HUMAN)


# ─────────────────── round-trip + index ───────────────────


def test_round_trip_short_term_keeps_pydantic_types():
    h = Hypothesis(
        parent_trigger_id="trg-x",
        parent_world_state_id="wsb-x",
        thesis="USD weakens on dovish FOMC",
        regime=Regime.DISINFLATION,
        horizon_days=14,
        conviction="medium",
        kill_criteria=[KillCriterion(description="DXY > 108", metric="DXY", threshold=108, direction="above")],
        rationale="...",
    )
    append_short_term(h, WriterIdentity.HYPOTHESIS_AGENT)

    entries = read_short_term()
    assert len(entries) == 1
    got = entries[0]
    assert isinstance(got, Hypothesis)
    assert got.thesis == h.thesis
    assert got.kill_criteria[0].metric == "DXY"


def test_index_offset_resolves_entry():
    h = Hypothesis(
        parent_trigger_id="trg-1", parent_world_state_id="wsb-1",
        thesis="t", regime=Regime.RISK_ON, horizon_days=10,
        conviction="low", kill_criteria=[KillCriterion(description="x")],
        rationale="r",
    )
    append_short_term(h, WriterIdentity.HYPOTHESIS_AGENT)
    found = find_by_id(h.entry_id)
    assert found is not None and found.entry_id == h.entry_id


def test_trim_drops_old_entries_and_rebuilds_index():
    # Three triggers
    keep_ids = set()
    for i in range(3):
        trg = TriggerRecord(
            source=TriggerSource.NEWS, headline=f"news-{i}", significance=0.6,
        )
        append_short_term(trg, WriterIdentity.TRIGGER_RUNNER)
        if i == 1:
            keep_ids.add(trg.entry_id)
    dropped = trim_short_term(keep_ids, WriterIdentity.CURATOR_AGENT)
    assert dropped == 2

    remaining = read_short_term()
    assert len(remaining) == 1
    assert remaining[0].entry_id in keep_ids
    # Index must be rebuilt — find_by_id should still work
    assert find_by_id(remaining[0].entry_id) is not None


def test_latest_n_filters_by_kind():
    for i in range(3):
        trg = TriggerRecord(
            source=TriggerSource.CRON_FALLBACK, headline=f"h-{i}", significance=0.3,
        )
        append_short_term(trg, WriterIdentity.TRIGGER_RUNNER)
    h = Hypothesis(
        parent_trigger_id="x", parent_world_state_id="y",
        thesis="t", regime=Regime.UNCERTAIN, horizon_days=7,
        conviction="low", kill_criteria=[KillCriterion(description="d")],
        rationale="r",
    )
    append_short_term(h, WriterIdentity.HYPOTHESIS_AGENT)

    triggers = latest_n(kind="TriggerRecord", n=10)
    assert len(triggers) == 3
    hyps = latest_n(kind="Hypothesis", n=10)
    assert len(hyps) == 1
    summary = journal_summary()
    assert summary["TriggerRecord"] == 3 and summary["Hypothesis"] == 1


def test_trade_event_round_trips():
    ev = TradeEvent(
        event_type="open", instrument_id="TLT",
        parent_hypothesis_id="hyp-x", parent_expression_id="exp-x",
        quantity=100, fill_price=90.05, slippage_cost=4.5, commission_cost=0.0,
        pre_trade_nav=1_000_000.0, post_trade_nav=999_995.5,
    )
    append_short_term(ev, WriterIdentity.EXECUTION)
    got = read_short_term()
    assert isinstance(got[0], TradeEvent)
    assert got[0].instrument_id == "TLT"


def test_reset_journals_requires_token():
    with pytest.raises(RuntimeError, match="reset_journals refused"):
        reset_journals()
    reset_journals(confirm_token="I_KNOW_WHAT_I_AM_DOING")
