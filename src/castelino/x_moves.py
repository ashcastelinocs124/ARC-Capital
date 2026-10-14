"""Post unusual market moves to X, every 30 minutes in US trading hours.

Code checks ASSETS on Yahoo: today's move so far against the standard deviation of the past 252
daily moves (z). Markets with |z| >= Z that haven't been posted today go out as one post, the
largest |z| first. Code writes every number; one cited web search (the Move Explainer) adds a
"Why:" line, kept only if the search cited it. Dry run (log only) unless X_MOVES_LIVE=1 and the
X write keys are set (see x_post.py). Each post carries one chart: the Chart Picker chooses today's
intraday path (the default) or a context chart of one series the Why points at; code fetches and
draws both, and any chart failure falls back (context -> intraday -> text only), never blocking
the post. Each day's posts: data/x_posts/moves/<YYYY-MM-DD>.json, charts in <YYYY-MM-DD>/<HHMM>.png.
Run by deploy/crontab: python -m castelino.x_moves [--dry-run]
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Literal
from zoneinfo import ZoneInfo

import pandas as pd
from pydantic import BaseModel

from castelino import x_post
from castelino.agents.base import StructuredAgent
from castelino.agents.update.facts import facts_from_search
from castelino.agents.update.fsio import atomic_write_text
from castelino.config import get_settings

ET = ZoneInfo("America/New_York")
ASSETS = [  # (name, Yahoo symbol, unit); ^TNX quotes the yield in %, so its moves are in bp
    ("S&P 500", "^GSPC", "%"),
    ("Nasdaq 100", "^NDX", "%"),
    ("Russell 2000", "^RUT", "%"),
    ("US 10-year yield", "^TNX", "bp"),
    ("WTI crude", "CL=F", "%"),
    ("Gold", "GC=F", "%"),
    ("Copper", "HG=F", "%"),
    ("Dollar index", "DX-Y.NYB", "%"),
    ("USD/JPY", "JPY=X", "%"),
    ("Bitcoin", "BTC-USD", "%"),
]
Z = 2.5  # ponytail: one bar for every market; tune it from the dry-run log
MAX_PER_DAY = 3
MAX_ALSO = 3  # other markets named on a combined post's "Also moving" line
OPEN, CLOSE = time(9, 35), time(16, 5)
LINK = "arcresearch.markets"

SYSTEM = """You explain one market move for an X post by ARC Research, a macro research shop.
Search today's news and answer with ONE sentence of at most 170 characters saying why it moved,
with a citation. Use only news reported today by named outlets: no anonymous X posts, no
speculation, no advice. Don't restate the size of the move. If no outlet reports a reason,
answer exactly: none"""


@dataclass
class Move:
    name: str
    unit: str  # "%" or "bp"
    change: float  # today's move so far, in unit
    level: float  # last price (the yield in % for ^TNX)
    z: float
    since: date | None  # last earlier day with a move this big the same way; None = none in history
    symbol: str = ""
    prev: float = 0.0  # yesterday's close: the intraday chart's zero line


def measure(name: str, unit: str, closes: pd.Series, today: date, symbol: str = "") -> Move | None:
    """Today's move vs. the past year's daily moves; None unless Yahoo's last bar is today's."""
    closes = closes.dropna()
    if len(closes) < 253 or closes.index[-1].date() != today:
        return None  # a holiday or stale feed: the last bar would be yesterday's move again
    ch = (closes.diff() * 100 if unit == "bp" else closes.pct_change() * 100).dropna()
    now, past = float(ch.iloc[-1]), ch.iloc[:-1]
    sd = float(past.iloc[-252:].std())
    if not sd:
        return None
    bigger = past[past <= now] if now < 0 else past[past >= now]
    since = bigger.index[-1].date() if len(bigger) else None
    return Move(
        name,
        unit,
        round(now, 2),
        round(float(closes.iloc[-1]), 2),
        round(now / sd, 1),
        since,
        symbol,
        float(closes.iloc[-2]),
    )


def check(today: date) -> list[Move]:
    import yfinance as yf

    out = []
    for name, sym, unit in ASSETS:
        try:
            closes = yf.Ticker(sym).history(period="5y", interval="1d", auto_adjust=True)["Close"]
            m = measure(name, unit, closes, today, sym)
        except Exception as e:  # one bad feed skips that market, not the run
            print(f"  {name}: {e}")
            continue
        if m:
            out.append(m)
    return out


def fmt(m: Move) -> str:
    sign = "+" if m.change > 0 else "−"
    return f"{sign}{abs(m.change):.0f}bp" if m.unit == "bp" else f"{sign}{abs(m.change):.1f}%"


def headline(m: Move, today: date) -> str:
    up = m.change > 0
    word = ("rise" if up else "fall") if m.unit == "bp" else ("gain" if up else "drop")
    level = f" to {m.level:.2f}%" if m.unit == "bp" else ""
    if m.since is None:
        when = "in 5 years"
    else:
        when = f"since {m.since:%b} {m.since.day}" + (
            "" if m.since.year == today.year else f", {m.since.year}"
        )
    arrow = "📈" if up else "📉"
    return f"{arrow} {m.name} {fmt(m)} today{level}, its biggest one-day {word} {when} (a {abs(m.z):.1f}σ move)."


def compose(moves: list[Move], why: str | None, today: date) -> str:
    """The post: the lead move, then others in the same run, the why if it fits 280, the link."""
    text = headline(moves[0], today)
    if rest := moves[1 : 1 + MAX_ALSO]:
        text += "\nAlso moving: " + ", ".join(f"{m.name} {fmt(m)}" for m in rest) + "."
    tail = f"\n\n{LINK}"
    if why and x_post.xlen(full := f"{text}\n\nWhy: {why}{tail}") <= x_post.LIMIT:
        return full
    return text + tail


def explain(moves: list[Move], today: date) -> str | None:
    """One cited search for the reason; None when the answer's sentence carries no citation."""
    from castelino.data.web_search import search_cited

    lead = moves[0]
    ask = f"Why is the {lead.name} {'up' if lead.change > 0 else 'down'} {fmt(lead)} today"
    if len(moves) > 1:
        ask += " (with " + ", ".join(f"{m.name} {fmt(m)}" for m in moves[1:]) + ")"
    text, cites = search_cited(SYSTEM, f"Today is {today:%A %B} {today.day}, {today.year}. {ask}?")
    facts = facts_from_search("W", text, cites)  # one per cited line; uncited lines are dropped
    if not facts:
        return None
    why = re.sub(r"\s+([.,;:])", r"\1", facts[0].text).strip()
    return why if len(why) <= 200 else None


