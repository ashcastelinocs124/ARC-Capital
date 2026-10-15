from datetime import date

import pandas as pd
import pytest

from castelino.agents.trade import llm, loop, tools
from castelino.agents.trade.models import TurnDraft
from castelino.agents.weekly.board import Board
from tests.trade_fakes import FakeClient, parsed, said, tool_call


def make_box(max_calls=2):
    idx = pd.bdate_range("2026-01-01", periods=30)
    return tools.TradeToolBox(
        agent="t",
        prefix="B1.",
        allowed=["yahoo_prices"],
        board=Board(),
        end=date(2026, 10, 14),
        max_calls=max_calls,
        yahoo=lambda t: pd.Series(range(100, 130), index=idx, dtype=float),
    )


@pytest.fixture
def fake(monkeypatch):
    c = FakeClient()
    monkeypatch.setattr(llm, "_client", lambda m: c)
    return c


def run(box, ask="Write your turn."):
    return loop.run(
        agent="trade_bull",
        model="gpt-6-sol",
        fallback=None,
        system="s",
        user="u",
        box=box,
        meter=llm.Meter(),
        schema=TurnDraft,
        ask=ask,
    )


def test_runs_tools_then_parses(fake):
    fake.script = [
        said(calls=[tool_call("yahoo_prices", {"ticker": "INDA", "start": "2026-01-01"})]),
        said("done"),
        parsed(TurnDraft(text="INDA rose 29.0%", fact_ids=["B1.1"])),
    ]
    box = make_box()
    out, msgs = run(box)
    assert out.fact_ids == ["B1.1"] and box.facts[0].id == "B1.1"
    tool_msg = next(m for m in msgs if m["role"] == "tool")
    assert tool_msg["content"].startswith("[B1.1]")
    assert msgs[-1] == {"role": "user", "content": "Write your turn."}


def test_invalid_json_counts_against_the_budget_and_exhausted_forces_none(fake):
    bad = tool_call("yahoo_prices", {})
    bad.function.arguments = "{not json"
    fake.script = [
        said(calls=[bad]),
        said(calls=[bad]),
        said("ok"),
        parsed(TurnDraft(text="x", fact_ids=[])),
    ]
    box = make_box(max_calls=2)
    run(box, ask="go")
    assert box.calls == 2
    assert fake.calls[2][1]["tool_choice"] == "none"


def test_fix_appends_errors_and_reparses(fake):
    fake.script = [parsed(TurnDraft(text="fixed", fact_ids=[]))]
    out = loop.fix(
        agent="a",
        model="gpt-6-sol",
        fallback=None,
        msgs=[{"role": "user", "content": "go"}],
        out=TurnDraft(text="bad 9%", fact_ids=[]),
        errors=["9%"],
        schema=TurnDraft,
        meter=llm.Meter(),
    )
    assert out.text == "fixed"
    sent = fake.calls[0][1]["messages"]
    assert sent[-2]["role"] == "assistant" and "9%" in sent[-1]["content"]
