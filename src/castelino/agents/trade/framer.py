"""Framer: turns the user's sentence into a testable thesis with Yahoo tickers. Code checks every ticker
returns prices and makes one fact per ticker (its last year), plus up to 8 cited "why now" lines from one
search; the debate starts from these facts."""

from __future__ import annotations

from datetime import date, timedelta

from castelino.agents.trade import llm
from castelino.agents.trade.models import Frame, StepError
from castelino.agents.update.facts import facts_from_search
from castelino.agents.update.models import Fact
from castelino.agents.weekly.tools import SEARCH_SYSTEM, series_fact
from castelino.config import get_settings

SYSTEM = """You frame a trade idea so it can be tested with market data.
Return: a title of at most 6 words; the thesis in one sentence; 2 to 4 stand-ins, each a Yahoo Finance
ticker that exists (ETFs, indices like ^NSEI, FX like INR=X, futures like BZ=F): exactly one "subject"
(what the idea is about) and 1 to 3 "benchmark"s to compare it with; a horizon in months; 1 to 3 tests
that would prove the thesis wrong, each measurable with prices (e.g. "INDA's 26-week correlation with SMH
rises above 0.6"); and a web search query for why the idea matters this week.
Never make a buy or sell call."""


def _yahoo(ticker: str):
    from castelino.forecast.regime import _fetch_yf_close

    return _fetch_yf_close(ticker)


def _why_now(query: str, n: int, meter: llm.Meter, search, today: date) -> list[Fact]:
    """One cited search for why the idea matters this week; up to 8 cited lines become F facts."""
    from castelino.data import web_search

    try:
        text, cites = (search or web_search.search_cited)(
            SEARCH_SYSTEM,
            f"As of {today:%Y-%m-%d}: {query}",
            model=get_settings().trade_lab.search_model,
        )
    except Exception:  # noqa: BLE001 - "why now" is context; the debate can still search
        return []
    meter.add(llm.SEARCH_USD)
    found = facts_from_search("x", text, cites)[:8]
    return [f.model_copy(update={"id": f"F1.{n + k}"}) for k, f in enumerate(found, 1)]


def frame(
    idea_text: str, meter: llm.Meter, *, prices=None, search=None, today: date | None = None
) -> tuple[Frame, list[Fact]]:
    cfg = get_settings().trade_lab
    today = today or date.today()
    msgs = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"Today is {today:%Y-%m-%d}. Trade idea: {idea_text}"},
    ]
    errs: list[str] = []
    for _ in range(2):
        fr = llm.structured(
            "trade_framer", cfg.framer_model, msgs, Frame, meter, fallback=cfg.fallback_debate_model
        )
        facts, errs = [], []
        if sum(s.role == "subject" for s in fr.stand_ins) != 1 or not 2 <= len(fr.stand_ins) <= 4:
            errs.append("need exactly one subject and 2 to 4 stand-ins")
        if not 1 <= len(fr.prove_wrong) <= 3:
            errs.append("need 1 to 3 prove-wrong tests")
        for s in fr.stand_ins:
            try:
                px = (prices or _yahoo)(s.ticker)
                px = px[px.index >= str(today - timedelta(days=365))]
                fid = f"F1.{len(facts) + 1}"
                url = f"https://finance.yahoo.com/quote/{s.ticker}"
                facts.append(
                    series_fact(
                        fid,
                        px,
                        provider="yahoo",
                        sid=s.ticker,
                        title=f"Yahoo Finance {s.ticker}",
                        url=url,
                    )
                )
            except Exception as e:  # noqa: BLE001 - any fetch failure means the ticker is unusable
                errs.append(f"ticker {s.ticker} returned no Yahoo prices ({str(e)[:60]})")
        if not errs:
            return fr, facts + _why_now(fr.why_now_query, len(facts), meter, search, today)
        msgs += [
            {"role": "assistant", "content": fr.model_dump_json()},
            {"role": "user", "content": "Fix these and answer again: " + "; ".join(errs)},
        ]
    raise StepError("The framer couldn't set up the idea: " + "; ".join(errs))
