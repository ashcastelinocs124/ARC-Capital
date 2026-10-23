"""Market sentiment for the Daily Update (code, no LLM): ARC's Fear & Greed needle and the Sector
Sentiment rows, as facts the Editor uses to explain why a market or sector moved.

Runs after the calendar step (daily run and admin rebuild). The 17:00 Sector Sentiment refresh runs
beside the note, so the stored needle is the previous session's: the step recomputes it from the
day's close (about 30 s of Yahoo + FRED) and reads the sector rows from the latest snapshot, dated in
the fact text. The facts carry the "why" in words (how to read the scale, which signal moved most,
price trend against fundamentals, sector-wide or one stock's story), so the Editor can explain a
reading instead of only quoting it. One finding, "Market sentiment: …", backs them all; the guard
keeps it from being an item of its own.

Fact ids sent1, sent2…, finding id sent-1, rebuilt from scratch for today's note. A past day keeps
the facts its run saved: the needle can't be recomputed for a past day without hindsight.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date
from zoneinfo import ZoneInfo

from castelino.agents.update.facts import numbers_in
from castelino.agents.update.models import Fact, Finding
from castelino.config import get_settings
from castelino.signals import fear_greed
from castelino.signals import sector_sentiment as ss

log = logging.getLogger(__name__)

PREFIX = "sent"  # fact ids sent1, sent2…; finding id sent-1
SOURCE = (
    "ARC Fear & Greed and Sector Sentiment",
    "https://arcresearch.markets/macro#sector-sentiment",
)
ET = ZoneInfo("America/New_York")
READ = (
    "How to read ARC's sentiment gauges: the Fear & Greed needle averages 5 market signals, each "
    "ranked against its own last 2 years (0 = its most fearful day, 100 = its most greedy); below 25 "
    "is Extreme fear, 25 to 45 Fear, 45 to 55 Neutral, 55 to 75 Greed, 75 and up Extreme greed. A "
    "sector's score compares the price trend of its 10 largest stocks (momentum, RSI, distance from "
    "their averages) with their fundamentals (forward P/E against peers, analysts' EPS revisions, "
    "growth): fearful (25 or below) means prices have fallen further than the earnings outlook, "
    "euphoric (75 or above) means they have run ahead of it."
)
MOOD = {
    "euphoric": "euphoric: prices have run ahead of the earnings outlook",
    "fearful": "fearful: prices have fallen further than the earnings outlook",
    "fair": "fair: prices in line with the earnings outlook",
}
# ponytail: a side's -1..+1 score past ±0.1 (about 0.3 sd across the stocks) reads strong or weak;
# tune it if the words mislead.
LEAN = 0.1


def _side(v: float | None, word: str) -> str:
    if v is None:
        return f"{word} unknown"
    return f"{word} {'strong' if v > LEAN else 'weak' if v < -LEAN else 'about average'}"


def needle_text(fg: fear_greed.FearGreed) -> str:
    past = (
        (fg.previous, "the session before"),
        (fg.week_ago, "a week ago"),
        (fg.month_ago, "a month ago"),
        (fg.year_ago, "a year ago"),
    )
    then = "; ".join(f"{v} ({fear_greed.zone(v)}) {when}" for v, when in past if v is not None)
    head = (
        f"ARC Fear & Greed closed {fg.as_of:%A, %B} {fg.as_of.day} at {fg.score} of 100 ({fg.zone})"
    )
    return head + (f"; {then}" if then else "") + "."


def signal_text(c: fear_greed.FGComponent) -> str:
    then = [
        f"{v} {when}"
        for v, when in ((c.previous, "the session before"), (c.week_ago, "a week ago"))
        if v is not None
    ]
    moved = f", from {' and '.join(then)}" if then else ""
    return f"Fear & Greed signal, {c.name}: {c.score} of 100{moved} ({c.raw})."


def _moved(c: fear_greed.FGComponent) -> int:
    return abs(c.score - c.week_ago) if c.week_ago is not None else 0


def sector_text(s: ss.SectorScore, names: dict[str, str], as_of: str) -> str:
    cfg = get_settings().sector_sentiment
    score = s.fg_score
    if score is None:
        score = fear_greed.sector_score(s.divergence, cfg.euphoric_threshold, cfg.fearful_threshold)
    head = f"Sector Sentiment, {s.sector} ({s.etf})" + (
        f", within {s.part_of}" if s.part_of else ""
    )
    parts = [f"{head}, {as_of}: {score} of 100, {MOOD.get(s.label, s.label)}"]
    if s.delta_since_prev is not None:
        prev = fear_greed.sector_score(
            s.divergence - s.delta_since_prev, cfg.euphoric_threshold, cfg.fearful_threshold
        )
        parts.append(f"{prev} at the previous reading")
    parts.append(f"{_side(s.tech_score, 'price trend')}, {_side(s.fund_score, 'fundamentals')}")
    # a fair reading has no mood to trace, and near zero the top stock's share runs past 100%
    if (e := s.explanation) and s.label != "fair":
        top = f"{names.get(e.top_symbol, e.top_symbol)} ({e.top_symbol})"
        agree = f"{e.n_agree} of its {e.n_total} largest stocks lean the same way"
        share = f", which supplies {e.top_share:.0%} of the reading" if e.top_share <= 1 else ""
        parts.append(
            {
                "sector_wide": f"sector-wide, {agree}",
                "stock_specific": f"one stock's story, led by {top}{share}",
            }.get(e.verdict, f"mixed, {agree}, led by {top}")
        )
    return "; ".join(parts) + "."


def add(
    findings: list[Finding],
    facts: list[Fact],
    day: str,
    *,
    today: Callable[[], date] = date.today,
    load=ss.load_snapshot,
    compute=fear_greed.compute,
) -> tuple[list[Finding], list[Fact], list[str]]:
    """The day's findings and facts with the sentiment ones (re)added, and any data gaps."""
    if day != today().isoformat():
        return findings, facts, []  # a past day keeps what its run saved
    findings = [f for f in findings if not f.id.startswith(f"{PREFIX}-")]
    facts = [f for f in facts if not (f.id.startswith(PREFIX) and f.id[len(PREFIX) :].isdigit())]
    snap = load()
    if snap is None:
        return findings, facts, ["market sentiment: no Sector Sentiment snapshot"]
    gaps: list[str] = []
    try:
        fg = compute(sorted({r.symbol for r in snap.stocks}))
    except Exception as exc:  # noqa: BLE001 - the stored needle still explains, dated in its text
        log.warning("sentiment: fear & greed recompute failed", exc_info=True)
        fg = snap.fear_greed
        gaps.append(f"market sentiment: Fear & Greed recompute failed, used the stored one: {exc}")

    at = snap.as_of.astimezone(ET)
    as_of = f"as of {at:%B} {at.day} {at:%H:%M} ET"
    names = {r.symbol: r.name for r in snap.stocks}
    texts = [READ]
    if fg is not None:
        texts.append(needle_text(fg))
        texts += [signal_text(c) for c in sorted(fg.components, key=_moved, reverse=True)]
    rows = sorted(snap.sectors, key=lambda s: abs(s.divergence), reverse=True)  # strongest first
    texts += [sector_text(s, names, as_of) for s in rows]
    new = [
        Fact(
            id=f"{PREFIX}{i}",
            text=t,
            numbers=numbers_in(t),
            provenance="data",
            source_title=SOURCE[0],
            source_url=SOURCE[1],
        )
        for i, t in enumerate(texts, 1)
    ]
    if fg is not None:
        was = f", from {fg.previous} the session before" if fg.previous is not None else ""
        claim = (
            f"Market sentiment: ARC's Fear & Greed needle closed at {fg.score} ({fg.zone}){was}."
        )
    else:
        claim = "Market sentiment: ARC's Sector Sentiment readings."
    finding = Finding(
        id=f"{PREFIX}-1",
        agent="alt",
        claim=claim,
        figure=fg.score if fg is not None else None,
        unit="level" if fg is not None else "",
        provenance="data",
        source_title=SOURCE[0],
        source_url=SOURCE[1],
        fact_ids=[f.id for f in new],
    )
    return findings + [finding], facts + new, gaps
