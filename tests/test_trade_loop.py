import threading
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


def test_a_turn_with_more_calls_than_the_budget_resends_only_the_budget(fake):
    """A news desk asked for 560 calls in one turn; the API refuses a resent message with over 128 (2026-10-18)."""
    asked = [
        tool_call("yahoo_prices", {"ticker": "INDA", "start": "2026-01-01"}, cid=f"c{k}")
        for k in range(200)
    ]
    fake.script = [said(calls=asked), said("done"), parsed(TurnDraft(text="x", fact_ids=[]))]
    box = make_box(max_calls=2)
    _, msgs = run(box)
    sent = next(m for m in msgs if m["role"] == "assistant")
    assert [c["id"] for c in sent["tool_calls"]] == ["c0", "c1"]
    assert [m["tool_call_id"] for m in msgs if m["role"] == "tool"] == ["c0", "c1"]


def test_a_turns_searches_run_at_once_inside_the_budget_and_keep_their_order(fake):
    """News desks ask for 8 to 10 searches in one turn; one at a time they took 4 minutes (2026-10-15)."""
    gate = threading.Barrier(2, timeout=2)  # one search at a time would wait here, then break
    ran: list[str] = []

    def search(system, user, model=None):
        q = user.rsplit(" ", 1)[-1]
        ran.append(q)
        gate.wait()
        line = f"{q} rose 5%"
        return line, [(q, f"https://{q}.com/a", 0, len(line))]

    queries = ("alpha", "beta", "gamma")
    fake.script = [
        said(calls=[tool_call("web_search", {"query": q}) for q in queries]),
        said("done"),
        parsed(TurnDraft(text="x", fact_ids=[])),
    ]
    box = tools.TradeToolBox(
        agent="t",
        prefix="NA1.",
        allowed=["web_search"],
        board=Board(),
        end=date(2026, 10, 14),
        max_calls=2,
        search=search,
    )
    run(box)
    assert sorted(ran) == ["alpha", "beta"]  # the third is over budget, so it never starts
    assert [(f.id, f.text) for f in box.facts] == [
        ("NA1.1", "alpha rose 5%"),
        ("NA1.2", "beta rose 5%"),
    ]


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
