from datetime import date

import numpy as np
import pandas as pd
import pytest

from castelino.agents.trade import debate, framer, llm
from castelino.agents.trade.models import (
    Frame,
    Moderation,
    OpenQ,
    Settled,
    StandIn,
    StepError,
    TurnDraft,
)
from tests.trade_fakes import FakeClient, fact, parsed, said

IDX = pd.bdate_range("2025-06-01", periods=400)
PX = pd.Series(np.linspace(100, 120, 400), index=IDX)
NO_NEWS = lambda *a, **k: ("", [])  # noqa: E731


@pytest.fixture
def fake(monkeypatch):
    c = FakeClient()
    monkeypatch.setattr(llm, "_client", lambda m: c)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)  # DeepSeek roles fall back to OpenAI
    return c


def a_frame(*tickers):
    return Frame(
        title="India as an AI hedge",
        thesis="t",
        stand_ins=[
            StandIn(ticker=t, role="subject" if i == 0 else "benchmark", label=t)
            for i, t in enumerate(tickers)
        ],
        horizon_months=12,
        prove_wrong=["INDA correlates above 0.6 with SMH"],
        why_now_query="q",
    )


def test_framer_makes_a_fact_per_ticker_and_why_now_facts(fake):
    fake.script = [parsed(a_frame("INDA", "SMH"))]
    news = (
        "India stocks fell as funds rotated to AI.",
        [("Reuters", "https://reuters.com/x", 0, 10)],
    )
    m = llm.Meter()
    fr, facts = framer.frame(
        "India is an AI hedge",
        m,
        prices=lambda t: PX,
        search=lambda *a, **k: news,
        today=date(2026, 10, 14),
    )
    assert [f.id for f in facts] == ["F1.1", "F1.2", "F1.3"] and facts[0].series.id == "INDA"
    assert facts[2].provenance == "reported" and m.total >= llm.SEARCH_USD


def test_framer_retries_bad_ticker_then_fails_clearly(fake):
    def prices(t):
        if t == "NIFTY":
            raise RuntimeError("yfinance returned empty")
        return PX

    fake.script = [parsed(a_frame("NIFTY", "SMH")), parsed(a_frame("NIFTY", "SMH"))]
    with pytest.raises(StepError, match="NIFTY"):
        framer.frame(
            "Nifty is an AI hedge",
            llm.Meter(),
            prices=prices,
            search=NO_NEWS,
            today=date(2026, 10, 14),
        )
    retry_msgs = fake.calls[1][1]["messages"]
    assert "NIFTY" in retry_msgs[-1]["content"]


def test_debate_runs_three_rounds_per_side_and_guards_numbers(fake):
    facts = [fact("F1.1", "INDA fell 13.0% this year", [-13.0])]
    good = [said("ok"), parsed(TurnDraft(text="INDA fell 13.0%.", fact_ids=["F1.1"]))]
    fake.script = good * 6  # each turn: one chat reply with no tool calls, then the parse
    turns, new = debate.run(a_frame("INDA", "SMH"), facts, llm.Meter(), yahoo=lambda t: PX)
    assert [(t.side, t.round) for t in turns] == [
        ("bull", 0),
        ("bear", 0),
        ("bull", 1),
        ("bear", 1),
        ("bull", 2),
        ("bear", 2),
    ]
    assert new == []


def test_turn_with_unsourced_number_is_fixed_once_then_fails(fake):
    facts = [fact("F1.1", "INDA fell 13.0% this year", [-13.0])]
    bad = TurnDraft(text="INDA fell 20.0%.", fact_ids=["F1.1"])
    fake.script = [said("ok"), parsed(bad), parsed(bad)] * 2  # both sides fail twice
    with pytest.raises(StepError, match="20.0%"):
        debate.run(a_frame("INDA", "SMH"), facts, llm.Meter(), yahoo=lambda t: PX)


def test_moderator_checks_ids(fake):
    by = {"F1.1": fact("F1.1", "x", [1.0])}
    opens = [OpenQ(question="q", why="w")] * 2
    good = Moderation(settled=[Settled(point="p", fact_ids=["F1.1"])], open=opens)
    bad = Moderation(settled=[Settled(point="p", fact_ids=["Z1"])], open=opens)
    fake.script = [parsed(bad), parsed(good)]
    assert debate.moderate(a_frame("INDA"), [], by, llm.Meter()) == good
