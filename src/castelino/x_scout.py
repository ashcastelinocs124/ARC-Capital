"""Post one interesting macro or AI finding to X with a chart, a few times a day.

Code runs one cited web search for the last 6 hours of macro and AI news (uncited lines are
dropped). The Scout picks the one item worth a post, or nothing, and names 1-4 fred:/yahoo: series
that chart it; code fetches and draws them with the Morning Note renderer. The Writer writes the
lead post and one reply from that cited line and the chart's code-computed numbers; code adds the
topic tag and the source line. Every figure must be among those numbers (check()) and each post
must fit 280, or the Writer gets one retry told what failed, then nothing is posted. The chart is
the point, so a chart failure posts nothing. At most MAX_PER_DAY posts a day; the Scout sees this
account's posts from the last MEMORY_DAYS days and today's market alerts, and code refuses a source
URL already posted. A run within THEME_GAP of today's Theme Charts thread is skipped. Dry run (log only) unless X_SCOUT_LIVE=1 and the X write keys are set (see
x_post.py). Each day's posts: data/x_posts/scout/<YYYY-MM-DD>.json, charts in <YYYY-MM-DD>/<HHMM>.png.
Run by deploy/crontab: python -m castelino.x_scout [--dry-run]
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from castelino import x_post
from castelino.agents.base import StructuredAgent
from castelino.agents.update.charts import is_rate
from castelino.agents.update.facts import _NUM, facts_from_search, numbers_in
from castelino.agents.update.fsio import atomic_write_text
from castelino.agents.update.guard import _FIG, _supported, unsupported
from castelino.agents.update.models import Fact
from castelino.config import get_settings

ET = ZoneInfo("America/New_York")
MAX_PER_DAY = 2
MEMORY_DAYS = 7
THEME_GAP = timedelta(hours=1)  # the morning Theme Charts thread gets the feed to itself this long
TAG = {"macro": "📊 MACRO · ", "ai": "🤖 AI · "}

SCAN_SYSTEM = (
    "You are a markets news desk for ARC Research, a macro research shop. Report only what named "
    "outlets published; quote figures exactly as reported, with a citation on every line."
)
SCAN_USER = """It is {now} New York time. List up to 8 items from the last 6 hours that a macro
investor would care about, most notable first, one per line starting with MACRO or AI: data
releases and how they compared with forecasts, central banks and policy, rates, credit, oil and the
dollar; AI model launches with benchmark or price figures, chip and data-center news, AI capex and
earnings. One sentence each, with the key figures exactly as reported."""

SCOUT = """You pick at most one item for ARC Research's X account to post with a chart and a short
analysis. Post only what a macro investor would stop scrolling for: a data surprise, a first or a
record, a policy shift, a model or chip launch with hard numbers, a big AI capex or earnings figure.
Routine, in-line or already-posted stories are a no: answer post=false, which should be the usual
answer. Never pick a story listed under "Already posted", including a market that today's alerts
already covered. If you post, name the chart that best shows the story: 1-4 series, each
"fred:SERIES_ID" for economic data (FRED lags a day or more) or "yahoo:TICKER" for anything that
trades (NVDA, SMH, ^TNX, CL=F, DX-Y.NYB). One series draws a line; 2-4 are compared, with prices
rebased to 100. Pick series whose level reads on its own (a yield, spread, price or rate such as
DGS10, T10YIE, UNRATE), never an index level like CPIAUCSL or INDPRO. names: a reader name per
series ("Chip stocks (SMH)"). window_days: 30-365. chart_title and headline: short, no figures.
When post is false, leave item_id, series and names empty and give the reason."""

WRITER = """You write one X post and its single reply for ARC Research, a macro research shop. The
lead (at most 240 characters) states the finding and what the attached chart shows. The reply (at
most 200 characters) is 2-3 plain sentences of analysis: why it matters and what to watch next.
Use only figures from the source line and the chart data you are given, written as given; any
other number gets the post dropped. Write a change in words ("up 10bp", "down 2.1%"), never with a
+ sign. No hashtags, no emoji, no links, no advice: code adds the topic tag and the source."""


class ScoutPick(BaseModel):  # LLM output (closed schema: no defaults)
    post: bool
    item_id: str  # "N3"; "" when post is false
    topic: Literal["macro", "ai"]
    headline: str  # a short label of the story, no figures: the log and the next runs' memory
    series: list[str]  # 1-4 of "fred:SERIES_ID" / "yahoo:TICKER"
    names: list[str]  # a reader name per series, the chart's legend
    window_days: int
    chart_title: str
    reason: str


class ScoutPost(BaseModel):  # LLM output (closed schema: no defaults)
    lead: str
    reply: str


class Scout(StructuredAgent[ScoutPick]):
    name = "x_scout"
    output_schema = ScoutPick
    tier = "reasoning"
    max_output_tokens = 16000  # reasoning tokens share this budget

    def __init__(self) -> None:
        self.model = get_settings().x_scout.scout_model

    def system_prompt(self) -> str:
        return SCOUT

    def user_prompt(self, *, now: str, items: list[Fact], posted: list[dict]) -> str:
        done = "\n".join(f"- {p['headline']}" for p in posted) or "(nothing yet)"
        lines = "\n".join(f"[{f.id}] {f.text} — {f.source_title}" for f in items)
        return f"Now: {now} New York time.\n\nAlready posted:\n{done}\n\nCited items:\n{lines}"


class Writer(StructuredAgent[ScoutPost]):
    name = "x_scout_writer"
    output_schema = ScoutPost
    tier = "fast"

    def __init__(self) -> None:
        self.model = get_settings().x_scout.writer_model

    def system_prompt(self) -> str:
        return WRITER

    def user_prompt(
        self, *, item: Fact, chart_title: str, numbers: str, fix: list[str] | None = None
    ) -> str:
        out = (
            f"Source line ({item.source_title}): {item.text}\n\nThe chart: {chart_title}\n{numbers}"
        )
        if fix:
            out += "\n\nYour last draft had problems. Fix them:\n" + "\n".join(
                f"- {e}" for e in fix
            )
        return out


def scan(now: datetime) -> list[Fact]:
    from castelino.data import web_search

    text, cites = web_search.search_cited(
        SCAN_SYSTEM,
        SCAN_USER.format(now=f"{now:%a %b %d, %H:%M}"),
        model=get_settings().x_scout.search_model,
    )
    return facts_from_search("N", text, cites)


def recent(base: Path, now: datetime) -> list[dict]:
    """What already went out: this agent's posts over MEMORY_DAYS days, then today's market alerts."""
    out = []
    for d in range(MEMORY_DAYS):
        f = base / "scout" / f"{now - timedelta(days=d):%Y-%m-%d}.json"
        if f.exists():
            out += [
                {"headline": p["headline"], "url": p["source_url"]}
                for p in json.loads(f.read_text())["posts"]
            ]
    moves = base / "moves" / f"{now:%Y-%m-%d}.json"
    if moves.exists():
        out += [
            {"headline": p["text"].split("\n")[0], "url": ""}
            for p in json.loads(moves.read_text())["posts"]
        ]
    return out


def chart(pick: ScoutPick, now: datetime, path: Path) -> tuple[list[Fact], str]:
    """Fetch the picked series and draw them to `path` (one as a line, 2-4 compared). Returns the
    series facts and the chart's code-written subtitle; raises when it can't be drawn."""
    from castelino.agents import themes
    from castelino.agents.weekly.charts import make_weekly_exhibits
    from castelino.agents.weekly.models import ExhibitPick

    specs = [themes.SERIES.match(s) for s in pick.series[:4]]
    if not specs or not all(specs):
        raise ValueError(f"not fred:/yahoo: series: {pick.series!r}")
    days = min(365, max(30, pick.window_days))
    start = now - timedelta(days=days)
    facts = [themes.fetch_series(*m.groups(), f"S{i}", start) for i, m in enumerate(specs, 1)]
    for f, name in zip(facts, pick.names, strict=False):
        if name.strip() and not unsupported([name], set()):  # a legend never carries a figure
            f.series.label = name.strip()
    ex = ExhibitPick(
        kind="line" if len(facts) == 1 else "compare",
        title=pick.chart_title,
        fact_ids=[f.id for f in facts],
        window_days=days,
        points=[],
        unit="",
    )
    out = path.with_suffix("")
    report = SimpleNamespace(sections=[SimpleNamespace(exhibits=[ex])])
    drawn = make_weekly_exhibits(report, facts, out, kicker=pick.topic.upper())
    if not drawn:
        raise RuntimeError(f"{pick.series} could not be drawn")
    (out / "exhibit_1.png").replace(path)
    out.rmdir()
    return facts, drawn[0].subtitle


def chart_numbers(facts: list[Fact], subtitle: str) -> tuple[str, set[float]]:
    """The chart's numbers as the Writer reads them, and the set its figures must come from: each
    series' last, first, change, last week, high and low (series_fact), its distance below the
    window high and, for prices, its level rebased to 100; plus the chart's own subtitle."""
    lines, nums = [f"Chart subtitle: {subtitle}"], set(numbers_in(subtitle))
    for f in facts:
        last, first, _chg, _week, high, _low = f.numbers
        below = round((last / high - 1) * 100, 1)
        line = f"{f.series.label}: {f.text}; {abs(below):.1f}% below its window high"
        nums |= {*f.numbers, below}
        if not (f.series.provider == "fred" and is_rate(f.series.id)):
            rebased = round(last / first * 100, 1)
            line += f"; {rebased:.1f} rebased to 100 at the start"
            nums.add(rebased)
        lines.append(line)
    return "\n".join(lines), nums