class ChartChoice(BaseModel):  # Chart Picker output (closed schema: no defaults)
    choice: Literal["intraday", "context"]
    series: str  # context: "yahoo:TICKER" or "fred:SERIES_ID"; "" for intraday
    name: str  # context: the reader name, the chart's title ("US 10-year yield")
    window_days: int  # context: 30-365
    reason: str


PICKER = """You choose the one chart for an ARC Research market-alert post on X.
Default to "intraday": the markets in the post, change since yesterday's close, through today.
Choose "context" only when the post's Why line names a driver whose own chart explains the move
better than today's price path (a yield, oil, the dollar, one stock, an economic release). Then
name exactly one series: "yahoo:TICKER" for anything that trades today (^TNX, CL=F, NVDA,
DX-Y.NYB) or "fred:SERIES_ID" for economic data (CPIAUCSL, ICSA, DGS2; FRED lags a day or more),
a reader name for it ("US 10-year yield", no figures), and a window of 30-365 days. Pick a
series whose level reads on its own (a yield, breakeven, spread, price or rate such as DGS10,
T10YIE, UNRATE, CL=F), never an index level like CPIAUCSL or INDPRO. For
"intraday" leave series and name empty and window_days 0. Give a one-line reason."""


class ChartPicker(StructuredAgent[ChartChoice]):
    name = "x_chart_picker"
    output_schema = ChartChoice
    tier = "fast"

    def system_prompt(self) -> str:
        return PICKER

    def user_prompt(self, *, post: str, moves: list[Move]) -> str:
        lines = "\n".join(f"- {m.name} ({m.symbol}): {fmt(m)} today, z {m.z:+.1f}" for m in moves)
        return f"Markets in the post:\n{lines}\n\nThe post:\n{post}"


