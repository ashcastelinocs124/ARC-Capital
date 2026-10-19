"""X Scout calendar posts: the week on Monday, today's calendar Tuesday to Friday, each release as it lands.

`card` (07:00 ET on weekdays): code reads Week Ahead's data/week_ahead.json, picks the key rows (US
releases by TIERS with a consensus, inflation and jobs abroad, the largest companies reporting),
draws the card in the ARC chart frame and saves the day's watch list: today's MAX_RELEASES most
important rows still to come (watch_rows: top-tier US data, then the largest companies), marked WATCH.
The Card Writer adds a short read whose figures must be the card's (x_scout.check); one retry, then a
code-written line. Monday's card is the whole week's and also sets Monday's watch list.
`watch` (every 5 minutes, 07:00-19:55 ET on weekdays): code fetches today's Nasdaq calendar and posts
each watched row whose actual (data) or EPS (earnings) has appeared, once, at most MAX_RELEASES a day:
a code-written numbers line, then one Release Writer sentence that may hold no digit (else it's
dropped and the numbers line posts alone). Release posts skip the Theme Charts quiet hour: they are
news. X only; dry run (log only) unless X_SCOUT_LIVE=1 and the X write keys are set.
Each day: data/x_posts/calendar/<YYYY-MM-DD>.json (card, watch list, releases) and <YYYY-MM-DD>/card.png.
Run by deploy/crontab: python -m castelino.x_calendar card|watch [--dry-run]
"""

from __future__ import annotations

import json
import os
import re
import sys
import textwrap
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from castelino import x_post, x_scout
from castelino.agents.base import StructuredAgent
from castelino.agents.update.fsio import atomic_write_text
from castelino.config import get_settings
from castelino.week_ahead import econ, nasdaq
from castelino.week_ahead.econ import parse_num

ET = ZoneInfo("America/New_York")
MAX_RELEASES = 4
TIERS = [  # US releases by importance; a release outside every tier never makes the card
    re.compile(
        r"^(Core )?(CPI|PCE Price Index)\b|Nonfarm Payrolls|Unemployment Rate|Fed Interest Rate Decision|^GDP",
        re.I,
    ),  # fmt: skip
    re.compile(
        r"^(Core )?(PPI|Retail Sales)\b|\bISM\b|JOLTS|^Initial Jobless Claims|Average Hourly Earnings",
        re.I,
    ),  # fmt: skip
    re.compile(
        r"Housing Starts|Building Permits|Home Sales|Durable Goods|Consumer Confidence|Michigan|NAHB|Industrial Production",
        re.I,
    ),  # fmt: skip
]
ABROAD = 1.5  # inflation and jobs abroad rank between the US second and third tiers
COUNTRY = {"CN": ("China", "Chinese"), "DE": ("Germany", "German"), "JP": ("Japan", "Japanese"), "IN": ("India", "Indian")}  # fmt: skip
TAG = {"week": "🗓️ WEEK AHEAD · ", "day": "📅 TODAY · "}
FALLBACK = {
    "week": TAG["week"] + "The data and earnings that matter this week, by day.",
    "day": TAG["day"] + "What's out today and when.",
}
SESSION = {"pre": ("Pre-open", "06:00"), "post": ("After close", "16:05")}  # label, sort time
CHARS = 95  # characters a full-width card line holds at 8 pt
WATCH_COLOR = "#C2410C"

CARD = """You write the short read on top of ARC Research's calendar card on X: the week ahead, or
today. In one or two plain sentences, at most 220 characters, say what matters on the card and why a
macro investor should care. Use only figures that are on the card, written exactly as shown, and no
others; times are fine. Put each figure in a plain sentence that names its release ("housing starts
are seen at 1.3M"), never the card's "·" shorthand. Name companies as the card does. No advice,
hashtags, emoji or links."""

RELEASE = """You add one plain sentence, at most 150 characters, under an ARC Research post on X that
reports an economic release or an earnings result. Say what it means for markets or the economy. Use
no number or digit at all: the line above already gives them. No advice, hashtags or emoji."""


class CardRead(BaseModel):  # LLM output (closed schema: no defaults)
    text: str


class ReleaseRead(BaseModel):  # LLM output (closed schema: no defaults)
    sentence: str


