from datetime import date

from castelino.agents.consultants import consult, store
from castelino.agents.consultants.models import Answer, Part, Thesis, Watchlist
from castelino.agents.research.deep import sub_agent
from castelino.agents.research.deep.tools import ResearchToolBox
from castelino.agents.trade import llm
from castelino.agents.trade.tools import TradeToolBox
from castelino.agents.update.models import Fact
from castelino.agents.weekly.board import Board
from castelino.agents.weekly.tools import ToolBox

WL = Watchlist(companies=[], series=[], queries=["q"])
TODAY = date.today()
FID = f"K1-{TODAY:%Y%m%d}-1"


def fact(fid: str, nums=(41.2,)) -> Fact:
    return Fact(
        id=fid,
        text=f"TSMC revenue grew 41.2% ({fid})",
        numbers=list(nums),
        provenance="data",
        source_title="TSMC",
        source_url="u",
    )


def consultant(topic="AI models and chips", text="Funding is the squeeze."):
    c = store.create(topic, WL)
    p = Part(text=text, fact_ids=[FID] if c.code == "K1" else [])
    store.write_thesis(
        c.slug,
        Thesis(
            happening=p, lean=p, alternative=p, change_mind=p, reason="r", updated="x", version=1
        ),
    )
    store.write_facts(c.slug, TODAY.isoformat(), [fact(f"{c.code}-{TODAY:%Y%m%d}-1")])
    return c


def stub_answer(monkeypatch, answers: list[Answer]) -> list:
    calls = []

    def fake(agent, model, messages, schema, meter, **kw):
        calls.append((agent, model, messages))
        return answers[len(calls) - 1]

    monkeypatch.setattr(llm, "structured", fake)
    return calls


def test_spec_none_without_consultants():
    assert consult.spec() is None


def test_spec_lists_active_slugs_as_enum():
    a = consultant()
    b = consultant("India")
    with store.edit(b.slug) as x:
        x.status = "paused"
    s = consult.spec()
    assert s["name"] == "consult" and s["strict"] is True
    assert s["parameters"]["properties"]["topic"]["enum"] == [a.slug]
    assert "AI models and chips" in s["description"]


def test_answer_logs_ask_and_returns_cited_facts(monkeypatch):
    c = consultant()
    calls = stub_answer(monkeypatch, [Answer(text="The squeeze is financing.", fact_ids=[FID])])
    text, facts = consult.answer(c.slug, "Is AI funding tightening?", asker="Weekly · desk B")
    assert text == "The squeeze is financing." and [f.id for f in facts] == [FID]
    assert calls[0][0] == "consultant_answer" and calls[0][1] == "gpt-6-luna"
    day = store.day_log(c.slug, TODAY.isoformat())
    assert [a.asker for a in day.asks] == ["Weekly · desk B"] and day.cost_usd == 0.0


def test_answer_retries_then_drops_an_invented_figure(monkeypatch):
    c = consultant()
    bad = Answer(text="Revenue grew 9%. The squeeze is financing.", fact_ids=[FID])
    stub_answer(monkeypatch, [bad, bad])
    text, _ = consult.answer(c.slug, "q", asker="x")
    assert "9%" not in text and "squeeze is financing" in text


def test_answer_never_researches(monkeypatch):
    c = consultant()

    def boom(*a, **k):
        raise AssertionError("consult must not research")

    monkeypatch.setattr(sub_agent, "research", boom)
    stub_answer(monkeypatch, [Answer(text="ok", fact_ids=[])])
    assert consult.answer(c.slug, "q", asker="x")[0] == "ok"


def test_for_note_saves_and_reuses_the_day(tmp_path):
    c = consultant()
    first = consult.for_note("2026-10-15", tmp_path / "updates")
    assert first.codes == {c.slug: "K1"} and first.names == {c.slug: "AI models and chips"}
    assert "Funding is the squeeze." in first.prompt_md and FID in first.prompt_md
    assert "Funding is the squeeze." in first.watch_md
    assert [f.id for f in first.facts] == [FID]
    p = Part(text="Changed later.", fact_ids=[])
    store.write_thesis(
        c.slug,
        Thesis(
            happening=p, lean=p, alternative=p, change_mind=p, reason="r", updated="y", version=2
        ),
    )
    again = consult.for_note("2026-10-15", tmp_path / "updates")
    assert again.prompt_md == first.prompt_md


def _box(cls=ToolBox, **kw):
    return cls(
        agent="desk B",
        prefix="B",
        allowed=[],
        board=Board(),
        end=TODAY,
        max_calls=4,
        **kw,
    )


def test_toolbox_consult_copies_facts_and_specs_include_consult(monkeypatch):
    c = consultant()
    box = _box()
    assert "consult" in [s["name"] for s in box.specs()]
    stub_answer(monkeypatch, [Answer(text="The squeeze is financing.", fact_ids=[FID])])
    out = box.call("consult", {"topic": c.slug, "question": "Is funding tightening?"})
    assert out.startswith("The squeeze is financing.") and f"[{FID}]" in out
    assert [f.id for f in box.facts] == [FID] and box.calls == 1
    assert (
        box.call("consult", {"topic": "nope", "question": "q"})
        == "Error: no consultant called nope"
    )


def test_toolbox_without_consultants_has_no_consult_spec():
    assert "consult" not in [s["name"] for s in _box().specs()]


def test_trade_and_research_boxes_offer_consult():
    consultant()
    trade = _box(TradeToolBox, meter=llm.Meter())
    research = _box(ResearchToolBox, meter=llm.Meter())
    assert "consult" in [s["name"] for s in trade.specs()]
    assert "consult" in [s["name"] for s in research.specs()]
