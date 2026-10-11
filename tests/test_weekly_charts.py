from castelino.agents.update import charts as uc
from castelino.agents.update.models import SeriesRef
from castelino.agents.weekly.charts import make_weekly_exhibits, window_label
from castelino.agents.weekly.models import ExhibitPick, TrendSection, WeeklyReport
from tests.weekly_fixtures import fact


def test_window_labels():
    assert [window_label(d) for d in (7, 30, 90, 180, 365, 1100)] == [
        "last week",
        "last month",
        "last 3 months",
        "last 6 months",
        "last year",
        "last 3 years",
    ]


def test_title_uses_window_label_when_given():
    ref = SeriesRef(kind="daily", provider="fred", id="DGS10", label="DGS10")
    assert uc.title_for(2, ref, 63, window_label="last 3 months") == (
        "Exhibit 2: DGS10 · last 3 months"
    )
    assert uc.title_for(2, ref, 7) == "Exhibit 2: DGS10 · last 7 obs"  # Morning Note unchanged


def sec(exhibits):
    return TrendSection(
        title="t", agent="a", paragraphs=["p"], fact_ids=["A1"], exhibits=exhibits, challenges=[]
    )


def test_weekly_exhibits_numbered_across_sections_with_windows(tmp_path):
    seen = []

    def fetch(ref, window_days):
        seen.append(window_days)
        return [(f"Jul {i:02d}", 4.0 + i / 100) for i in range(1, 40)]

    rep = WeeklyReport(
        title="T",
        subtitle="S",
        bullets=[],
        watch="W",
        sections=[
            sec([ExhibitPick(fact_id="A1", window_days=90)]),
            sec(
                [
                    ExhibitPick(fact_id="NOPE", window_days=30),
                    ExhibitPick(fact_id="A1", window_days=365),
                ]
            ),
        ],
    )
    out = make_weekly_exhibits(rep, [fact("A1")], tmp_path, fetch=fetch)
    assert [(e.n, e.section, e.file) for e in out] == [
        (1, 0, "exhibit_1.png"),
        (2, 1, "exhibit_2.png"),
    ]
    assert seen == [90, 365] and (tmp_path / "exhibit_2.png").stat().st_size > 0
    assert out[0].title.endswith("· last 3 months")
