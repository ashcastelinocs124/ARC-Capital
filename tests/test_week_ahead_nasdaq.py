"""Nasdaq's economicevents?date=D answered with D-1's releases in October 2026 (Thursday's jobless
claims came back for Friday's date), so fetch_day finds the shift from the claims and asks for the right
date. The earnings calendar was never shifted."""

from datetime import date

import pytest

from castelino.week_ahead import nasdaq

CLAIMS = [{"eventName": "Initial Jobless Claims", "country": "United States"}]
MBA = [{"eventName": "MBA Mortgage Applications", "country": "United States"}]


def calendar(shift: int) -> dict[str, list[dict]]:
    """Wednesday Oct 21 and Thursday Oct 22, 2026, filed `shift` days late."""
    days = {date(2026, 10, 21): MBA, date(2026, 10, 22): CLAIMS}
    return {date.fromordinal(d.toordinal() + shift): rows for d, rows in days.items()}


@pytest.fixture
def nasdaq_api(monkeypatch):
    asked = []

    def use(shift: int, today=date(2026, 10, 23)):
        cal = calendar(shift)

        def rows(kind, day):
            asked.append((kind, day))
            return cal.get(day, []) if kind == "economicevents" else [{"symbol": f"E{day.day}"}]

        monkeypatch.setattr(nasdaq, "_rows", rows)
        monkeypatch.setattr(nasdaq, "_today", lambda: today)
        nasdaq.econ_shift.cache_clear()
        return asked

    return use


def test_a_calendar_filed_a_day_late_is_read_from_the_next_date(nasdaq_api):
    nasdaq_api(1)
    assert nasdaq.econ_shift() == 1
    assert nasdaq.fetch_day("economicevents", date(2026, 10, 22)) == CLAIMS
    assert nasdaq.fetch_day("economicevents", date(2026, 10, 21)) == MBA


def test_a_calendar_on_its_own_date_is_read_as_is(nasdaq_api):
    nasdaq_api(0)
    assert nasdaq.fetch_day("economicevents", date(2026, 10, 22)) == CLAIMS


def test_the_earnings_calendar_is_never_shifted(nasdaq_api):
    asked = nasdaq_api(1)
    assert nasdaq.fetch_day("earnings", date(2026, 10, 22)) == [{"symbol": "E22"}]
    assert ("economicevents", date(2026, 10, 22)) not in asked


def test_no_claims_in_reach_reads_dates_as_given(nasdaq_api):
    nasdaq_api(5)
    assert nasdaq.econ_shift() == 0
