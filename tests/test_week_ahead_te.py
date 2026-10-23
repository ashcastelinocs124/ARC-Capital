from datetime import date

import pytest

from castelino.week_ahead import te


def row(day, time, iso, event, ref="SEP", actual="", previous="", consensus="", forecast=""):
    """One calendar row exactly as Trading Economics serves it (copied from its Japan page,
    2026-10-22), including the flag's nested table."""
    return f"""<tr data-url="/x/y" data-id="401960" data-country="x" data-category="y" data-event="{event.lower()}" data-symbol='S'>
                <td style="white-space: nowrap;" class=' {day}'>
                    <span class="event-8 calendar-date-2">
                        {time}
                    </span>
                </td>
                <td class="calendar-item" style="white-space: nowrap">
                    <table style="padding: 0px;"><tr>
                        <td style="padding-left: 5px;"><div title="X" class='flag flag-jp'></div></td>
                        <td title="X" style="padding-left: 5px;" class="calendar-iso">{iso}</td>
                    </tr></table>
                </td>
                <td style="max-width: 250px; overflow-x: hidden;">
                    <a class='calendar-event' href='/x/y'>{event}</a> <span class="calendar-reference">{ref}</span>
                </td>
                <td class="calendar-item calendar-item-positive">
                    <a href='/x/y'><span id='actual'>{actual}</span></a>
                </td>
                <td class="calendar-item calendar-item-positive">
                    <span id='previous'>{previous}</span>
                    <span id='revised' style="cursor: pointer;" title=></span>
                </td>
                <td class="calendar-item calendar-item-positive">
                    <a id='consensus' aria-label='S' href='/x/y'>{consensus}</a></span>
                </td>
                <td class="calendar-item calendar-item-positive">
                    <a id='forecast' href='/x/y'>{forecast}</a></span>
                </td>
            </tr>"""


def page(*rows):
    return "<html><table id='calendar'>" + "".join(rows) + "</table></html>"


JAPAN = page(
    row("2026-10-22", "11:30 PM", "JP", "Core Inflation Rate YoY", actual="2.1%", previous="1.7%", consensus="2.1%", forecast="2.0%"),
    row("2026-10-22", "11:50 PM", "JP", "Balance of Trade", actual="¥-536.6B", previous="¥-181.0B"),
    row("2026-10-23", "", "JP", "Sports Day", ref=""),  # a holiday: no time, no numbers
    row("2026-10-23", "3:35 AM", "JP", "5-Year JGB Auction", actual="1.02%"),
    row("2026-10-23", "1:00 AM", "GB", "Retail Sales MoM", actual="0.4%"),  # not one of ours
)  # fmt: skip


def test_parse_reads_a_row_in_new_york_time():
    core = te.parse(JAPAN)[0]
    assert core == {
        "date": "2026-10-22",
        "time_et": "19:30",
        "kind": "inflation",
        "country": "JP",
        "name": "Core Inflation Rate",
        "measure": "y/y",
        "consensus": 2.1,
        "previous": 1.7,
        "actual": 2.1,
        "unit": "%",
    }


def test_parse_keeps_currency_values_and_drops_holidays_auctions_and_other_countries():
    evs = te.parse(JAPAN)
    assert [e["name"] for e in evs] == ["Core Inflation Rate", "Balance of Trade"]
    trade = evs[1]
    assert (trade["actual"], trade["previous"], trade["unit"], trade["measure"]) == (
        -536.6,
        -181.0,
        "B",
        None,
    )


def test_a_page_without_rows_parses_to_nothing():
    assert te.parse("<html>new layout</html>") == []


def test_a_utc_time_after_midnight_is_the_previous_new_york_day():
    (e,) = te.parse(
        page(
            row(
                "2026-10-23",
                "12:30 AM",
                "US",
                "Initial Jobless Claims",
                actual="194K",
                consensus="200K",
            )
        )
    )
    assert (e["date"], e["time_et"], e["kind"], e["actual"], e["unit"]) == (
        "2026-10-22",
        "20:30",
        "jobs",
        194.0,
        "K",
    )


def test_rates_count_as_inflation_but_index_levels_do_not():
    evs = te.parse(page(
        row("2026-10-30", "12:30 PM", "US", "Core PCE Price Index MoM", consensus="0.2%"),
        row("2026-10-30", "12:30 PM", "US", "PCE Price Index", previous="128.1"),
    ))  # fmt: skip
    assert [e["kind"] for e in evs] == ["inflation", "other"]


def test_day_events_reads_only_the_countries_asked(monkeypatch):
    asked = []

    def get(slug):
        asked.append(slug)
        return JAPAN

    evs = te.day_events(date(2026, 10, 22), countries={"JP"}, get=get)
    assert asked == ["japan"] and [e["name"] for e in evs] == [
        "Core Inflation Rate",
        "Balance of Trade",
    ]


def test_get_page_refuses_a_bot_wall(monkeypatch):
    class R:
        status_code = 200
        text = "<title>Just a moment...</title><div id='challenge-platform'>"

    monkeypatch.setattr(te.httpx, "get", lambda *a, **k: R())
    with pytest.raises(RuntimeError, match="blocked"):
        te.get_page("japan")
