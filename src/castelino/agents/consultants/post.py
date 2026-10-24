"""A consultant's post to X: the knob on /admin → Consultants (`Consultant.post_to_x`, off by default).

While the knob is on, the evening review asks the Decisions API one more question (POST_Q). A yes has the
Post Writer write one post (what's happening, then what could happen) and name a chart; code draws the
chart with X Scout's chart code (Trade Lab's forms, so the model never supplies a plotted number) and both
go to X, then out as a Substack Note (x_scout.note: after X, never blocking it). Every number in the post must be one of its cited facts, the post carries no link (X bills $0.200
for one against $0.015) and every ticker must trade. No chart, no post. At most one post per consultant a
day: X's id (and the Note's) is kept in that day's log."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from castelino import x_post, x_scout
from castelino.agents.consultants import store
from castelino.agents.consultants.models import Watchlist
from castelino.agents.trade import llm
from castelino.agents.update.models import Fact
from castelino.config import get_settings

POST_Q = (
    "Today brings a notable new point for this topic worth posting publicly: a fresh development, a turning "
    "point or a surprise, not a recap of what the thesis already says, of a point under Already posted, or "
    "of data marked unchanged since an earlier day."
)
SYSTEM = """You write one X post for an ARC Research topic consultant about the notable new point today
brings to its topic. Write analysis, not a list of data points: say what is happening, then what could
happen next. Keep it under 250 characters (X cuts at 280), plain text: no hashtags, no emoji, no links or
web addresses, no advice to buy or sell. Name a company as "Name (TICKER)". Any number must be one of the numbers of the
facts you cite, written as the fact writes it; put those facts' ids in fact_ids. The point must be new
today: cite at least one fact marked (new today), and never repeat a point under Already posted, even in
other words. A figure marked unchanged since an earlier day is not news.

Also pick ONE chart that shows the point, from these forms:
{forms}
series: "fred:SERIES_ID" or "yahoo:TICKER", as many as the form takes; start from the consultant's
watchlist. names: a short reader name per series, no figures. window_days: 30 to 730. threshold: the level
for threshold_band, else null. chart_title: the claim the chart shows, under 60 characters, no figures."""


class PostDraft(BaseModel):  # LLM output (closed schema: no defaults)
    text: str
    fact_ids: list[str]
    form: str
    series: list[str]
    names: list[str]
    window_days: int
    threshold: float | None
    chart_title: str


def errors(
    d: PostDraft, facts: dict[str, Fact], lookup=None, fresh: set[str] | None = None
) -> list[str]:
    """What's wrong with a draft: an unknown fact id, no fact new today (`fresh`), a figure its facts
    don't give, a link, over 280 characters, or a ticker that doesn't trade."""
    bad = [f"{i} is not one of the facts given to you" for i in d.fact_ids if i not in facts]
    if fresh is not None and not fresh & set(d.fact_ids):
        bad.append("the post cites no fact marked (new today); a point already out is not news")
    nums = {n for i in d.fact_ids if i in facts for n in facts[i].numbers}
    bad += [
        b.replace("the source line or the chart data", "the facts you cite")
        for b in x_scout._untraced([d.text], nums)
    ]
    if x_scout._LINK.search(d.text):
        bad.append("the post has a link or web address; it must carry none")
    if (n := x_post.xlen(d.text)) > x_post.LIMIT:
        bad.append(f"the post is {n} characters; X allows {x_post.LIMIT}, so cut it to under 250")
    return bad + x_scout.ticker_errors([d.text], lookup)


def write(
    topic: str,
    context_md: str,
    wl: Watchlist,
    facts: list[Fact],
    meter: llm.Meter,
    fresh: set[str] | None = None,
    seen: dict[str, str] | None = None,
) -> PostDraft:
    """One Post Writer call, one retry with the errors; raises ValueError when both fail the checks.
    Each fact is marked new today (`fresh`), unchanged since an earlier day (`seen`) or by its day."""
    from castelino.agents.trade import forms

    seen = seen or {}

    def mark(f: Fact) -> str:
        if fresh and f.id in fresh:
            return " (new today)"
        if (k := store.fact_key(f.text)) in seen:
            return f" (unchanged since {seen[k]})"
        return f" (from {day})" if (day := store._day_of(f.id)) else ""

    by_id = {f.id: f for f in facts}
    companies = ", ".join(f"{c.name} ({c.ticker})" for c in wl.companies) or "none"
    user = (
        f"Topic: {topic}\nWatchlist companies: {companies}\nWatchlist series: "
        f"{', '.join(wl.series) or 'none'}\n\n{context_md}\n\n## Facts you may cite\n"
        + ("\n".join(f"- [{f.id}] {f.text} ({f.source_title}){mark(f)}" for f in facts) or "(none)")
    )
    msgs = [
        {"role": "system", "content": SYSTEM.format(forms=forms.catalog_text())},
        {"role": "user", "content": user},
    ]
    model = get_settings().consultants.note_model
    for _ in range(2):
        d = llm.structured("consultant_post", model, msgs, PostDraft, meter)
        if not (bad := errors(d, by_id, fresh=fresh)):
            return d
        msgs += [
            {"role": "assistant", "content": d.model_dump_json()},
            {"role": "user", "content": "Fix these and answer again:\n- " + "\n- ".join(bad)},
        ]
    raise ValueError(bad)


def run(
    slug: str, day: str, context_md: str, facts: list[Fact], meter: llm.Meter
) -> tuple[str, str] | None:
    """Write, chart and post today's point; returns (text, chart form), or None when it already posted
    today. Raises when the draft fails its checks twice, no chart can be drawn or X refuses."""
    if store.day_log(slug, day).post_id:
        return None
    seen = store.earlier_texts(slug, day)
    fresh = {
        f.id for f in facts if store._day_of(f.id) == day and store.fact_key(f.text) not in seen
    }
    if not fresh:  # e.g. the Ramp index re-read unchanged: the same post would go out again
        raise ValueError("nothing new today: every fact was gathered on an earlier day")
    c = store.load(slug)
    context_md += f"\n\n## Already posted (never repeat these)\n{store.posts_md(slug)}"
    d = write(c.topic, context_md, c.watchlist, facts, meter, fresh, seen)
    png = store.cdir(slug) / "posts" / f"{day}.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    pick = x_scout.ScoutPick(
        post=True,
        item_id="",
        topic="macro",
        headline=d.chart_title,
        form=d.form,
        series=d.series,
        names=d.names,
        window_days=d.window_days,
        threshold=d.threshold,
        chart_title=d.chart_title,
        reason="",
        searches=[],
    )
    _, _, form, _ = x_scout.chart(pick, datetime.now(x_scout.ET), png, kicker=c.topic.upper())
    if not x_post.can_post():
        raise RuntimeError("the X write keys aren't set here, so nothing was posted")
    pid = x_post.post(d.text, media_id=x_post.upload_image(png.read_bytes()))
    with store.edit_day(slug, day) as log:
        log.post_id = pid  # saved before the Note, so a Note failure can't make X post twice
    noted = x_scout.note(d.text, png, live=True)
    with store.edit_day(slug, day) as log:
        log.note_id = noted["note_id"]
        if err := noted.get("note_error"):
            log.notes.append(f"Substack Note failed: {err}")
    return d.text, form
