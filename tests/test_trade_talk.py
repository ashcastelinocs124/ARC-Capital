import pytest

from castelino.agents.trade import llm, talk
from tests.test_trade_editor import idea, report
from tests.trade_fakes import FakeClient, parsed


def r(**kw):
    base = dict(
        answer="INDA fell 13.0% this year.",
        fact_ids=["F1.1"],
        research_question="Is the RBI defending 95 per dollar?",
        research_kind="claim",
        edit_parts=[],
        edit_instruction="",
    )
    return talk.Reply(**{**base, **kw})


@pytest.fixture
def fake(monkeypatch):
    c = FakeClient()
    monkeypatch.setattr(llm, "_client", lambda m: c)
    return c


def test_talk1_yes_adds_a_claim_to_research(fake):
    fake.script = [parsed(r())]
    msgs, item, edit = talk.reply(
        idea(),
        1,
        "ARC",
        "My read is the RBI defends 95.",
        llm.Meter(),
        decide_fn=lambda ctx, m, names, meter: {"research": 0.93},
    )
    assert [m.role for m in msgs] == ["user", "agent"] and msgs[1].decision == {"research": 0.93}
    assert item.kind == "claim" and item.text == "Is the RBI defending 95 per dollar?"
    assert item.round == 1 and edit == [] and msgs[1].action == "research"


def test_talk1_no_adds_nothing(fake):
    fake.script = [parsed(r(research_kind="question"))]
    msgs, item, edit = talk.reply(
        idea(), 1, "Bull", "Why October 13?", llm.Meter(), decide_fn=lambda *a: {"research": 0.02}
    )
    assert item is None and edit == [] and msgs[1].action == "" and msgs[0].to == "Bull"


def test_talk2_returns_each_section_to_edit_and_never_queues_research(fake):
    """Talk 2 is an assistant: it edits one or more sections now, and research happens before the reply
    (the runner's talk job), never as an item for a later round (2026-10-16)."""
    i = idea().model_copy(update={"report": report()})
    fake.script = [parsed(r(edit_parts=["bull", "bear"], edit_instruction="Open with valuation"))]
    msgs, item, edits = talk.reply(
        i,
        2,
        "ARC",
        "Make the bull and bear cases open with valuation",
        llm.Meter(),
        decide_fn=lambda *a: {"research": 0.0, "edit": 1.0},
    )
    assert edits == [("bull", "Open with valuation"), ("bear", "Open with valuation")]
    assert item is None and msgs[1].action == "edit:bull,bear"
    fake.script = [parsed(r(research_kind="question", research_question="Compare Indonesia"))]
    _, item, edits = talk.reply(
        i,
        2,
        "ARC",
        "How would Indonesia compare?",
        llm.Meter(),
        decide_fn=lambda *a: {"research": 0.97, "edit": 0.04},
    )
    assert item is None and edits == []


def test_fact_ids_the_model_writes_into_the_answer_are_taken_out(fake):
    """Haiku wrote "[NA1.14, NB1.43]" into its first live answer; the ids belong in fact_ids (chips)."""
    fake.script = [parsed(r(answer="INDA fell 13.0% this year [F1.1, F1.2]. Rates held (F1.3)."))]
    msgs, _, _ = talk.reply(
        idea(), 1, "ARC", "how much?", llm.Meter(), decide_fn=lambda *a: {"research": 0.0}
    )
    assert msgs[1].text == "INDA fell 13.0% this year. Rates held."


def test_unsourced_answer_twice_becomes_a_plain_refusal(fake):
    fake.script = [parsed(r(answer="It fell 77.0%.")), parsed(r(answer="It fell 77.0%."))]
    msgs, _, _ = talk.reply(
        idea(), 1, "ARC", "how much?", llm.Meter(), decide_fn=lambda *a: {"research": 0.1}
    )
    assert msgs[1].text == "I can't answer that from this idea's facts." and msgs[1].fact_ids == []
