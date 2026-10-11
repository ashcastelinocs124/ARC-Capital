from castelino.agents.update import charts as uc
from castelino.agents.update.models import SeriesRef
from castelino.agents.weekly.charts import make_weekly_exhibits, window_label
from castelino.agents.weekly.models import WeeklyReport
from tests.weekly_fixtures import fact, line, pick, trend


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
    return trend(
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
            sec([line("A1", 90)]),
            sec(
                [
                    line("NOPE", 30),
                    line("A1", 365),
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


def test_polymarket_exhibit_is_labelled_last_7_days(tmp_path):
    from castelino.agents.update.models import Fact

    pm = Fact(
        id="A2",
        text="odds",
        numbers=[62],
        provenance="data",
        series=SeriesRef(kind="daily", provider="polymarket", id="tok", label="Dec cut odds"),
        source_title="Polymarket",
        source_url="u",
    )
    rep = WeeklyReport(
        title="T",
        subtitle="S",
        bullets=[],
        watch="W",
        sections=[
            trend(
                title="t",
                agent="a",
                paragraphs=["p"],
                fact_ids=["A2"],
                exhibits=[line("A2", 90)],
                challenges=[],
            )
        ],
    )
    out = make_weekly_exhibits(rep, [pm], tmp_path, fetch=lambda r, w: [("a", 60.0), ("b", 62.0)])
    assert out[0].title.endswith("· last 7 days")


def facts_for_bars():
    from tests.weekly_fixtures import fact as f

    return [
        f("A1", nums=(0.4,), chart=False, text="Prof services AHE +0.4%"),
        f("A2", nums=(0.3,), chart=False, text="Financial AHE +0.3%"),
        f("A3", nums=(-0.2,), chart=False, text="Leisure AHE -0.2%"),
    ]


def one_section_report(exhibits, ids):
    return WeeklyReport(
        title="T",
        subtitle="S",
        bullets=[],
        watch="W",
        sections=[trend(fact_ids=ids, exhibits=exhibits)],
    )


def test_bar_forms_render_from_fact_numbers(tmp_path):
    pts = [("A1", "Prof. services", 0.4), ("A2", "Financial", 0.3), ("A3", "Leisure", -0.2)]
    exhibits = [
        pick(
            "breakdown", ["A1", "A2", "A3"], points=pts, unit="%", title="Hourly earnings by sector"
        ),
        pick("movers", ["A1", "A2", "A3"], points=pts, unit="%", title="Week's moves"),
        pick("dumbbell", ["A1", "A2"], points=pts[:2], unit="%", title="Before and after"),
    ]
    out = make_weekly_exhibits(
        one_section_report(exhibits, ["A1", "A2", "A3"]), facts_for_bars(), tmp_path
    )
    assert [e.kind for e in out] == ["breakdown", "movers", "dumbbell"]
    assert out[0].title == "Exhibit 1: Hourly earnings by sector"
    assert all((tmp_path / e.file).stat().st_size > 1000 for e in out)


def test_compare_rebases_price_series_and_keeps_rate_levels(tmp_path):
    import pandas as pd

    from castelino.agents.weekly import charts as wc
    from tests.weekly_fixtures import fact as f

    def series(ref, window_days):
        idx = pd.bdate_range(end="2026-10-09", periods=30)
        base = {"^SOX": 100.0, "^GSPC": 50.0, "DGS10": 4.0, "DGS2": 3.5}[ref.id]
        return pd.Series([base * (1 + i / 100) for i in range(30)], index=idx)

    sox = f("A1")
    sox.series.provider = "yahoo"
    sox.series.id = "^SOX"
    spx = f("A2")
    spx.series.provider = "yahoo"
    spx.series.id = "^GSPC"
    rebased = wc.compare_frame([sox, spx], 90, series)
    assert abs(rebased.iloc[0, 0] - 100) < 1e-9 and abs(rebased.iloc[0, 1] - 100) < 1e-9
    d10, d2 = f("B1"), f("B2")
    d2.series.id = "DGS2"
    levels = wc.compare_frame([d10, d2], 90, series)
    assert abs(levels.iloc[0, 0] - 4.0) < 1e-9  # yields stay in % levels
    out = make_weekly_exhibits(
        one_section_report([pick("compare", ["A1", "A2"], title="Chips vs market")], ["A1", "A2"]),
        [sox, spx],
        tmp_path,
        series=series,
    )
    assert out[0].kind == "compare" and (tmp_path / out[0].file).exists()


def test_a_form_its_facts_cannot_support_is_dropped(tmp_path):
    bad = pick("compare", ["A1"])  # one series
    out = make_weekly_exhibits(one_section_report([bad], ["A1"]), facts_for_bars(), tmp_path)
    assert out == []
