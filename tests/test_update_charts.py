from castelino.agents.update import charts
from castelino.agents.update.models import Finding, Point, SeriesRef


def finding(fid, ref):
    return Finding(
        id=fid,
        agent="macro",
        claim="c",
        provenance="data",
        series=ref,
        source_title=f"FRED {ref.id}",
        source_url="u",
        fact_ids=["M1"],
    )


DAILY = SeriesRef(kind="daily", provider="fred", id="DGS10", label="10-year Treasury yield")
REL = SeriesRef(
    kind="release",
    provider="fred",
    id="CPIAUCSL",
    label="CPI y/y",
    points=[Point(label="Jul 2026 data", value=3.54), Point(label="Aug 2026 data", value=3.71)],
)
SEVEN = [(f"Oct 0{i}", 5.24 + i / 100) for i in range(7)]


def test_exhibits_numbered_in_order_and_failures_dropped(tmp_path):
    def fetch(ref):
        if ref.id == "BAD":
            raise RuntimeError("down")
        return SEVEN

    bad = SeriesRef(kind="daily", provider="yahoo", id="BAD", label="bad")
    short = SeriesRef(
        kind="release", provider="bls", id="S", label="s", points=[Point(label="a", value=1)]
    )
    out = charts.make_exhibits(
        [
            finding("macro-1", DAILY),
            finding("macro-2", bad),
            finding("macro-3", short),
            finding("macro-4", REL),
        ],
        tmp_path,
        fetch=fetch,
    )
    assert [(e.n, e.finding_id, e.file) for e in out] == [
        (1, "macro-1", "exhibit_1.png"),
        (2, "macro-4", "exhibit_2.png"),
    ]
    assert (tmp_path / "exhibit_1.png").stat().st_size > 10_000
    assert out[0].title == "Exhibit 1: 10-year Treasury yield, last 7 observations"
    assert out[1].title == "Exhibit 2: CPI y/y"


def test_subtitles_follow_units():
    assert charts.subtitle(REL, [(p.label, p.value) for p in REL.points]) == (
        "+0.17pp vs previous release"
    )
    assert charts.subtitle(DAILY, [("a", 5.24), ("b", 5.27)]) == "+3bp over the window"
    poly = SeriesRef(kind="daily", provider="polymarket", id="t", label="q")
    assert charts.subtitle(poly, [("a", 58.0), ("b", 41.0)]) == "-17.0pp over the window"
    spy = SeriesRef(kind="daily", provider="yahoo", id="SPY", label="SPY")
    assert charts.subtitle(spy, [("a", 100.0), ("b", 102.3)]) == "+2.3% over the window"


def test_footer_credits_arc_research():
    assert charts.footer_lines(finding("macro-1", DAILY)) == (
        "Source: ARC Research",
        "Data: FRED DGS10.",
    )
