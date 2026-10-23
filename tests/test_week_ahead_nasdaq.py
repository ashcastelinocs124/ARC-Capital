"""Nasdaq is read only for the earnings calendar, on the date asked."""

from datetime import date

from castelino.week_ahead import nasdaq


def test_the_earnings_calendar_is_read_for_the_date_asked(monkeypatch):
    asked = []

    class R:
        status_code = 200

        def json(self):
            return {"data": {"rows": [{"symbol": "PG"}]}}

    def get(url, params, headers, timeout):
        asked.append((url, params["date"]))
        return R()

    monkeypatch.setattr(nasdaq.httpx, "get", get)
    assert nasdaq.fetch_day("earnings", date(2026, 10, 22)) == [{"symbol": "PG"}]
    assert asked == [("https://api.nasdaq.com/api/calendar/earnings", "2026-10-22")]
