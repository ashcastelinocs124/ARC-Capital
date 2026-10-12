import json
from datetime import date
from pathlib import Path

import pytest

from castelino.week_ahead import econ

FIX = Path(__file__).parent / "fixtures" / "week_ahead"


def rows(day: str) -> list[dict]:
    return (json.loads((FIX / f"econ-{day}.json").read_text()).get("data") or {}).get("rows") or []


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


def test_keeps_only_five_countries_and_drops_auctions():
    evs = econ.events_for_day(rows("2026-10-14"), date(2026, 10, 14))
    assert {e["country"] for e in evs} <= {"US", "CN", "DE", "JP", "IN"}
    assert not [e for e in evs if "Auction" in e["name"]]


def test_tiers_and_german_prefix():
    evs = econ.events_for_day(rows("2026-10-14"), date(2026, 10, 14))
    de = [e for e in evs if e["country"] == "DE" and e["kind"] == "inflation"]
    assert {e["name"] for e in de} >= {"CPI", "HICP"}
    adp = [e for e in evs if e["name"].startswith("ADP")]
    assert adp and adp[0]["kind"] == "jobs"
    assert [e for e in evs if e["name"] == "Existing Home Sales"][0]["kind"] == "other"


def test_index_levels_are_not_tier1():
    evs = econ.events_for_day(rows("2026-10-15"), date(2026, 10, 15))
    lvl = [e for e in evs if e["name"] == "Core CPI Index"]
    assert lvl and lvl[0]["kind"] == "other"


def test_pairs_labelled_in_either_order():
    us = econ.events_for_day(rows("2026-10-15"), date(2026, 10, 15))
    cpi = {e["measure"]: e for e in us if e["country"] == "US" and e["name"] == "CPI"}
    assert cpi["y/y"]["consensus"] == 3.6 and cpi["m/m"]["consensus"] == 0.6  # m/m row comes first
    cn = econ.events_for_day(rows("2026-10-14"), date(2026, 10, 14))
    ccpi = {e["measure"]: e for e in cn if e["country"] == "CN" and e["name"] == "CPI"}
    assert ccpi["y/y"]["consensus"] == 1.0 and ccpi["m/m"]["previous"] == 0.4  # y/y row comes first


def test_time_and_units():
    evs = econ.events_for_day(rows("2026-10-13"), date(2026, 10, 13))
    ind = [e for e in evs if e["country"] == "IN" and e["name"] == "CPI"][0]
    assert ind["time_et"] == "06:30" and ind["unit"] == "%" and ind["previous"] == 4.82
    assert ind["date"] == "2026-10-13"


def test_fetch_week_handles_empty_day():
    calls = []

    def fetch(kind, day):
        calls.append((kind, day))
        return [] if day == date(2026, 10, 12) else rows(day.isoformat())

    evs = econ.fetch_week(date(2026, 10, 12), fetch=fetch)
    assert len(calls) == 5 and all(k == "economicevents" for k, _ in calls)
    assert evs and not [e for e in evs if e["date"] == "2026-10-12"]


def test_fetch_week_raises_when_whole_week_is_empty():
    # five empty days across five economies never happens: Nasdaq changed its reply
    with pytest.raises(RuntimeError, match="no releases"):
        econ.fetch_week(date(2026, 10, 12), fetch=lambda kind, day: [])