class CardWriter(StructuredAgent[CardRead]):
    name = "x_calendar_writer"
    output_schema = CardRead
    tier = "fast"

    def __init__(self) -> None:
        self.model = get_settings().x_scout.writer_model

    def system_prompt(self) -> str:
        return CARD

    def user_prompt(self, *, kind: str, title: str, card: str, fix: list[str] | None = None) -> str:
        out = f"The {kind} card: {title}\n{card}"
        if fix:
            out += "\n\nYour last read had problems. Fix them:\n" + "\n".join(f"- {e}" for e in fix)
        return out


class ReleaseWriter(StructuredAgent[ReleaseRead]):
    name = "x_release_writer"
    output_schema = ReleaseRead
    tier = "fast"

    def __init__(self) -> None:
        self.model = get_settings().x_scout.writer_model

    def system_prompt(self) -> str:
        return RELEASE

    def user_prompt(self, *, release: str) -> str:
        return f"The post: {release}"


# ── picking and drawing ─────────────────────────────────────────────────────


def key(e: dict) -> str:
    """One row's identity in both the morning file and Nasdaq's live reply."""
    if e["kind"] == "earnings":
        return f"E|{e['ticker']}"
    return f"{e['country']}|{e['time_et']}|{e['name']}|{e['measure']}"


def _rank(e: dict) -> float | None:
    if e.get("consensus") is None:
        return None
    if e.get("country") != "US":
        return ABROAD if e["kind"] in ("inflation", "jobs") else None
    return next((float(i) for i, t in enumerate(TIERS) if t.search(e["name"])), None)


def pick(events: list[dict], day: str, data: int, earnings: int) -> list[dict]:
    """A day's card rows: its `data` most important releases, then its `earnings` largest reporters."""
    rows = [e for e in events if e["date"] == day]
    econ_rows = [e for e in rows if e["kind"] != "earnings" and _rank(e) is not None]
    econ_rows = sorted(econ_rows, key=lambda e: (_rank(e), e.get("time_et") or ""))[:data]
    earn = [e for e in rows if e["kind"] == "earnings"]
    earn = sorted(earn, key=lambda e: -(e.get("market_cap") or 0))[:earnings]
    return econ_rows + earn


def fmt(v: float | None, unit: str = "") -> str:
    return "" if v is None else f"{v:g}{unit}"


def label(e: dict) -> str:
    """'US Housing Starts', 'Japan National Core CPI'; no prefix when the name already says it."""
    where = "US" if e["country"] == "US" else COUNTRY.get(e["country"], (e["country"],) * 2)[0]
    if e["name"].startswith((where, *COUNTRY.get(e["country"], ()))):
        where = ""
    return " ".join(x for x in (where, e["name"], e.get("measure")) if x)


def company(e: dict) -> str:
    """The universe's name without a trailing '(The)': 'Travelers Companies (The)' -> 'Travelers Companies'."""
    return re.sub(r"\s*\(The\)$", "", e["company"])


def upcoming(events: list[dict], now: datetime) -> list[dict]:
    """Drops today's releases already out by `now` (their consensus is old news)."""
    day, hm = f"{now:%Y-%m-%d}", f"{now:%H:%M}"
    return [e for e in events if not (e["date"] == day and e["kind"] != "earnings" and (e.get("time_et") or "24:00") < hm)]  # fmt: skip


def group(e: dict) -> str:
    """A release's m/m and y/y share one group: one watch slot, one post."""
    return (
        f"E|{e['ticker']}"
        if e["kind"] == "earnings"
        else f"{e['country']}|{e['time_et']}|{e['name']}"
    )


def watch_rows(rows: list[dict]) -> list[dict]:
    """The rows release posts follow: top-tier US data (CPI, payrolls, PPI ...), then the largest
    companies, then the rest; MAX_RELEASES groups, so the cap never crowds out the big names."""

    def prio(e: dict) -> tuple[int, float]:
        if e["kind"] == "earnings":
            return 1, -(e.get("market_cap") or 0)
        r = _rank(e)
        return (0 if r is not None and r <= 1 else 2), r or 0.0

    groups: dict[str, list[dict]] = {}
    for e in rows:
        groups.setdefault(group(e), []).append(e)
    best = sorted(groups.values(), key=lambda g: min(prio(e) for e in g))[:MAX_RELEASES]
    return [e for g in best for e in g]


def _time(e: dict) -> tuple[str, str]:
    """(shown, sort key) for a row."""
    if e["kind"] == "earnings":
        return SESSION.get(e.get("session") or "", ("During day", "12:00"))
    t = e.get("time_et") or ""
    return t.lstrip("0") if t[:1] == "0" else t, t or "12:00"


