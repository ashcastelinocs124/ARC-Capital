"""X Scout: ARC's short updates, run by one module with three jobs. They post on X, and the card and
the findings also go out as Substack Notes (note(): after X, never blocking it; substack.post_note
with the SUBSTACK_SID cookie). Dry run (log only) unless X_SCOUT_LIVE=1 and the X write keys are set
(see x_post.py). One log: data/x_scout.log.

`scout` (the default; every 2 h, 10:15-22:15 ET on weekdays and 08:15-22:15 at weekends): post one
interesting macro or AI finding with a chart. Code runs one cited web search for the last 6 hours of
macro and AI news (uncited lines are dropped). The Scout picks the one item worth a post, or
nothing, and names a chart form (allowed_forms) and the fred:/yahoo: series it needs; code fetches
and draws them. A pass with nothing to post (no item clears the bar, or the pick can't be
charted, written or was already posted) is followed by a second one (PASSES): the last 24 hours, and
the Scout must pick the best item not yet posted. One cited follow-up search adds context, and the
Writer writes the lead and a 3-post analysis thread from that line, the context and the chart's
code-computed numbers (the Note gets the same text as paragraphs), and names the source; code adds the topic tag
and "Source: <name>" to the lead. X posts carry no link: X's pay-per-use API charges $0.200 for a
post with a URL against $0.015 for a plain one (docs.x.com, 2026-10-19), and X turns a bare domain
("Investing.com") into a link, so check() refuses one anywhere in the posts. The Substack Note keeps
the link (Notes are free). Every figure must be among those numbers (check()) and each post must fit
280, or the Writer gets one retry told what failed, then nothing is posted. The chart is the point,
so a chart failure posts nothing. At most MAX_PER_DAY posts a day; the Scout sees this account's
posts from the last MEMORY_DAYS days and today's market alerts, and code refuses a source URL
already posted. A run within THEME_GAP of today's Theme Charts thread is skipped. Records:
data/x_posts/scout/<YYYY-MM-DD>.json, charts in <YYYY-MM-DD>/<HHMM>.png.

`card` (07:00 ET on weekdays): code reads Week Ahead's data/week_ahead.json, picks the key rows (US
releases by TIERS with a consensus, inflation and jobs abroad, the largest companies reporting),
draws the card in the ARC chart frame and saves the day's watch list: today's MAX_RELEASES most
important release groups still to come (watch_rows: top-tier US data, then the largest companies),
marked WATCH. The Card Writer adds a short read whose figures must be the card's (check()); one
retry, then a code-written line. Monday's card is the whole week's and also sets Monday's watch list.

`watch` (every 5 min, 07:00-19:55 ET on weekdays): code fetches today's Nasdaq calendar and posts
each watched release whose actual (data) or EPS (earnings) has appeared, once, at most MAX_RELEASES
a day: a code-written numbers line (a release's m/m and y/y together), then one Release Writer
sentence that may hold no digit (else it's dropped and the numbers line posts alone). Release posts
skip the Theme Charts quiet hour: they are news. Records: data/x_posts/calendar/<YYYY-MM-DD>.json
(card, watch list, releases) and <YYYY-MM-DD>/card.png.

Run by deploy/crontab: python -m castelino.x_scout [scout|card|watch] [--dry-run]
"""

from __future__ import annotations

import json
import os
import re
import sys
import textwrap
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from castelino import substack, x_post
from castelino.agents.base import StructuredAgent
from castelino.agents.update.charts import is_rate
from castelino.agents.update.facts import _NUM, facts_from_search, numbers_in
from castelino.agents.update.fsio import atomic_write_text
from castelino.agents.update.guard import _FIG, _supported, unsupported
from castelino.agents.update.models import Fact
from castelino.config import get_settings
from castelino.week_ahead import econ, nasdaq
from castelino.week_ahead.econ import parse_num

ET = ZoneInfo("America/New_York")
MAX_PER_DAY = 8  # one per 2-hourly run (deploy/crontab)
MEMORY_DAYS = 7
THEME_GAP = timedelta(hours=1)  # the morning Theme Charts thread gets the feed to itself this long
PASSES = ((6, False), (24, True))  # (hours searched, must pick): every run posts unless all is old
TAG = {"macro": "MACRO · ", "ai": "AI · "}

