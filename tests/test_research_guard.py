from castelino.agents.research.deep import guard
from castelino.agents.research.deep.models import PointDraft, ReportDraft
from tests.research_fakes import fact, xfact

BY = {
    "A1": fact("A1", "AI use 9.2% of firms", [9.2]),
    "G3": xfact("G3", "sama", "usage up 40%", [40.0]),
}


def pt(body, ids=("A1",), headline="AI use reached 9.2% of firms.", agent="A"):
    return PointDraft(agent=agent, headline=headline, body=body, fact_ids=list(ids))


def test_cited_numbers_pass():
    assert guard.point_errors(pt("The survey puts it at 9.2%."), BY) == []


def test_uncited_number_fails():
    errs = guard.point_errors(pt("The survey puts it at 9.7%."), BY)
    assert any("9.7%" in e for e in errs)


def test_x_figure_needs_its_handle_in_the_sentence():
    bad = pt("Enterprise usage rose 40%.", ids=("A1", "G3"))
    good = pt("@sama says enterprise usage rose 40%.", ids=("A1", "G3"))
    assert any("@handle" in e for e in guard.point_errors(bad, BY))
    assert guard.point_errors(good, BY) == []


def test_report_checks_owner_and_dashes():
    d = ReportDraft(
        title="AI adoption — rising",
        subtitle="US",
        points=[pt("9.2%.", agent="Z")],
        caveats=[],
        chart_specs=[],
    )
    errs = guard.report_errors(d, BY, owners={"A", "B"})
    assert any("not one of" in e for e in errs) and any("dash" in e for e in errs)


def test_report_needs_points():
    d = ReportDraft(title="t", subtitle="s", points=[], caveats=[], chart_specs=[])
    assert "the report has no points" in guard.report_errors(d, BY, owners={"A"})


def test_strip_ids():
    assert guard.strip_ids("Up to 9.2% [A1, B12]. Rising (G3).") == "Up to 9.2%. Rising."
