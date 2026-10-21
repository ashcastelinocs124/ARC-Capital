from datetime import date

from castelino.agents.update import calendar
from castelino.agents.update.models import Fact, Finding
from castelino.substack import build_doc

ECON = [
    {"country": "United States", "eventName": "Housing Starts", "gmt": "08:30", "actual": "1.221M", "consensus": "1.305M", "previous": "1.307M"},
    {"country": "United States", "eventName": "NAHB Housing Market Index", "gmt": "10:00", "actual": "", "consensus": "31", "previous": "32"},
    {"country": "Germany", "eventName": "Buba Monthly Report", "gmt": "06:00", "actual": "", "consensus": "", "previous": ""},
    {"country": "Japan", "eventName": "National Core CPI (YoY)", "gmt": "19:30", "actual": "2.9%", "consensus": "2.8%", "previous": "2.7%"},
]  # fmt: skip
EARN = [
    {"symbol": "NFLX", "marketCap": "$290,851,193,000", "time": "time-after-hours", "epsForecast": "$0.82"},
    {"symbol": "GE", "marketCap": "$322,972,451,000", "time": "time-pre-market", "epsForecast": "$2.02"},
    {"symbol": "ZZZZ", "marketCap": "$1,000", "epsForecast": "$1.00"},  # not in the calendar's universe
]  # fmt: skip
UNIVERSE = {
    "NFLX": ("Netflix", "sp500"),
    "GE": ("GE Aerospace", "sp500"),
    "SPCX": ("SpaceX", "ai_extra"),
}
KW = {  # Yahoo: GE's result is in, Netflix's not yet; SpaceX is off Nasdaq's calendar but on Yahoo's
    "eps": lambda t, day: {"GE": (2.25, 2.02, 11.4), "SPCX": (0.31, 0.13, 138.5)}.get(t),
    "yf_date": lambda t: (date(2026, 10, 20), 0.13302),
}


def fetch(kind, day):
    return ECON if kind == "economicevents" else EARN


def test_the_days_calendar_becomes_lines_facts_and_findings_once():
    old = Finding(id="news-1", agent="news", claim="x", provenance="reported", source_title="t", source_url="u", fact_ids=["N1"])  # fmt: skip
    f1, x1, lines = calendar.add([old], [], "2026-10-20", fetch, UNIVERSE, **KW)
    assert lines == [
        "08:30 ET · US Housing Starts: 1.221M vs 1.305M expected (previous 1.307M)",
        "10:00 ET · US NAHB Housing Market Index: 31 expected (previous 32)",  # not out yet
        "19:30 ET · Japan National Core CPI (YoY): 2.9% vs 2.8% expected (previous 2.7%)",
        "SpaceX (SPCX) EPS: $0.31 vs $0.13 expected, a 138.5% beat",  # AI names first
        "GE Aerospace (GE) EPS: $2.25 vs $2.02 expected, an 11.4% beat",  # then by market value
        "Netflix (NFLX) reported after the close; EPS estimate $0.82",  # Yahoo hasn't got it yet
    ]  # the Buba report (other news abroad) and the off-list ZZZZ are left out
    assert [f.id for f in x1] == ["cal1", "cal2", "cal3", "cal4"]  # only results that are out
    assert x1[0].numbers == [1.221, 1.305, 1.307] and x1[3].numbers == [2.25, 2.02, 11.4]
    assert [(f.id, f.agent) for f in f1] == [("news-1", "news"), ("cal-1", "macro"), ("cal-2", "macro"), ("cal-3", "news"), ("cal-4", "news")]  # fmt: skip
    assert f1[1].claim.startswith("On today's calendar: 08:30 ET") and f1[1].fact_ids == ["cal1"]

    keep = Fact(
        id="N1", text="n", numbers=[], provenance="reported", source_title="t", source_url="u"
    )
    f2, x2, _ = calendar.add(f1, [keep, *x1], "2026-10-20", fetch, UNIVERSE, **KW)  # a desk rebuild
    assert [f.id for f in f2] == [f.id for f in f1] and [f.id for f in x2] == [
        "N1",
        "cal1",
        "cal2",
        "cal3",
        "cal4",
    ]


def test_the_substack_draft_lists_the_calendar_under_the_items():
    note = {"headline": "h", "takeaways": ["a", "b", "c"], "items": []}
    doc = build_doc({"date": "2026-10-20", "note": note, "calendar": ["Netflix (NFLX) reports after the close"]}, {})  # fmt: skip
    i = next(i for i, c in enumerate(doc["content"]) if c["type"] == "heading" and c["content"][0]["text"] == "On the calendar today")  # fmt: skip
    assert doc["content"][i + 1]["content"][0]["content"][0]["content"][0]["text"] == "Netflix (NFLX) reports after the close"  # fmt: skip
    assert "On the calendar today" not in str(build_doc({"date": "2026-10-20", "note": note}, {}))