SCAN_SYSTEM = (
    "You are a markets news desk for ARC Research, a macro research shop. Report only what named "
    "outlets published; quote figures exactly as reported, with a citation on every line."
)
SCAN_USER = """It is {now} New York time. List up to 8 items from the last {hours} hours that a macro
investor would care about, most notable first, one per line starting with MACRO or AI: data
releases and how they compared with forecasts, central banks and policy, rates, credit, oil and the
dollar; AI model launches with benchmark or price figures, chip and data-center news, AI capex and
earnings. One sentence each, with the key figures exactly as reported."""

SCOUT = """You pick at most one item for ARC Research's X account to post with a chart and a short
analysis. Post only what a macro investor would stop scrolling for: a data surprise, a first or a
record, a policy shift, a model or chip launch with hard numbers, a big AI capex or earnings figure.
Routine, in-line or already-posted stories are a no: answer post=false, which should be the usual
answer. Never pick a story listed under "Already posted", including a market that today's alerts
already covered. If you post, name the chart that best shows the story: a form from the list in
the message and the series it needs, each "fred:SERIES_ID" for economic data (FRED lags a day or
more) or "yahoo:TICKER" for anything that trades (NVDA, SMH, ^TNX, CL=F, DX-Y.NYB). Pick the form
that tells the story at a glance, not a line by habit: a dial for how stretched a market is, bars
for which markets moved most, underwater for a selloff or recovery, calendar for one stock against
its sector, slope for whether a hedge held on the worst days, scatter for whether two things move
together; a line or compare only when the story is a series' path. Pick series whose level reads
on its own (a yield, spread, price or rate such as DGS10, T10YIE, UNRATE), never an index level
like CPIAUCSL or INDPRO. names: a reader name per series ("Chip stocks (SMH)"). window_days:
30-365. threshold: a number for threshold_band, else null. chart_title and headline: short, no
figures. When post is false, leave item_id, series and names empty and give the reason."""
MUST = """Nothing cleared the bar in the last 6 hours, and the account posts every run. This time
pick the best item here that is not already posted and that a chart can show; answer post=false
only if every item is already posted or none can be charted."""

WRITER = """You write one X thread for ARC Research, a macro research shop: a lead and exactly 3
analysis posts. The same text also goes out as a Substack Note, so make the analysis worth reading.
- lead (at most 220 characters): the finding and what the attached chart shows. For a chart that is
  not a line, say what its form shows with its own numbers (the "The chart shows" lines), such as
  "beat chip stocks on 63 of 130 days" or "85% of the way up its 1-year range".
- posts: exactly 3, each at most 260 characters, 2-3 plain sentences, no numbering (code adds it):
  1. What happened in detail: the figures against forecasts or the prior reading, and what the
     chart adds (the trend, how stretched it is, how it compares).
  2. Why it matters: the cause and the chain from it to rates, equities, the dollar or AI spending,
     drawn from the context lines.
  3. What to watch: the next data, event or level that would confirm or break the story.
Use only figures from the source line, the context lines and the chart data you are given, written
as given; any other number gets the post dropped. Write a change in words ("up 10bp", "down 2.1%"),
never with a + sign. No hashtags, no emoji, no links or web addresses, no advice: code adds the topic
tag and the source. source: the name of the outlet or body that published the source line, as
readers know it ("Reuters", "NAHB", "AP"), never a link or a domain: write "Investing", not
"Investing.com"."""
CONTEXT = """Background for an X post about this news item: {item}
In up to 6 lines, each with a citation, give the context an analyst would add: why it happened, the
prior readings or the trend it continues or breaks, how markets reacted, and what comes next (the
next release, meeting, report or deadline). Quote figures exactly as reported. Nothing older than a
year unless it is the comparison that matters."""
POSTS = 3


class ScoutPick(BaseModel):  # LLM output (closed schema: no defaults)
    post: bool
    item_id: str  # "N3"; "" when post is false
    topic: Literal["macro", "ai"]
    headline: str  # a short label of the story, no figures: the log and the next runs' memory
    form: str  # a Trade Lab form (agents/trade/forms.py FORMS) from the run's allowed list
    series: list[str]  # "fred:SERIES_ID" / "yahoo:TICKER", as many as the form takes
    names: list[str]  # a reader name per series, the chart's legend
    window_days: int
    threshold: float | None  # threshold_band only
    chart_title: str
    reason: str