def check(lead: str, reply: str, source: str, nums: set[float]) -> list[str]:
    """What's wrong with a draft: a figure no source gave, or a post over 280. Unit figures (%, bp,
    pp) go through the Morning Note guard; any other number must be in `nums` too, except a year or a
    plain count up to 31 (dates, "3 weeks"). The reply is measured with the source line code adds."""
    texts = [lead, reply]
    bad = [f"{t} is not in the source line or the chart data" for t in unsupported(texts, nums)]
    for text in texts:
        for m in _NUM.finditer(_FIG.sub(" ", text)):
            tok = m.group(0)
            v = float(tok.replace(",", "").replace("−", "-"))
            if v.is_integer() and (abs(v) <= 31 or ("," not in tok and 1900 <= v <= 2100)):
                continue
            decimals = len(tok.split(".")[1]) if "." in tok else 0
            if not _supported(v, decimals, False, nums):
                bad.append(f"{tok} is not in the source line or the chart data")
    if (n := x_post.xlen(lead)) > x_post.LIMIT:
        bad.append(f"the lead post is {n} characters; X allows 280")
    room = x_post.LIMIT - x_post.xlen(f"\n\n{source}")
    if (n := x_post.xlen(reply)) > room:
        bad.append(f"the reply is {n} characters; it must be at most {room}")
    return bad


