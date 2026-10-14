"""Post unusual market moves to X, every 30 minutes in US trading hours.

Code checks ASSETS on Yahoo: today's move so far against the standard deviation of the past 252
daily moves (z). Markets with |z| >= Z that haven't been posted today go out as one post, the
largest |z| first. Code writes every number; one cited web search (the Move Explainer) adds a
"Why:" line, kept only if the search cited it. Dry run (log only) unless X_MOVES_LIVE=1 and the
X write keys are set (see x_post.py). Each day's posts: data/x_posts/moves/<YYYY-MM-DD>.json.
Run by deploy/crontab: python -m castelino.x_moves [--dry-run]
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from castelino import x_post
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


def measure(name: str, unit: str, closes: pd.Series, today: date) -> Move | None:
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
        name, unit, round(now, 2), round(float(closes.iloc[-1]), 2), round(now / sd, 1), since
    )


def check(today: date) -> list[Move]:
    import yfinance as yf

    out = []
    for name, sym, unit in ASSETS:
        try:
            closes = yf.Ticker(sym).history(period="5y", interval="1d", auto_adjust=True)["Close"]
            m = measure(name, unit, closes, today)
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


def run(dry: bool = False, now: datetime | None = None, root: Path | None = None) -> dict | None:
    """One check; returns the post record when something went out (or would have, in a dry run)."""
    now = now or datetime.now(ET)
    if now.weekday() >= 5 or not OPEN <= now.time() <= CLOSE:
        return None
    path = (root or get_settings().root) / "data" / "x_posts" / "moves" / f"{now:%Y-%m-%d}.json"
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
    live = not dry and os.getenv("X_MOVES_LIVE") == "1" and x_post.can_post()
    rec = {
        "at": now.isoformat(timespec="minutes"),
        "markets": [m.name for m in hits],
        "moves": [asdict(m) | {"since": m.since and m.since.isoformat()} for m in hits],
        "text": text,
        "dry_run": not live,
        # ponytail: a failed post raises and isn't recorded, so the next run retries (and re-searches)
        "id": x_post.post(text) if live else None,
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