def _wrap(s: str, width: float) -> str:
    return "\n".join(textwrap.fill(line, int(width * CHARS)) for line in s.split("\n"))


def day_table(rows: list[dict], watched: set[str] = frozenset()) -> tuple[list[str], list[list[str]], list[float]]:  # fmt: skip
    widths = [0.15, 0.48, 0.26, 0.11]
    cells = []
    for e in sorted(rows, key=lambda e: _time(e)[1]):
        if e["kind"] == "earnings":
            what = f"{company(e)} ({e['ticker']})"
            exp = f"EPS {fmt(e.get('eps_est'))}" if e.get("eps_est") is not None else ""
        else:
            what = label(e).removeprefix("US ")
            u = e.get("unit") or ""
            exp = fmt(e["consensus"], u) + (f" · prev {fmt(e['previous'], u)}" if e.get("previous") is not None else "")  # fmt: skip
        cells.append(
            [_time(e)[0], _wrap(what, widths[1]), exp, "WATCH" if key(e) in watched else ""]
        )
    return ["Time", "Release or company", "Expected", ""], cells, widths


def week_table(by_day: dict[str, list[dict]]) -> tuple[list[str], list[list[str]], list[float]]:
    widths = [0.08, 0.54, 0.38]
    cells = []
    for day, rows in by_day.items():
        data = []
        for e in [e for e in rows if e["kind"] != "earnings"]:
            u = e.get("unit") or ""
            prev = f" · prev {fmt(e['previous'], u)}" if e.get("previous") is not None else ""
            data.append(
                f"{_time(e)[0]} {label(e).removeprefix('US ')} · {fmt(e['consensus'], u)}{prev}"
            )
        groups: dict[str, list[str]] = {}
        for e in [e for e in rows if e["kind"] == "earnings"]:
            groups.setdefault({"pre": "Pre", "post": "After"}.get(e.get("session") or "", "Day"), []).append(e["ticker"])  # fmt: skip
        earn = " · ".join(f"{k}: {', '.join(v)}" for k, v in groups.items())
        cells.append([f"{date.fromisoformat(day):%a}", _wrap("\n".join(data) or "—", widths[1]), _wrap(earn or "—", widths[2])])  # fmt: skip
    return ["Day", "Data (ET) · consensus · previous", "Earnings"], cells, widths


def draw_card(title: str, sub: str, header: list[str], cells: list[list[str]], widths: list[float], kicker: str, path: Path) -> None:  # fmt: skip
    """The card as a table in the ARC chart frame (no "Exhibit" number)."""
    from castelino.agents.weekly import charts as wc

    xs = [sum(widths[:i]) for i in range(len(widths))]
    lines = [max(c.count("\n") + 1 for c in row) for row in cells]
    step = min(0.062, 0.94 / (1.6 + sum(lines) + 0.45 * len(cells)))  # one text line, in axes units

    def draw(ax):
        ax.axis("off")
        y = 1.0
        for x, h in zip(xs, header, strict=True):
            ax.text(x, y, h.upper(), fontsize=6.5, fontweight="bold", color=wc.INK2, va="top", transform=ax.transAxes)  # fmt: skip
        y -= step * 1.25
        ax.plot(
            [0, 1], [y + step * 0.2] * 2, color=wc.INK, lw=1, transform=ax.transAxes, clip_on=False
        )
        for row, n in zip(cells, lines, strict=True):
            y -= step * 0.2
            for i, (x, c) in enumerate(zip(xs, row, strict=True)):
                watch = c == "WATCH"  # the day card's flag on rows release posts will follow
                ax.text(x, y, c, fontsize=7 if watch else 8, fontweight="bold" if i == 0 or watch else "normal",
                        va="top", linespacing=1.3, color=WATCH_COLOR if watch else wc.INK, transform=ax.transAxes)  # fmt: skip
            y -= step * (n + 0.25)
            ax.plot([0, 1], [y + step * 0.1] * 2, color="#E5E5E8", lw=0.6, transform=ax.transAxes, clip_on=False)  # fmt: skip

    wc._frame(1, title, sub, "Nasdaq economic and earnings calendars", path, draw, left=0.06, bottom=0.11, kicker=kicker, numbered=False)  # fmt: skip


# ── records ────────────────────────────────────────────────────────────────


def _day_path(root: Path, now: datetime) -> Path:
    return root / "data" / "x_posts" / "calendar" / f"{now:%Y-%m-%d}.json"


def day_record(root: Path, now: datetime) -> dict:
    p = _day_path(root, now)
    return json.loads(p.read_text()) if p.exists() else {"watch": [], "releases": []}


