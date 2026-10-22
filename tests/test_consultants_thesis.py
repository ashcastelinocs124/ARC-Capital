import pytest

from castelino.agents.consultants import thesis
from castelino.agents.consultants.models import Part, ThesisDraft
from castelino.agents.trade import llm
from castelino.agents.update.models import Fact


def fact(fid: str, nums: list[float]) -> Fact:
    return Fact(
        id=fid, text=f"t {fid}", numbers=nums, provenance="data", source_title="s", source_url="u"
    )


FACTS = {
    "K1-20261015-1": fact("K1-20261015-1", [41.2]),
    "K1-20261015-2": fact("K1-20261015-2", [6.3]),
}


def draft(
    happening="Chip makers keep spending; funding is the squeeze.", ids=("K1-20261015-1",), **kw
):
    p = Part(text=happening, fact_ids=list(ids))
    plain = Part(text="If cloud budgets hold, the squeeze stays with small builders.", fact_ids=[])
    return ThesisDraft(
        happening=p,
        lean=kw.get("lean", plain),
        alternative=kw.get("alternative", plain),
        change_mind=kw.get("change_mind", plain),
        reason="funding risk is new",
    )


def test_errors_flags_unknown_ids_and_unsupported_figures():
    d = draft(happening="Revenue grew 9% while listings stalled.", ids=("K1-20261015-1", "K9-1-1"))
    errs = thesis.errors(d, FACTS)
    assert any("K9-1-1" in e for e in errs)
    assert any("9%" in e for e in errs)


def test_errors_accepts_a_supported_figure():
    assert (
        thesis.errors(draft(happening="Revenue grew 41.2% a year.", ids=("K1-20261015-1",)), FACTS)
        == []
    )


def test_errors_flags_too_many_figures():
    one = Part(text="Grew 41.2%.", fact_ids=["K1-20261015-1"])
    d = draft(happening="Grew 41.2%.", lean=one, alternative=one)
    assert any("analysis, not data points: 3 figures" in e for e in thesis.errors(d, FACTS))


def _stub(monkeypatch, drafts: list[ThesisDraft]) -> list:
    calls = []

    def fake(agent, model, messages, schema, meter, **kw):
        calls.append(messages)
        return drafts[len(calls) - 1]

    monkeypatch.setattr(llm, "structured", fake)
    return calls


def test_write_retries_once_then_succeeds(monkeypatch):
    calls = _stub(monkeypatch, [draft(happening="Up 9%."), draft()])
    t = thesis.write("AI", list(FACTS.values()), "", None, "2026-10-15", llm.Meter())
    assert len(calls) == 2 and "9%" in calls[1][-1]["content"]
    assert (t.version, t.updated) == (1, "2026-10-15")


def test_write_bumps_version_from_old(monkeypatch):
    _stub(monkeypatch, [draft()])
    first = thesis.write("AI", list(FACTS.values()), "", None, "2026-10-15", llm.Meter())
    _stub(monkeypatch, [draft()])
    assert (
        thesis.write("AI", list(FACTS.values()), "", first, "2026-10-16", llm.Meter()).version == 2
    )


def test_write_raises_after_second_failure(monkeypatch):
    _stub(monkeypatch, [draft(happening="Up 9%."), draft(happening="Up 8%.")])
    with pytest.raises(ValueError):
        thesis.write("AI", list(FACTS.values()), "", None, "2026-10-15", llm.Meter())


def test_system_prompt_rules():
    s = thesis.SYSTEM.lower()
    for phrase in ("what is happening", "what could happen", "no buy or sell", "not data points"):
        assert phrase in s
    assert "outlook" in s and "made-up" in s
