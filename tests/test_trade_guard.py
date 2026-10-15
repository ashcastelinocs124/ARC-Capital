from castelino.agents.trade import guard
from castelino.agents.trade.models import Report, ReportSection
from tests.trade_fakes import fact

BY = {
    "F1.1": fact("F1.1", "INDA fell 13.0% this year", [-13.0]),
    "C1.1": fact("C1.1", "rupee", [-5.3]),
}


def test_cited_errors_flags_unknown_ids_and_unsourced_figures():
    assert guard.cited_errors(["INDA fell 13.0%"], ["F1.1"], BY) == []
    errs = guard.cited_errors(["INDA fell 14.0%"], ["F1.1", "X9"], BY)
    assert "unknown fact X9" in errs and "14.0%" in errs


def test_dash_errors():
    assert guard.dash_errors(["a — b", "ok", "c – d"]) == ["dash in: a — b", "dash in: c – d"]


def report(**kw):
    secs = [
        ReportSection(key=k, heading=k, paragraphs=["INDA fell 13.0%."], fact_ids=["F1.1"])
        for k in ("bull", "bear", "question", "technical", "read")
    ]
    base = dict(
        title="t",
        subtitle="s",
        introduction=["a", "b"],
        takeaways=["1", "2", "3"],
        sections=secs,
        what_to_watch="the rupee, which took 5.3 points off",
        changes=[],
    )
    return Report(**{**base, **kw})


def test_report_shape_and_numbers():
    assert guard.report_errors(report(), BY) == []
    errs = guard.report_errors(report(introduction=["only one"], takeaways=["x"]), BY)
    assert "need 2 introduction paragraphs, got 1" in errs and "need 3 takeaways, got 1" in errs
    errs = guard.report_errors(report(what_to_watch="a 7.7% move"), BY)
    assert any("7.7%" in e for e in errs)