def write(pick: ScoutPick, item: Fact, numbers: str, nums: set[float]) -> tuple[str, str] | None:
    """The lead and the reply, tagged and sourced by code; one retry told what failed, then None."""
    writer, fix = Writer(), None
    # just the link: X's card shows the outlet and headline, and a title can eat the reply's room
    source = f"Source: {item.source_url}"
    for _ in range(2):
        d = writer(item=item, chart_title=pick.chart_title, numbers=numbers, fix=fix)
        lead, reply = TAG[pick.topic] + d.lead.strip(), d.reply.strip()
        fix = check(lead, reply, source, nums)
        if not fix:
            return lead, f"{reply}\n\n{source}"
        print("  guard: " + "; ".join(fix))
    return None


def run(dry: bool = False, now: datetime | None = None, root: Path | None = None) -> dict | None:
    """One scout; returns the post record when something went out (or would have, in a dry run)."""
    now = now or datetime.now(ET)
    base = (root or get_settings().root) / "data" / "x_posts"
    path = base / "scout" / f"{now:%Y-%m-%d}.json"
    png = path.parent / f"{now:%Y-%m-%d}" / f"{now:%H%M}.png"
    day = json.loads(path.read_text()) if path.exists() else {"posts": []}
    print(f"{now:%Y-%m-%d %H:%M} ET  scout")
    if len(day["posts"]) >= MAX_PER_DAY:
        print(f"  already {MAX_PER_DAY} posts today")
        return None
    theme = base / "themes" / f"{now:%Y-%m-%d}-am.json"  # rewritten after each thread post
    if theme.exists():
        quiet = datetime.fromtimestamp(theme.stat().st_mtime, ET) + THEME_GAP
        if now < quiet:
            print(f"  Theme Charts thread posted: quiet until {quiet:%H:%M} ET")
            return None
    items = scan(now)
    print(f"  scan: {len(items)} cited items")
    posted = recent(base, now)
    pick = Scout()(now=f"{now:%a %b %d, %H:%M}", items=items, posted=posted) if items else None
    hit = next((f for f in items if pick and pick.post and f.id == pick.item_id), None)
    if hit is None:
        print("  pick: nothing" + (f" ({pick.reason})" if pick else ""))
        return None
    print(
        f"  pick: {pick.topic.upper()} · {pick.headline} ({hit.id}, {hit.source_title})"
        f" → {', '.join(pick.series)} {pick.window_days}d"
    )
    if hit.source_url in {p["url"] for p in posted}:
        print("  already posted this story")
        return None
    png.parent.mkdir(parents=True, exist_ok=True)
    try:
        series, subtitle = chart(pick, now, png)
    except Exception as e:  # the chart is the point: no chart, no post
        print(f"  no chart, no post: {e}")
        return None
    numbers, nums = chart_numbers(series, subtitle)
    texts = write(pick, hit, numbers, nums | set(hit.numbers))
    if texts is None:
        print("  still failing after a retry: no post")
        return None
    lead, reply = texts
    live = not dry and os.getenv("X_SCOUT_LIVE") == "1" and x_post.can_post()
    ids: list[str] = []
    if live:
        # ponytail: a failed upload or lead post raises and isn't recorded, so the next run retries
        ids.append(x_post.post(lead, media_id=x_post.upload_image(png.read_bytes())))
        try:
            ids.append(x_post.post(reply, reply_to=ids[0]))
        except Exception as e:  # the lead is out: record it anyway so it never goes twice
            print(f"  reply failed: {e}")
    rec = {
        "at": now.isoformat(timespec="minutes"),
        "topic": pick.topic,
        "headline": pick.headline,
        "reason": pick.reason,
        "source_title": hit.source_title,
        "source_url": hit.source_url,
        "series": pick.series,
        "chart": f"{png.parent.name}/{png.name}",
        "lead": lead,
        "reply": reply,
        "dry_run": not live,
        "ids": ids,
    }
    day["posts"].append(rec)
    atomic_write_text(path, json.dumps(day, indent=2, ensure_ascii=False))
    print(
        ("  POSTED " + " ".join(ids) if live else "  DRY RUN would post")
        + f" ({x_post.xlen(lead)}/280) + reply ({x_post.xlen(reply)}/280):"
    )
    print("    " + lead.replace("\n", "\n    "))
    print("    ↳ " + reply.replace("\n", "\n      "))
    return rec


if __name__ == "__main__":
    run(dry="--dry-run" in sys.argv[1:])