class ScoutPost(BaseModel):  # LLM output (closed schema: no defaults)
    lead: str
    posts: list[str]  # the POSTS analysis posts: what happened, why it matters, what to watch
    source: str  # the publisher's name, never a link or domain


class Scout(StructuredAgent[ScoutPick]):
    name = "x_scout"
    output_schema = ScoutPick
    tier = "reasoning"
    max_output_tokens = 16000  # reasoning tokens share this budget

    def __init__(self) -> None:
        self.model = get_settings().x_scout.scout_model

    def system_prompt(self) -> str:
        return SCOUT

    def user_prompt(
        self, *, now: str, items: list[Fact], posted: list[dict], forms: str, must: bool = False
    ) -> str:
        done = "\n".join(f"- {p['headline']}" for p in posted) or "(nothing yet)"
        lines = "\n".join(f"[{f.id}] {f.text} — {f.source_title}" for f in items)
        out = (
            f"Now: {now} New York time.\n\nAlready posted:\n{done}\n\nCited items:\n{lines}"
            f"\n\nChart forms you may use this run:\n{forms}"
        )
        return f"{out}\n\n{MUST}" if must else out


class Writer(StructuredAgent[ScoutPost]):
    name = "x_scout_writer"
    output_schema = ScoutPost
    tier = "fast"

    def __init__(self) -> None:
        self.model = get_settings().x_scout.writer_model

    def system_prompt(self) -> str:
        return WRITER

    def user_prompt(
        self,
        *,
        item: Fact,
        chart_title: str,
        numbers: str,
        context: str = "",
        fix: list[str] | None = None,
    ) -> str:
        out = (
            f"Source line ({item.source_title}, {item.source_url}): {item.text}\n\n"
            f"Context lines (cited):\n{context or '(none found)'}\n\n"
            f"The chart: {chart_title}\n{numbers}"
        )
        if fix:
            out += "\n\nYour last draft had problems. Fix them:\n" + "\n".join(
                f"- {e}" for e in fix
            )
        return out


def context(item: Fact) -> list[Fact]:
    """One cited follow-up search on the picked story, as facts (K1…) the analysis may use: the
    why, the trend, the market reaction and what comes next. [] on any failure."""
    from castelino.data import web_search

    try:
        text, cites = web_search.search_cited(
            SCAN_SYSTEM, CONTEXT.format(item=item.text), model=get_settings().x_scout.search_model
        )
    except Exception as e:  # noqa: BLE001 - the post goes out on the source line alone
        print(f"  context search failed: {e}")
        return []
    return facts_from_search("K", text, cites)


