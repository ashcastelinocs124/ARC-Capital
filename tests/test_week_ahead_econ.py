from datetime import date

import pytest

from castelino.week_ahead import econ
from tests.test_week_ahead_te import page, row

MONDAY = date(2026, 10, 19)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("5.40%", (5.4, "%")),
        ("195K", (195.0, "K")),
        ("3,270.0B", (3270.0, "B")),
        ("-1.7%", (-1.7, "%")),
        ("($0.09)", (-0.09, "")),
        ("$880,976,070,000", (880976070000.0, "")),
        ("&nbsp;", (None, "")),
        (" ", (None, "")),
        ("N/A", (None, "")),
        (None, (None, "")),
    ],
)
def test_parse_num(raw, expected):
    assert econ.parse_num(raw) == expected


def test_kinds():
    assert econ.kind_of("Core Inflation Rate") == "inflation"
    assert econ.kind_of("Non Farm Payrolls") == "jobs"
    assert econ.kind_of("Existing Home Sales") == "other"
    assert econ.kind_of("Core CPI Index") == "other"  # an index level isn't the headline


PAGES = {
    "japan": page(
        row("2026-10-21", "11:50 PM", "JP", "Balance of Trade", actual="¥-536.6B"),  # Wed 19:50 ET
        row(
            "2026-10-22",
            "11:30 PM",
            "JP",
            "Core Inflation Rate YoY",
            actual="2.1%",
            consensus="2.1%",
        ),
        row("2026-10-27", "11:30 PM", "JP", "Unemployment Rate", consensus="2.5%"),  # next week
    ),
    "united-states": page(
        row(
            "2026-10-22",
            "12:30 PM",
            "US",
            "Initial Jobless Claims",
            actual="194K",
            consensus="200K",
        ),
    ),
}


def ev(cc, day, name):
    return {"date": day, "time_et": "09:00", "kind": "other", "country": cc, "name": name,
            "measure": None, "consensus": None, "previous": None, "actual": None, "unit": ""}  # fmt: skip


def get(slug):
    if slug not in PAGES:
        raise RuntimeError(f"tradingeconomics {slug}: HTTP 403")
    return PAGES[slug]


def test_fetch_week_reads_trading_economics_for_the_week_only():
    evs = econ.fetch_week(MONDAY, get=get)
    assert [(e["country"], e["date"], e["name"]) for e in evs] == [
        ("US", "2026-10-22", "Initial Jobless Claims"),
        ("JP", "2026-10-21", "Balance of Trade"),
        ("JP", "2026-10-22", "Core Inflation Rate"),
    ]


def test_fetch_week_keeps_earlier_days_the_page_no_longer_shows():
    prior = [ev("JP", "2026-10-19", "Tertiary Industry Index"), ev("JP", "2026-10-21", "old row"),
             ev("US", "2026-10-20", "Housing Starts")]  # fmt: skip
    evs = econ.fetch_week(MONDAY, prior=prior, get=get)
    names = [e["name"] for e in evs]
    assert (
        "Tertiary Industry Index" in names and "Housing Starts" in names
    )  # before each page's start
    assert "old row" not in names  # a day the page covers is read fresh


def test_fetch_week_keeps_a_failed_countrys_last_rows():
    evs = econ.fetch_week(MONDAY, prior=[ev("DE", "2026-10-20", "ZEW Economic Sentiment")], get=get)
    assert ("DE", "ZEW Economic Sentiment") in [(e["country"], e["name"]) for e in evs]


def test_a_page_with_no_rows_counts_as_failed():
    # Trading Economics changed its layout: the page loads but no row parses
    with pytest.raises(RuntimeError, match="no releases"):
        econ.fetch_week(MONDAY, get=lambda slug: "<html>new layout</html>")


def test_fetch_week_raises_when_every_page_fails():
    with pytest.raises(RuntimeError, match="no releases"):
        econ.fetch_week(MONDAY, get=lambda slug: (_ for _ in ()).throw(RuntimeError("down")))