def save_day(root: Path, now: datetime, rec: dict) -> None:
    p = _day_path(root, now)
    p.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(p, json.dumps(rec, indent=2, ensure_ascii=False))


def _live(dry: bool) -> bool:
    return not dry and os.getenv("X_SCOUT_LIVE") == "1" and x_post.can_post()


# ── the morning card ───────────────────────────────────────────────────────


def read(kind: str, title: str, card: str, nums: set[float]) -> str:
    """The Card Writer's read, tagged; one retry told what failed, then the code-written line."""
    fix = None
    for _ in range(2):
        try:
            text = TAG[kind] + CardWriter()(kind=kind, title=title, card=card, fix=fix).text.strip()
        except Exception as e:  # noqa: BLE001 - the card goes out with the fallback line
            print(f"  card read failed: {e}")
            break
        fix = x_scout.check(text, "", "", nums)
        if not fix:
            return text
        print("  check: " + "; ".join(fix))
    return FALLBACK[kind]


def card(now: datetime | None = None, root: Path | None = None, dry: bool = False) -> dict | None:
    """Monday: the week's card; Tuesday to Friday: today's. Returns the card record, or None."""
    now, root = now or datetime.now(ET), root or get_settings().root
    day = f"{now:%Y-%m-%d}"
    print(f"{now:%Y-%m-%d %H:%M} ET  card")
    rec = day_record(root, now)
    if rec.get("card"):
        print("  already posted today")
        return None
    try:
        week = json.loads((root / "data" / "week_ahead.json").read_text())
    except (OSError, ValueError) as e:
        print(f"  no Week Ahead calendar: {e}")
        return None
    start, end = week.get("week_start", ""), week.get("week_end", "")
    if not start <= day <= end:
        print(f"  Week Ahead holds {start}..{end}, not today")
        return None
    events = week["events"]
    if now.weekday() == 0:
        kind, s, e = "week", date.fromisoformat(start), date.fromisoformat(end)
        days = [f"{s + timedelta(days=i):%Y-%m-%d}" for i in range((e - s).days + 1)]
        by_day = {d: pick(events, d, data=2, earnings=6) for d in days}
        header, cells, widths = week_table(by_day)
        rows, today = (
            [r for d in days for r in by_day[d]],
            watch_rows(upcoming(by_day.get(day, []), now)),
        )
        title = f"The week of {s:%b} {s.day}–" + (
            f"{e.day}" if e.month == s.month else f"{e:%b} {e.day}"
        )
        sub = "Key releases and the largest companies reporting"
    else:
        kind = "day"
        rows = pick(upcoming(events, now), day, data=4, earnings=5)
        if not rows:
            print("  nothing on the calendar today")
            return None
        today = watch_rows(rows)
        header, cells, widths = day_table(rows, {key(r) for r in today})
        title, sub = f"{now:%A}, {now:%b} {now.day}", "What's out today (ET) · consensus · previous"
    png = _day_path(root, now).with_suffix("") / "card.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    draw_card(title, sub, header, cells, widths, "WEEK AHEAD" if kind == "week" else "TODAY", png)
    nums = {float(r[k]) for r in rows for k in ("consensus", "previous", "eps_est") if r.get(k) is not None}  # fmt: skip
    text = read(kind, title, "\n".join(" | ".join(c.replace("\n", "; ") for c in row) for row in cells), nums)  # fmt: skip
    live = _live(dry)
    post_id = x_post.post(text, media_id=x_post.upload_image(png.read_bytes())) if live else None
    rec["card"] = {
        "at": now.isoformat(timespec="minutes"),
        "kind": kind,
        "title": title,
        "text": text,
        "file": f"{png.parent.name}/{png.name}",
        "dry_run": not live,
        "id": post_id,
    }
    rec["watch"] = [{"key": key(r), **r} for r in today]
    rec.setdefault("releases", [])
    save_day(root, now, rec)
    print(f"  {kind} card: {len(cells)} rows, {len(today)} watched today → {rec['card']['file']}")
    print(
        ("  POSTED " + post_id if live else "  DRY RUN would post")
        + f" ({x_post.xlen(text)}/280) + card:"
    )
    print("    " + text)
    return rec["card"]


# ── the release watcher ────────────────────────────────────────────────────


def _money(v: float) -> str:
    return f"-${abs(v):.2f}" if v < 0 else f"${v:.2f}"