def scan(now: datetime, hours: int = 6) -> list[Fact]:
    from castelino.data import web_search

    text, cites = web_search.search_cited(
        SCAN_SYSTEM,
        SCAN_USER.format(now=f"{now:%a %b %d, %H:%M}", hours=hours),
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


PLAIN_PER_DAY = 2  # line or compare charts a day; the rest use the other forms (user, 2026-10-20)
LINES = ("line", "compare")
FALLBACK = (
    "dial",
    "bars",
    "line",
)  # tried in turn, if allowed, when the picked form can't be drawn


def allowed_forms(today: list[dict]) -> list[str]:
    """The forms this run may use: never the previous post's, and a line or compare only while
    fewer than PLAIN_PER_DAY went out today. Posts from before forms existed count as lines."""
    from castelino.agents.trade.forms import FORMS

    used = [p.get("form", "line") for p in today]
    lines_left = sum(f in LINES for f in used) < PLAIN_PER_DAY
    return [
        f for f in FORMS if f != (used[-1] if used else None) and (lines_left or f not in LINES)
    ]


def chart(
    pick: ScoutPick, now: datetime, path: Path, allowed: list[str] | None = None
) -> tuple[list[Fact], str, str, list[tuple[str, float]]]:
    """Draw the pick to `path` in its form, else the first allowed FALLBACK that draws. Returns the
    series facts, the line chart's subtitle ("" for other forms), the form drawn and the numbers a
    non-line form computed; raises when nothing can be drawn."""
    from castelino.agents import themes
    from castelino.agents.trade.forms import FORMS

    specs = [themes.SERIES.match(s) for s in pick.series[:12]]
    if not specs or not all(specs):
        raise ValueError(f"not fred:/yahoo: series: {pick.series!r}")
    allowed = list(FORMS) if allowed is None else allowed
    for form in [f for f in dict.fromkeys([pick.form, *FALLBACK]) if f in allowed and f in FORMS]:
        n = FORMS[form].max_series
        if len(pick.series) < FORMS[form].min_series or (
            form == "compare" and len(pick.series) < 2
        ):
            continue
        try:
            if form in LINES:
                return (
                    *_line_chart(pick, now, path, specs[: 1 if form == "line" else 4]),
                    form,
                    [],
                )
            facts, sub, shown = _form_chart(pick, form, now, path, specs[:n])
            return facts, sub, form, shown
        except Exception as e:  # noqa: BLE001 - try the next form
            print(f"  {form} chart failed: {e}")
    raise RuntimeError(f"{pick.series} could not be drawn in any allowed form")


def _series_facts(pick: ScoutPick, now: datetime, specs: list, days: int) -> list[Fact]:
    from castelino.agents import themes

    start = now - timedelta(days=days)
    facts = [themes.fetch_series(*m.groups(), f"S{i}", start) for i, m in enumerate(specs, 1)]
    for f, name in zip(facts, pick.names, strict=False):
        if name.strip() and not unsupported([name], set()):  # a legend never carries a figure
            f.series.label = name.strip()
    return facts


def _form_chart(
    pick: ScoutPick, form: str, now: datetime, path: Path, specs: list
) -> tuple[list[Fact], str, list[tuple[str, float]]]:
    """A Trade Lab form (dial, bars, underwater…) drawn by its code; the first 4 series' facts
    still give the Writer their levels."""
    from castelino.agents.trade import forms
    from castelino.agents.trade.models import ChartSpec

    series = [m.group(0) for m in specs]
    spec = ChartSpec(
        section="intro",
        form=form,
        series=series,
        names=pick.names[: len(series)] or None,
        window_days=min(730, max(30, pick.window_days)),
        threshold=pick.threshold,
        title=pick.chart_title[:60],
        why="",
        agent_pick=True,
    )
    nums = forms.render(spec, forms.Sources.live(), path, 1, kicker=pick.topic.upper())
    return _series_facts(pick, now, specs[:4], min(365, max(30, pick.window_days))), "", nums


def _line_chart(pick: ScoutPick, now: datetime, path: Path, specs: list) -> tuple[list[Fact], str]:
    """One series as a line, 2-4 compared: the Morning Note renderer, with its subtitle."""
    from castelino.agents.weekly.charts import make_weekly_exhibits
    from castelino.agents.weekly.models import ExhibitPick

    days = min(365, max(30, pick.window_days))
    facts = _series_facts(pick, now, specs, days)
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


def chart_numbers(
    facts: list[Fact], subtitle: str, form: str = "line", shown: list[tuple[str, float]] = ()
) -> tuple[str, set[float]]:
    """The chart's numbers as the Writer reads them, and the set its figures must come from: each
    series' last, first, change, last week, high and low (series_fact), its distance below the
    window high and, for prices, its level rebased to 100; plus the chart's own subtitle, or the
    numbers a non-line form computed (an RSI, a place in the 52-week range, a drawdown)."""
    from castelino.agents.trade.forms import FORMS

    lines = [f"Chart form: {form} ({FORMS[form].description})" if form in FORMS else ""]
    lines += [f"Chart subtitle: {subtitle}"] if subtitle else []
    lines += [f"The chart shows {label}: {v:g}" for label, v in shown]
    nums = set(numbers_in(subtitle)) | {x for _, v in shown for x in (v, abs(v))}
    lines = [x for x in lines if x]
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


_LINK = re.compile(r"https?://|\bwww\.|\w\.[a-z]{2,}\b", re.I)  # what X would turn into a link


def thread(posts: list[str]) -> list[str]:
    """The analysis posts as they go out on X: "2/ …", "3/ …", "4/ …" (the lead is 1)."""
    return [f"{i}/ {p}" for i, p in enumerate(posts, 2)]


def check(lead: str, posts: list[str], source: str, nums: set[float]) -> list[str]:
    """What's wrong with a draft: a figure no source gave, a link or domain (X bills a post with a
    URL at $0.200), a source that isn't a name, a post over 280 or not POSTS analysis posts. Unit
    figures (%, bp, pp) go through the Morning Note guard; any other number must be in `nums` too,
    except a year or a plain count up to 31 (dates, "3 weeks"). The lead is measured with the source
    line code adds, each analysis post with its number."""
    texts = [lead, *posts]
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
    if len(posts) != POSTS:
        bad.append(f"write exactly {POSTS} analysis posts, not {len(posts)}")
    for name, text in (("lead", lead), *((f"post {i}", p) for i, p in enumerate(posts, 2))):
        if _LINK.search(text):
            bad.append(f"the {name} has a link or web address; X posts here carry none")
    if not source.strip() or len(source) > 40 or _LINK.search(source):
        bad.append(f"the source {source!r} must be a short name, not a link or domain")
    if (n := x_post.xlen(f"{lead}\n\nSource: {source}")) > x_post.LIMIT:
        bad.append(f"the lead post with its source line is {n} characters; X allows 280")
    for i, p in enumerate(thread(posts), 2):
        if (n := x_post.xlen(p)) > x_post.LIMIT:
            bad.append(f"post {i} is {n} characters with its number; X allows 280")
    return bad


def write(
    pick: ScoutPick, item: Fact, numbers: str, nums: set[float], ctx: str = ""
) -> tuple[str, list[str], str] | None:
    """The tagged lead, the analysis posts and the source's name; one retry told what failed, then
    None."""
    writer, fix = Writer(), None
    for _ in range(2):
        d = writer(item=item, chart_title=pick.chart_title, numbers=numbers, context=ctx, fix=fix)
        lead, source = TAG[pick.topic] + d.lead.strip(), d.source.strip()
        posts = [p.strip() for p in d.posts if p.strip()]
        fix = check(lead, posts, source, nums)
        if not fix:
            return lead, posts, source
        print("  guard: " + "; ".join(fix))
    return None


def find(
    now: datetime, hours: int, must: bool, posted: list[dict], png: Path, allowed: list[str]
) -> tuple[ScoutPick, Fact, tuple[str, str, str], str] | None:
    """One pass: scan, pick, chart (drawn to `png`) and write. None when it has nothing to post."""
    items = scan(now, hours)
    print(f"  scan, last {hours}h{' (must pick)' if must else ''}: {len(items)} cited items")
    stamp = f"{now:%a %b %d, %H:%M}"
    from castelino.agents.trade.forms import FORMS

    catalog = "\n".join(f"- {f}: {FORMS[f].description} Series: {FORMS[f].min_series} to {FORMS[f].max_series}." for f in allowed)  # fmt: skip
    pick = (
        Scout()(now=stamp, items=items, posted=posted, forms=catalog, must=must) if items else None
    )
    hit = next((f for f in items if pick and pick.post and f.id == pick.item_id), None)
    if hit is None:
        print("  pick: nothing" + (f" ({pick.reason})" if pick else ""))
        return None
    print(
        f"  pick: {pick.topic.upper()} · {pick.headline} ({hit.id}, {hit.source_title})"
        f" → {pick.form}: {', '.join(pick.series)} {pick.window_days}d"
    )
    if hit.source_url in {p["url"] for p in posted}:
        print("  already posted this story")
        return None
    png.parent.mkdir(parents=True, exist_ok=True)
    try:
        series, subtitle, form, shown = chart(pick, now, png, allowed)
    except Exception as e:  # the chart is the point: no chart, no post
        print(f"  no chart, no post: {e}")
        return None
    numbers, nums = chart_numbers(series, subtitle, form, shown)
    ctx = context(hit)
    print(f"  context: {len(ctx)} cited lines")
    lines = "\n".join(f"- {f.text} ({f.source_title})" for f in ctx)
    texts = write(
        pick, hit, numbers, nums | set(hit.numbers) | {n for f in ctx for n in f.numbers}, lines
    )
    if texts is None:
        print("  still failing after a retry: no post")
        return None
    return pick, hit, texts, form


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
    posted = recent(base, now)
    allowed = allowed_forms(day["posts"])
    found = None
    for hours, must in PASSES:
        if found := find(now, hours, must, posted, png, allowed):
            break
    if found is None:
        return None
    pick, hit, texts, form = found
    text, posts, source = texts
    lead = f"{text}\n\nSource: {source}"
    live = not dry and os.getenv("X_SCOUT_LIVE") == "1" and x_post.can_post()
    ids: list[str] = []
    if live:
        # ponytail: a failed upload or lead post raises and isn't recorded, so the next run retries
        ids.append(x_post.post(lead, media_id=x_post.upload_image(png.read_bytes())))
        try:
            for p in thread(posts):  # each replies to the one before
                ids.append(x_post.post(p, reply_to=ids[-1]))
        except Exception as e:  # the lead is out: record it anyway so it never goes twice
            print(f"  thread stopped after {len(ids)} posts: {e}")
    # one Note reads better than a thread: the lead, the analysis as paragraphs, then the source
    # with its link (free on Substack), with the chart
    body = "\n\n".join([text, *posts, f"Source: {source} ({hit.source_url})"])
    noted = note(body, png, live)
    rec = {
        "at": now.isoformat(timespec="minutes"),
        "topic": pick.topic,
        "headline": pick.headline,
        "reason": pick.reason,
        "source_title": hit.source_title,
        "source_url": hit.source_url,
        "source": source,
        "series": pick.series,
        "form": form,  # allowed_forms() reads it back
        "chart": f"{png.parent.name}/{png.name}",
        "lead": lead,
        "thread": thread(posts),
        "dry_run": not live,
        "ids": ids,
        **noted,
    }
    day["posts"].append(rec)
    atomic_write_text(path, json.dumps(day, indent=2, ensure_ascii=False))
    print(
        ("  POSTED " + " ".join(ids) if live else "  DRY RUN would post")
        + f" ({x_post.xlen(lead)}/280) + {len(posts)} thread posts:"
    )
    print("    " + lead.replace("\n", "\n    "))
    for t in thread(posts):
        print(f"    ↳ {t} ({x_post.xlen(t)}/280)")
    return rec


# ── the calendar: the week's or today's card each weekday morning, each release as it lands ──

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
CAL_TAG = {"week": "WEEK AHEAD · ", "day": "TODAY · "}
FALLBACK = {
    "week": CAL_TAG["week"] + "The data and earnings that matter this week, by day.",
    "day": CAL_TAG["day"] + "What's out today and when.",
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


def note(text: str, png: Path | None, live: bool) -> dict:
    """The same post as a Substack Note (the card and findings; release posts stay on X). Runs
    after X and never raises: the Notes API is unofficial, so a failure is logged and recorded."""
    if not live:
        print("  DRY RUN would also post it as a Substack Note")
        return {"note_id": None}
    if not substack.can_note():
        print("  no Substack Note: SUBSTACK_SID is not set")
        return {"note_id": None}
    try:
        return {"note_id": substack.post_note(text, png)}
    except Exception as e:  # noqa: BLE001 - X already went out; the Note is a bonus
        print(f"  note failed: {e}")
        return {"note_id": None, "note_error": str(e)[:200]}


# ── the morning card ───────────────────────────────────────────────────────


def read(kind: str, title: str, card: str, nums: set[float]) -> str:
    """The Card Writer's read, tagged; one retry told what failed, then the code-written line."""
    fix = None
    for _ in range(2):
        try:
            text = (
                CAL_TAG[kind]
                + CardWriter()(kind=kind, title=title, card=card, fix=fix).text.strip()
            )
        except Exception as e:  # noqa: BLE001 - the card goes out with the fallback line
            print(f"  card read failed: {e}")
            break
        fix = check(text, "", "", nums)
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
        **note(text, png, live),
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
    """'US Core PPI: 0.7% m/m vs 0.3% expected (previous 0.2%); 5% y/y vs ...' for one release."""
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
    return f"{head}: " + "; ".join(parts) + "."


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
            line = f"{company(w)} EPS: {_money(eps)}" + (f" vs {_money(est)} expected" if est is not None else "")  # fmt: skip
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
    # python -m castelino.x_scout [scout|card|watch] [--dry-run]; scout (the findings run) is the default
    args, dry = sys.argv[1:], "--dry-run" in sys.argv[1:]
    if "card" in args:
        card(dry=dry)
    elif "watch" in args:
        watch(dry=dry)
    else:
        run(dry=dry)
