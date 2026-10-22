"""The daily build: today's facts for one consultant, in two layers.

1. Code fetches the watchlist (no model): each company's price history and latest reported quarter, and
   each FRED/Yahoo series, so the same series grow day after day.
2. Deep Research's tool loop covers news and alt data (web search, Polymarket, Ramp, OpenRouter, ARC's
   adoption index; X only when X_BEARER_TOKEN is set), capped at `build_tool_calls`.

Every fact id is `{code}-{yyyymmdd}-{n}`. The first build also writes the first thesis."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from castelino.agents import themes
from castelino.agents.consultants import store, thesis
from castelino.agents.consultants.models import Consultant, HistoryLine, Thesis
from castelino.agents.research.deep import sub_agent
from castelino.agents.research.deep.models import AgentRun, Brief
from castelino.agents.research.deep.tools import XBudget
from castelino.agents.trade import llm
from castelino.agents.update import calendar
from castelino.agents.update.background import default_close, stock_fact
from castelino.agents.update.models import Fact
from castelino.agents.weekly.board import Board
from castelino.config import get_settings


def _prefix(c: Consultant, day: date) -> str:
    return f"{c.code}-{day:%Y%m%d}-"


def _earnings_fact(fid: str, name: str, ticker: str, eps: tuple, day: date) -> Fact:
    actual, est, surprise = eps
    text = f"{name} ({ticker}) reported EPS of {actual}"
    if est is not None:
        text += f" against an estimate of {est}"
    if surprise is not None:
        text += f", a {surprise}% surprise"
    return Fact(
        id=fid,
        text=text + f" (latest quarter, as of {day:%b %d, %Y}).",
        numbers=[x for x in (actual, est, surprise) if x is not None],
        provenance="data",
        source_title=f"Yahoo Finance earnings history: {ticker}",
        source_url=f"https://finance.yahoo.com/quote/{ticker}",
    )


def watchlist_facts(
    c: Consultant,
    day: date,
    *,
    close=default_close,
    series=themes.fetch_series,
    eps=calendar.yahoo_eps,
) -> tuple[list[Fact], list[str]]:
    """Code-made facts for the watchlist. One failed item is a gap, never an exception."""
    facts: list[Fact] = []
    gaps: list[str] = []

    def fid() -> str:
        return f"{_prefix(c, day)}{len(facts) + 1}"

    for co in c.watchlist.companies:
        try:
            facts.append(stock_fact(fid(), co.ticker, co.name, close(co.ticker), day))
        except Exception as e:  # noqa: BLE001 - one ticker never sinks the build
            gaps.append(f"{co.name} ({co.ticker}) prices: {str(e)[:80]}")
        try:
            if got := eps(co.ticker, day):
                facts.append(_earnings_fact(fid(), co.name, co.ticker, got, day))
        except Exception as e:  # noqa: BLE001
            gaps.append(f"{co.name} ({co.ticker}) earnings: {str(e)[:80]}")
    start = datetime.combine(day - timedelta(days=365), datetime.min.time())
    for s in c.watchlist.series:
        provider, sid = s.split(":", 1)
        try:
            facts.append(series(provider, sid, fid(), start))
        except Exception as e:  # noqa: BLE001
            gaps.append(f"{s}: {str(e)[:80]}")
    return facts, gaps


def research_facts(
    c: Consultant, day: date, prior: list[Fact], meter: llm.Meter, th: Thesis | None
) -> tuple[list[Fact], str | None]:
    """Run the research loop seeded with `prior`; its box numbers new facts on from them. Findings are
    ignored: the consultant keeps facts, and the thesis is its own reading of them."""
    cfg = get_settings().consultants
    brief = "Find today's news and data on this topic."
    if c.watchlist.queries:
        brief += " Start from these searches: " + "; ".join(c.watchlist.queries) + "."
    if th:
        brief += f" The consultant is watching: {th.lean.text} {th.change_mind.text}"
    ar = AgentRun(
        letter=_prefix(c, day),
        brief=Brief(name=c.topic, angle="today's news and alt data", brief=brief),
        facts=prior,
    )
    out = sub_agent.research(
        ar,
        c.topic,
        Board(),
        XBudget(cfg.x_posts_per_day),
        meter,
        max_calls=cfg.build_tool_calls,
        consult=False,  # its own file must come from fresh sources, never a consult answer
    )
    return out.facts, out.error


def build(slug: str, day: date, meter: llm.Meter) -> list[str]:
    """Build one consultant's day (once; a failed day can be rebuilt). Returns its gaps; never raises on a
    data or model failure — the consultant is marked failed with the reason instead."""
    c = store.load(slug)
    ds = day.isoformat()
    if store.day_log(slug, ds).built and c.status not in ("failed", "building"):  # Build now reruns
        return []
    facts, gaps = watchlist_facts(c, day)
    th = store.read_thesis(slug)
    try:
        all_facts, err = research_facts(c, day, facts, meter, th)
    except Exception as e:  # noqa: BLE001
        all_facts, err = facts, str(e)[:200]
    if err and len(all_facts) == len(facts):
        gaps.append(f"research: {err}")
    store.write_facts(slug, ds, all_facts)

    status, error = "active", None
    if not all_facts:
        status, error = "failed", ("no facts today: " + "; ".join(gaps))[:300]
    elif th is None:
        try:
            t = thesis.write(c.topic, all_facts, "", None, ds, meter)
            store.write_thesis(slug, t)
            store.append_history(
                slug,
                HistoryLine(
                    day=ds,
                    kind="start",
                    verdict="started",
                    after=t.happening.text,
                    reason=f"First view from {len(all_facts)} facts.",
                ),
            )
        except Exception as e:  # noqa: BLE001
            status, error = "failed", f"first thesis failed: {e}"[:300]
    with store.edit(slug) as x:
        if x.status != "paused":
            x.status, x.error = status, error
    with store.edit_day(slug, ds) as d:
        d.built = True
        d.notes += gaps
    return gaps
