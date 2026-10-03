"""Sector explainers fill narrative + prose via the LLM client, and fail soft."""

from datetime import UTC, datetime

import pytest

from castelino.agents import base
from castelino.agents.base import FakeLLMClient
from castelino.agents.sector_explainer import SectorNarrative, SectorProse, explain_snapshot
from castelino.signals.sector_sentiment import (
    SectorSentimentSnapshot,
    StockRow,
    aggregate_sectors,
)


def _row(sym, div, cap):
    return StockRow(
        symbol=sym,
        name=sym,
        sector="Energy",
        market_cap=cap,
        rsi14=60,
        macd_hist=None,
        vs_sma50=None,
        vs_sma200=0.1,
        ret_3m=None,
        rev_yoy=0.05,
        earnings_growth=None,
        pe_rel=1.0,
        tech_score=div,
        fund_score=0.0,
        divergence=div,
    )


@pytest.fixture
def snap():
    rows = [_row("XOM", 0.6, 500e9), _row("CVX", 0.4, 300e9), _row("COP", -0.1, 100e9)]
    return SectorSentimentSnapshot(
        as_of=datetime(2026, 10, 3, tzinfo=UTC), sectors=aggregate_sectors(rows), stocks=rows
    )


@pytest.fixture
def fake():
    client = FakeLLMClient()
    base.set_llm_client(client)
    yield client
    base.set_llm_client(None)


def test_fills_narrative_and_sector_prose(snap, fake):
    fake.register(
        "SectorNarrative",
        lambda s, u: SectorNarrative(narrative="Energy leads.", biggest_move="Energy +0.47"),
    )
    fake.register("SectorProse", lambda s, u: SectorProse(explanation="XOM drives it."))

    out = explain_snapshot(snap, prev_narrative="yesterday")

    assert out.narrative == "Energy leads." and out.narrative_generated_at
    assert out.sectors[0].explanation.prose == "XOM drives it."
    # the prompt carries the computed verdict and the prior narrative
    calls = {name: user for name, _, _, user in fake.call_log}
    assert "VERDICT (final, computed)" in calls["SectorProse"]
    assert "yesterday" in calls["SectorNarrative"]


def test_llm_failure_ships_numbers_without_text(snap, fake):
    # no handlers registered -> every call raises
    out = explain_snapshot(snap)
    assert out.narrative is None
    assert out.sectors[0].explanation.prose is None
    assert out.sectors[0].divergence == snap.sectors[0].divergence
