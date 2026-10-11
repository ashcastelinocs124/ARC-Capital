from castelino.agents.weekly.guard import check_report, report_texts
from castelino.agents.weekly.models import (
    Bullet,
    Challenge,
    ExhibitPick,
    TrendSection,
    WeeklyReport,
)
from tests.weekly_fixtures import fact

FACTS = [fact("A1", nums=(4.38, 28)), fact("B1", nums=(4.6,), chart=False)]


def section(**kw):
    base = dict(
        title="Long end",
        agent="Rates desk",
        paragraphs=["The 10y rose 28bp to 4.38%."],
        fact_ids=["A1"],
        exhibits=[ExhibitPick(fact_id="A1", window_days=90)],
        challenges=[Challenge(question="q", answer="Real yields carried it.", verdict="Accepted")],
    )
    return TrendSection(**(base | kw))


def chips(**kw):
    return section(**({"title": "Chips", "fact_ids": ["B1"], "exhibits": []} | kw))


def report(sections, bullets=None, title="Yields up", watch="CPI Wednesday."):
    return WeeklyReport(
        title=title,
        subtitle="Term premium returns",
        bullets=bullets or [Bullet(lead="Yields jumped.", body="Up 28bp.", fact_ids=["A1"])],
        watch=watch,
        sections=sections,
    )


def test_clean_report_passes():
    assert check_report(report([section(), chips(paragraphs=["SOX +4.6%."])]), FACTS) == []


def test_unsupported_figure_and_unknown_fact_are_reported():
    rep = report([section(paragraphs=["Up 31bp."]), section(fact_ids=["Z9"], exhibits=[])])
    errs = check_report(rep, FACTS)
    assert "section 1: 31bp" in errs and "section 2: unknown fact Z9" in errs


def test_section_cannot_borrow_numbers_from_another_sections_facts():
    errs = check_report(report([section(), chips(paragraphs=["Up 28bp."])]), FACTS)
    assert "section 2: 28bp" in errs


def test_exhibit_rules():
    b1 = [ExhibitPick(fact_id="B1", window_days=90)]
    rep = report([section(exhibits=b1), chips(paragraphs=["x"], exhibits=b1)])
    errs = check_report(rep, FACTS)
    assert "section 1: exhibit B1 is not one of its facts" in errs
    assert "section 2: exhibit B1 has no chartable series" in errs


def test_section_count_bounds():
    assert "need 2 to 4 sections, got 1" in check_report(report([section()]), FACTS)


def test_report_texts_cover_every_written_field():
    texts = report_texts(report([section(), section()]))
    assert "Yields up" in texts and "The 10y rose 28bp to 4.38%." in texts
    assert "Real yields carried it." in texts


def test_challenge_question_and_verdict_figures_are_checked():
    ch = [Challenge(question="Is the 30bp claim real?", answer="Yes.", verdict="Rejected: 31bp")]
    errs = check_report(report([section(challenges=ch), chips(paragraphs=["x"])]), FACTS)
    assert "section 1 challenge: 30bp" in errs and "section 1 challenge: 31bp" in errs
    texts = report_texts(report([section(challenges=ch), section()]))
    assert "Is the 30bp claim real?" in texts and "Rejected: 31bp" in texts
