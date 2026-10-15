"""Research desks: two news desks (cited web search across many outlets) and the technical desk
(indicators and positioning computed by code), in parallel on gpt-6-luna. A news desk that cited fewer
than `breadth_min_domains` outlets gets `breadth_extra_calls` more calls aimed at outlets it hasn't used.
Findings whose numbers aren't in their cited facts are dropped, not repaired."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from urllib.parse import urlparse

from castelino.agents.trade import guard, llm, loop
from castelino.agents.trade.models import Brief, DeskReport, DeskRun, StepError, TradeIdea
from castelino.agents.trade.tools import TradeToolBox, prefix
from castelino.agents.update.models import Fact
from castelino.agents.weekly.board import Board
from castelino.config import get_settings

NEWS = """You are a news research desk for ARC Research. Answer your brief by searching widely: wires,
financial press, regional press for the country involved, company filings, central banks and official
statistics. Run several searches from different angles and outlets. Every claim must cite the fact ids your
searches returned; anything you can't confirm goes in unanswered. Plain English, no buy or sell calls."""
TECH = """You are ARC Research's technical desk. Explain the price action with technical indicators and
positioning: use technicals (RSI, MACD, moving averages, 52-week range, volatility, drawdown, relative
strength against a benchmark) and cot where a futures market applies. Every number must come from a fact
you cite. Plain English, no buy or sell calls."""
CODES = {"news_1": "NA", "news_2": "NB", "technical": "T"}
NEWS_TOOLS = ["web_search", "fred_series", "yahoo_prices"]
TECH_TOOLS = ["technicals", "cot", "yahoo_prices", "fred_series"]


def domains(facts: list[Fact]) -> list[str]:
    return sorted(
        {
            urlparse(f.source_url).netloc.removeprefix("www.")
            for f in facts
            if f.provenance == "reported" and f.source_url
        }
    )


def _yahoo(t):
    from castelino.forecast.regime import _fetch_yf_close

    return _fetch_yf_close(t)


def run(
    idea: TradeIdea, briefs: list[Brief], meter: llm.Meter, *, yahoo=None, search=None, cftc=None
) -> tuple[list[DeskRun], list[Fact]]:
    cfg = get_settings().trade_lab
    board = Board()
    known = "\n".join(f"[{f.id}] {f.text}" for f in idea.facts)
    thesis = idea.frame.thesis if idea.frame else idea.idea

    def one(b: Brief) -> tuple[DeskRun, list[Fact]]:
        news = b.desk != "technical"
        box = TradeToolBox(
            agent=f"trade_{b.desk}",
            prefix=prefix(CODES[b.desk], idea.round),
            allowed=NEWS_TOOLS if news else TECH_TOOLS,
            board=board,
            end=date.today(),
            max_calls=cfg.news_calls if news else cfg.technical_calls,
            yahoo=yahoo or _yahoo,
            search=search,
            cftc=cftc,
            search_model=cfg.search_model,
            meter=meter,
        )
        user = (
            f"Brief: {b.title}\n{b.brief}\nYou must answer:\n"
            + "\n".join(f"- {q}" for q in b.must_answer)
            + (f"\nTickers: {', '.join(b.tickers)}" if b.tickers else "")
            + f"\nThesis: {thesis}\nFacts already known:\n{known}"
        )
        ask = "Give your findings (each citing fact ids), a short summary, and what you could not answer."
        kw = dict(
            agent=f"trade_{b.desk}",
            model=cfg.desk_model,
            fallback=None,
            system=NEWS if news else TECH,
            box=box,
            meter=meter,
            schema=DeskReport,
            ask=ask,
        )
        try:
            out, _ = loop.run(user=user, **kw)
            if news and len(domains(box.facts)) < cfg.breadth_min_domains:
                box.max_calls = box.calls + cfg.breadth_extra_calls
                used = ", ".join(domains(box.facts)) or "none"
                more_user = (
                    f"{user}\n\nOutlets used so far: {used}. "
                    "Search outlets you have not used yet, then answer again."
                )
                more, _ = loop.run(user=more_user, **kw)
                out = DeskReport(
                    findings=out.findings + more.findings,
                    summary=more.summary,
                    unanswered=more.unanswered,
                )
            by = {f.id: f for f in idea.facts + box.facts}
            keep = [f for f in out.findings if not guard.cited_errors([f.claim], f.fact_ids, by)]
            own = [f for f in box.facts if f.id.startswith(box.prefix)]
            run_ = DeskRun(
                desk=b.desk,
                brief=b,
                report=out.model_copy(update={"findings": keep}),
                calls=box.calls,
                domains=domains(own),
            )
            return run_, own
        except Exception as e:  # noqa: BLE001 - one desk failing leaves the others' work
            return DeskRun(desk=b.desk, brief=b, error=str(e)[:300], calls=box.calls), []

    with ThreadPoolExecutor(3) as pool:
        results = list(pool.map(one, briefs))
    runs = [r for r, _ in results]
    if all(r.error for r in runs):
        raise StepError("All desks failed: " + "; ".join(f"{r.desk}: {r.error}" for r in runs))
    return runs, [f for _, fs in results for f in fs]
