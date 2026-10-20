import pytest
from pydantic import ValidationError

from castelino.agents.research.deep import charts
from castelino.agents.research.deep.models import ChartSet, ChartValue, Point, PointChartDraft
from castelino.agents.trade import llm
from tests.research_fakes import fact
from tests.trade_fakes import FakeClient, parsed

BY = {
    "A1": fact("A1", "EU: 20.0% of enterprises used AI in 2025", [20.0, 2025]),
    "A3": fact("A3", "OECD: 20.2% in 2025", [20.2, 2025]),
    "A6": fact("A6", "US: 19.8% as of May 3, 2026", [19.8, 3, 2026]),
    "C14": fact("C14", "Klarna's assistant handled 69% of chats", [69.0]),
}
P1 = Point(
    id="p1",
    agent="A",
    headline="Roughly one in five enterprises use AI.",
    body="EU 20.0%, OECD 20.2% and US 19.8%.",
    fact_ids=["A1", "A3", "A6"],
)
P9 = Point(
    id="p9",
    agent="C",
    headline="Customer service is the clearest example of deep deployment in 2025.",
    body="Klarna's assistant handled 69% of chats.",
    fact_ids=["C14"],
)


def v(fid, label, value):
    return ChartValue(fact_id=fid, label=label, value=value)


GOOD_P1 = PointChartDraft(
    point_id="p1",
    form="bars",
    title="Share of enterprises using AI",
    unit="%",
    values=[
        v("A1", "EU (2025)", 20.0),
        v("A3", "OECD (2025)", 20.2),
        v("A6", "US (May 2026)", 19.8),
    ],
)


@pytest.fixture
def fake(monkeypatch):
    c = FakeClient()
    monkeypatch.setattr(llm, "_client", lambda m: c)
    return c


def test_guard_accepts_cited_numbers():
    assert charts.chart_errors(GOOD_P1, P1, BY) == []


def test_guard_rejects_a_number_not_in_its_fact_an_uncited_fact_and_a_bad_size():
    bad = GOOD_P1.model_copy(
        update={"values": [v("A1", "EU", 21.0), v("C14", "Klarna", 69.0)], "form": "dumbbell"}
    )
    errs = charts.chart_errors(bad, P1, BY)
    assert any("21.0 is not a number of A1" in e for e in errs)
    assert any("C14 is not one of this point's facts" in e for e in errs)
    one = GOOD_P1.model_copy(update={"values": GOOD_P1.values[:1]})
    assert any("bars needs 2-10" in e for e in charts.chart_errors(one, P1, BY))


def test_the_chart_agent_cannot_draw_a_single_figure_tile():
    with pytest.raises(ValidationError):
        PointChartDraft(point_id="p9", form="stat", title="t", unit="%", values=[])
    assert "stat" not in charts.SIZES and "Never chart a single figure" in charts.SYSTEM


def test_chart_points_in_one_call_on_gpt_6_luna(fake):
    fake.script = [parsed(ChartSet(charts=[GOOD_P1]))]
    got = charts.chart_points([P1], BY, llm.Meter())
    assert got["p1"].form == "bars" and [x.value for x in got["p1"].values] == [20.0, 20.2, 19.8]
    assert len(fake.calls) == 1 and fake.calls[0][1]["model"] == "gpt-6-luna"
    assert (
        "[A6] US: 19.8% as of May 3, 2026 | numbers: 19.8, 3, 2026"
        in fake.calls[0][1]["messages"][1]["content"]
    )


def test_one_retry_fixes_only_the_failed_points(fake):
    wrong = GOOD_P1.model_copy(update={"values": [v("A1", "EU", 21.0), v("A3", "OECD", 20.2)]})
    fake.script = [parsed(ChartSet(charts=[wrong])), parsed(ChartSet(charts=[GOOD_P1]))]
    got = charts.chart_points([P1], BY, llm.Meter())
    assert got["p1"].values[0].value == 20.0 and not got["p1"].fallback
    assert "p1: 21.0 is not a number of A1" in fake.calls[1][1]["messages"][-1]["content"]


def test_a_point_with_one_figure_gets_no_chart_never_a_one_value_tile(fake):
    no_p9 = ChartSet(charts=[GOOD_P1])
    fake.script = [parsed(no_p9), parsed(no_p9)]
    got = charts.chart_points([P1, P9], BY, llm.Meter())
    assert "p9" not in got and "leave out a point" in fake.calls[1][1]["messages"][-1]["content"]


def test_a_model_outage_never_fails_the_run(fake):
    fake.script = [RuntimeError("down")] * 2
    assert charts.chart_points([P1, P9], BY, llm.Meter()) == {}


def test_a_point_without_any_cited_figure_has_no_chart(fake):
    plain = Point(
        id="p5",
        agent="A",
        headline="Adoption is broad.",
        body="Many firms use it.",
        fact_ids=["A1"],
    )
    fake.script = [parsed(ChartSet(charts=[])), parsed(ChartSet(charts=[]))]
    assert charts.chart_points([plain], BY, llm.Meter()) == {}