def fetch_bars(symbol: str) -> pd.Series:
    import yfinance as yf

    return yf.Ticker(symbol).history(period="1d", interval="5m")["Close"].dropna()


def intraday_chart(moves: list[Move], path: Path) -> None:
    """Today's change since yesterday's close in 5-minute steps, one line per market of the lead's unit."""
    import matplotlib.dates as md

    from castelino.agents.weekly import charts as wc

    bp = moves[0].unit == "bp"
    lines = []
    for m in [m for m in moves if m.unit == moves[0].unit][: 1 + MAX_ALSO]:
        bars = fetch_bars(m.symbol)
        if len(bars) >= 2 and m.prev:
            lines.append((m, (bars - m.prev) * 100 if bp else (bars / m.prev - 1) * 100))
    if not lines:
        raise RuntimeError("no intraday bars")

    def draw(ax):
        for i, (m, s) in enumerate(lines):
            x = s.index.tz_convert(ET) if s.index.tz else s.index
            ax.plot(x, s.values, color=wc.COMPARE[i], lw=2.2 if i == 0 else 1.6, label=m.name)
        ax.axhline(0, color=wc.INK2, lw=0.9, ls="--")
        ax.xaxis.set_major_formatter(md.DateFormatter("%-I:%M", tz=ET))
        ax.set_ylabel(f"{'bp' if bp else '%'} since yesterday's close", fontsize=8.5)
        if len(lines) > 1:
            ax.legend(frameon=False, fontsize=8.5, loc="best")
        # end labels, nudged apart so two lines that finish close don't print over each other
        gap, last = 0.06 * (ax.get_ylim()[1] - ax.get_ylim()[0]), None
        for i, (_, s) in sorted(enumerate(lines), key=lambda t: float(t[1][1].iloc[-1])):
            y = float(s.iloc[-1])
            pos = y if last is None else max(y, last + gap)
            last = pos
            label = (
                f"{'+' if y > 0 else '−'}{abs(y):.0f}bp"
                if bp
                else f"{'+' if y > 0 else '−'}{abs(y):.1f}%"
            )
            ax.annotate(
                label,
                (s.index[-1], y),
                xytext=(s.index[-1], pos),
                va="center",
                fontsize=9,
                fontweight="bold",
                color=wc.COMPARE[i],
            )

    names = [m.name for m, _ in lines]
    title = (
        names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    ) + " today"
    unit = "bp" if bp else "%"
    wc._frame(
        1,
        title,
        f"{unit} change since yesterday's close, 5-minute steps",
        "Yahoo Finance " + ", ".join(m.symbol for m, _ in lines),
        path,
        draw,
        kicker="MARKET ALERT",
        left=0.12,
    )


def context_chart(c: ChartChoice, path: Path, now: datetime) -> None:
    """One series the Chart Picker named, drawn with the Morning Note's line chart."""
    from castelino.agents import themes
    from castelino.agents.update.guard import unsupported
    from castelino.agents.weekly.charts import make_weekly_exhibits
    from castelino.agents.weekly.models import ExhibitPick

    spec = themes.SERIES.match(c.series)
    if not spec:
        raise ValueError(f"not a fred:/yahoo: series: {c.series!r}")
    days = min(365, max(30, c.window_days))
    fact = themes.fetch_series(*spec.groups(), "S1", now - timedelta(days=days))
    if c.name.strip() and not unsupported([c.name], set()):  # a title never carries a figure
        fact.series.label = c.name.strip()
    pick = ExhibitPick(
        kind="line", title=fact.series.label, fact_ids=["S1"], window_days=days, points=[], unit=""
    )
    out = path.with_suffix("")
    report = SimpleNamespace(sections=[SimpleNamespace(exhibits=[pick])])
    if not make_weekly_exhibits(report, [fact], out, kicker="MARKET ALERT"):
        raise RuntimeError(f"{c.series} could not be drawn")
    (out / "exhibit_1.png").replace(path)
    out.rmdir()


