"""Trading Economics' public calendar pages: the source for every economic release (user rule,
2026-10-22: "when it comes to economic data always use trading economics"). Nasdaq stays only for the
earnings calendar.

Each country's page (tradingeconomics.com/<country>/calendar) is a server-rendered table: one row per
release with its UTC date and time and labelled actual / previous / consensus / forecast cells, from a
day or two back to about four weeks ahead. Code reads the cells directly, so no number is ever guessed.
A page shows times in UTC unless the visitor picks a zone; rows are turned into New York time here."""

from __future__ import annotations

import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx

from castelino.week_ahead.econ import DROP, INFLATION, kind_of, parse_num

URL = "https://tradingeconomics.com/{slug}/calendar"
SLUGS = {"US": "united-states", "CN": "china", "DE": "germany", "JP": "japan", "IN": "india"}
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    ),
    "Accept": "text/html",
}
ET = ZoneInfo("America/New_York")
MEASURE = re.compile(r"\s*\b(YoY|MoM|QoQ)\b")
MEASURES = {"YoY": "y/y", "MoM": "m/m", "QoQ": "q/q"}
_ROW = re.compile(r"<tr data-url=")
_DAY = re.compile(r"class=' (\d{4}-\d{2}-\d{2})'")
_TIME = re.compile(r'calendar-date-\d">\s*([^<]*?)\s*</span>')
_ISO = re.compile(r'class="calendar-iso">([A-Z]{2})<')
_EVENT = re.compile(r"class='calendar-event'[^>]*>([^<]+)</a>")
_CELL = {k: re.compile(rf"id='{k}'[^>]*>([^<]*)<") for k in ("actual", "previous", "consensus")}


def get_page(slug: str) -> str:
    r = httpx.get(URL.format(slug=slug), headers=HEADERS, timeout=30, follow_redirects=True)
    if r.status_code != 200:
        raise RuntimeError(f"tradingeconomics {slug}: HTTP {r.status_code}")
    if "challenge-platform" in r.text or "Just a moment" in r.text[:2000]:
        raise RuntimeError(f"tradingeconomics {slug}: blocked by a bot check")
    return r.text


def _num(s: str) -> tuple[float | None, str]:
    """'¥-536.6B' -> (-536.6, 'B'); '2.1%' -> (2.1, '%'); '' -> (None, '')."""
    return parse_num(re.sub(r"[^\d.,%KMBT()\-]", "", s.replace("&nbsp;", "")))


def _utc(day: str, hm: str) -> datetime | None:
    try:
        return datetime.strptime(f"{day} {hm}", "%Y-%m-%d %I:%M %p").replace(tzinfo=ZoneInfo("UTC"))
    except ValueError:
        return None  # no time ("", "All Day", "Tentative")


def parse(html: str) -> list[dict]:
    """A calendar page -> our five countries' releases, in the Week Ahead event shape."""
    out = []
    bounds = [m.start() for m in _ROW.finditer(html)] + [len(html)]
    for a, b in zip(bounds, bounds[1:], strict=False):  # bounds[1:] is one shorter by design
        block = html[a:b]
        day, iso, ev = _DAY.search(block), _ISO.search(block), _EVENT.search(block)
        if not (day and iso and ev) or iso[1] not in SLUGS:
            continue
        event = re.sub(r"\s+", " ", ev[1]).strip()
        if DROP.search(event):
            continue  # auctions
        vals = {k: _num(m[1]) if (m := rx.search(block)) else (None, "") for k, rx in _CELL.items()}
        tm = _TIME.search(block)
        when = _utc(day[1], tm[1].strip()) if tm else None
        if when is None and all(v is None for v, _ in vals.values()):
            continue  # a holiday
        m = MEASURE.search(event)
        name = MEASURE.sub("", event).strip()
        measure = MEASURES[m[1]] if m else None
        local = when.astimezone(ET) if when else None
        out.append(
            {
                "date": local.date().isoformat() if local else day[1],
                "time_et": f"{local:%H:%M}" if local else None,
                # a rate (YoY/MoM) of a price index is inflation; an index level is not
                "kind": "inflation" if measure and INFLATION.search(name) else kind_of(name),
                "country": iso[1],
                "name": name,
                "measure": measure,
                "consensus": vals["consensus"][0],
                "previous": vals["previous"][0],
                "actual": vals["actual"][0],
                "unit": vals["actual"][1] or vals["consensus"][1] or vals["previous"][1],
            }
        )
    return out


def country_events(cc: str, get=get_page) -> list[dict]:
    """Every release on one country's page (a day or two back to about four weeks ahead)."""
    return [e for e in parse(get(SLUGS[cc])) if e["country"] == cc]


def day_events(day: date, countries=None, get=get_page) -> list[dict]:
    """One New York day's releases, read fresh from the countries asked (all five by default)."""
    want = day.isoformat()
    return [e for cc in countries or SLUGS for e in country_events(cc, get) if e["date"] == want]