def _data_line(hits: list[tuple[dict, dict]]) -> str:
    """'🚨 US Core PPI: 0.7% m/m vs 0.3% expected (previous 0.2%); 5% y/y vs ...' for one release."""
    one = len(hits) == 1
    parts = []
    for w, e in hits:
        u = e.get("unit") or w.get("unit") or ""
        cons = e["consensus"] if e["consensus"] is not None else w.get("consensus")
        prev = e["previous"] if e["previous"] is not None else w.get("previous")
        p = fmt(e["actual"], u) + ("" if one or not w.get("measure") else f" {w['measure']}")
        p += f" vs {fmt(cons, u)} expected" if cons is not None else ""
        p += f" (previous {fmt(prev, u)})" if prev is not None else ""
        parts.append(p)
    head = label(hits[0][0] if one else {**hits[0][0], "measure": None})
    return f"🚨 {head}: " + "; ".join(parts) + "."


def landed(todo: list[dict], day: date) -> list[tuple[list[dict], str]]:
    """Watched releases whose number is out, in watch order: (their watch rows, the numbers line)."""
    out: list[tuple[list[dict], str]] = []
    if any(w["kind"] != "earnings" for w in todo):
        live = {
            key(e): e for e in econ.events_for_day(nasdaq.fetch_day("economicevents", day), day)
        }
        hits: dict[str, list[tuple[dict, dict]]] = {}
        for w in todo:
            e = live.get(w["key"]) if w["kind"] != "earnings" else None
            if e and e["actual"] is not None:
                hits.setdefault(group(w), []).append((w, e))
        out += [([w for w, _ in h], _data_line(h)) for h in hits.values()]
    if any(w["kind"] == "earnings" for w in todo):
        rows = {(r.get("symbol") or "").upper(): r for r in nasdaq.fetch_day("earnings", day)}
        for w in todo:
            r = rows.get(w["ticker"].upper()) if w["kind"] == "earnings" else None
            eps = parse_num(r.get("eps"))[0] if r else None
            if eps is None:
                continue
            est = parse_num(r.get("epsForecast"))[0]
            est = est if est is not None else w.get("eps_est")
            line = f"💼 {company(w)} EPS: {_money(eps)}" + (f" vs {_money(est)} expected" if est is not None else "")  # fmt: skip
            surprise = parse_num(r.get("surprise"))[0]
            if est is not None and surprise is not None:
                line += f", a {abs(surprise):g}% {'beat' if surprise >= 0 else 'miss'}"
            out.append(([w], line + "."))
    order = {w["key"]: i for i, w in enumerate(todo)}
    return sorted(out, key=lambda t: order[t[0][0]["key"]])


def explain(line: str) -> str | None:
    """The Release Writer's sentence, or None when it fails, runs long or holds a digit."""
    try:
        s = ReleaseWriter()(release=line).sentence.strip()
    except Exception as e:  # noqa: BLE001 - the news never waits on the model
        print(f"  release sentence failed: {e}")
        return None
    return s if s and len(s) <= 180 and not re.search(r"\d", s) else None


def watch(now: datetime | None = None, root: Path | None = None, dry: bool = False) -> list[dict]:
    """Post each watched release that has landed since the last check; returns what went out."""
    now, root = now or datetime.now(ET), root or get_settings().root
    rec = day_record(root, now)
    done = {k for r in rec.get("releases", []) for k in r.get("keys", [r["key"]])}
    todo = [w for w in rec.get("watch", []) if w["key"] not in done]
    room = MAX_RELEASES - len(rec.get("releases", []))
    if not todo or room <= 0:
        return []
    out = []
    for ws, line in landed(todo, now.date())[:room]:
        sentence = explain(line)
        text = line + (f"\n\n{sentence}" if sentence else "")
        live = _live(dry)
        r = {
            "key": group(ws[0]),
            "keys": [w["key"] for w in ws],
            "at": now.isoformat(timespec="minutes"),
            "text": text,
            "dry_run": not live,
            "id": x_post.post(text) if live else None,
        }
        rec.setdefault("releases", []).append(r)
        save_day(root, now, rec)  # after each post, so a crash never posts it twice
        out.append(r)
        print(f"{now:%Y-%m-%d %H:%M} ET  watch: " + ("POSTED " + r["id"] if live else "DRY RUN would post") + f" ({x_post.xlen(text)}/280):")  # fmt: skip
        print("    " + text.replace("\n", "\n    "))
    return out


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv[1:]
    if "watch" in sys.argv[1:]:
        watch(dry=dry)
    else:
        card(dry=dry)