def chart(moves: list[Move], post: str, now: datetime, path: Path) -> dict:
    """Draw the post's chart to `path` and say what was drawn; never raises."""
    rec: dict = {"kind": "intraday"}
    try:
        c = ChartPicker()(post=post, moves=moves)
        rec |= {"picked": c.choice, "reason": c.reason}
        if c.choice == "context":
            rec["series"] = c.series
            context_chart(c, path, now)
            return rec | {"kind": "context"}
    except Exception as e:  # a bad pick or series falls back to the intraday chart
        print(f"  context chart dropped: {e}")
        rec["error"] = str(e)[:200]
    try:
        intraday_chart(moves, path)
        return rec
    except Exception as e:
        print(f"  no chart: {e}")
        return rec | {"kind": None, "error": str(e)[:200]}


def run(dry: bool = False, now: datetime | None = None, root: Path | None = None) -> dict | None:
    """One check; returns the post record when something went out (or would have, in a dry run)."""
    now = now or datetime.now(ET)
    if now.weekday() >= 5 or not OPEN <= now.time() <= CLOSE:
        return None
    path = (root or get_settings().root) / "data" / "x_posts" / "moves" / f"{now:%Y-%m-%d}.json"
    png = path.parent / f"{now:%Y-%m-%d}" / f"{now:%H%M}.png"
    day = json.loads(path.read_text()) if path.exists() else {"posts": []}
    print(f"{now:%Y-%m-%d %H:%M} ET  check {len(ASSETS)} markets")
    if len(day["posts"]) >= MAX_PER_DAY:
        print(f"  already {MAX_PER_DAY} posts today")
        return None
    posted = {n for p in day["posts"] for n in p["markets"]}
    moves = check(now.date())
    for m in moves:
        print(f"  {m.name:<17} {fmt(m):>7}  z {m.z:+.1f}")
    hits = sorted(
        (m for m in moves if abs(m.z) >= Z and m.name not in posted), key=lambda m: -abs(m.z)
    )
    if not hits:
        print(
            "  nothing new" + (f" ({', '.join(sorted(posted))} already posted)" if posted else "")
        )
        return None
    try:
        why = explain(hits, now.date())
    except Exception as e:  # no reason beats no post
        print(f"  why search failed: {e}")
        why = None
    text = compose(hits, why, now.date())
    png.parent.mkdir(parents=True, exist_ok=True)
    drawn = chart(hits, text, now, png)
    if drawn["kind"]:
        drawn["file"] = f"{png.parent.name}/{png.name}"
        print(f"  chart: {drawn['kind']} {drawn.get('series', '')} → {drawn['file']}")
    live = not dry and os.getenv("X_MOVES_LIVE") == "1" and x_post.can_post()
    media = None
    if live and drawn["kind"]:
        try:
            media = x_post.upload_image(png.read_bytes())
        except Exception as e:  # an alert without its chart beats no alert
            print(f"  image upload failed, posting text only: {e}")
    rec = {
        "at": now.isoformat(timespec="minutes"),
        "markets": [m.name for m in hits],
        "moves": [asdict(m) | {"since": m.since and m.since.isoformat()} for m in hits],
        "text": text,
        "chart": drawn,
        "dry_run": not live,
        # ponytail: a failed post raises and isn't recorded, so the next run retries (and re-searches)
        "id": x_post.post(text, media_id=media) if live else None,
    }
    day["posts"].append(rec)
    atomic_write_text(path, json.dumps(day, indent=2, ensure_ascii=False))
    print(
        ("  POSTED " + rec["id"] if live else "  DRY RUN would post")
        + f" ({x_post.xlen(text)}/280):"
    )
    print("    " + text.replace("\n", "\n    "))
    return rec


if __name__ == "__main__":
    run(dry="--dry-run" in sys.argv[1:])
