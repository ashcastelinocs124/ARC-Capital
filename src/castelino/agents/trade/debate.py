"""Bull and bear: each builds its case with its own tools (opening), then answers the other side twice.
Bull and bear write each round in parallel. A turn whose numbers aren't in the facts it cites gets one fix,
then the step fails. The moderator lists what's settled and what's open, and never names a winner."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date

from castelino.agents.trade import guard, llm, loop
from castelino.agents.trade.models import (
    NAMES,
    Frame,
    Moderation,
    StepError,
    Turn,
    TurnDraft,
    instruments,
)
from castelino.agents.trade.tools import TradeToolBox, prefix
from castelino.agents.update.models import Fact
from castelino.agents.weekly.board import Board
from castelino.config import get_settings

SIDE = """You are the {side} in a debate about a trade idea for ARC Research. Argue the {stance} case as
strongly as the evidence allows. Use your tools to find data; every number you write must come from a fact
and you must cite those fact ids. Plain English, under 120 words, no dashes as punctuation, never a buy or
sell recommendation. {names}
Thesis: {thesis}
Instruments: {tickers}. Horizon: {horizon} months. What would prove it wrong: {wrong}"""
BULL = SIDE.replace("{side}", "bull").replace("{stance}", "supporting").replace("{names}", NAMES)
BEAR = SIDE.replace("{side}", "bear").replace("{stance}", "opposing").replace("{names}", NAMES)
MODERATOR = f"""You moderate a bull/bear debate for ARC Research. List what both sides' evidence settles
(cite fact ids) and 2 to 4 questions the debate left open, each with why it matters. Do not pick a winner.
{NAMES}"""
ROUNDS = ("opening", "first rebuttal", "second rebuttal")


def _facts_text(facts: list[Fact]) -> str:
    return "\n".join(f"[{f.id}] {f.text} ({f.source_title})" for f in facts)


def _yahoo(t):
    from castelino.forecast.regime import _fetch_yf_close

    return _fetch_yf_close(t)


def run(
    frame: Frame,
    facts: list[Fact],
    meter: llm.Meter,
    *,
    attempt: int = 1,
    yahoo=None,
    search=None,
) -> tuple[list[Turn], list[Fact]]:
    cfg = get_settings().trade_lab
    prompts = {"bull": BULL, "bear": BEAR}
    codes = {"bull": "B", "bear": "R"}
    boxes = {
        side: TradeToolBox(
            agent=f"trade_{side}",
            prefix=prefix(codes[side], attempt),
            allowed=["yahoo_prices", "fred_series", "technicals", "polymarket_odds", "web_search"],
            board=Board(),
            end=date.today(),
            max_calls=cfg.opening_calls,
            yahoo=yahoo or _yahoo,
            search=search,
            search_model=cfg.search_model,
            meter=meter,
        )
        for side in ("bull", "bear")
    }
    tickers = instruments(frame.stand_ins)
    system = {
        side: prompts[side].format(
            thesis=frame.thesis,
            tickers=tickers,
            horizon=frame.horizon_months,
            wrong="; ".join(frame.prove_wrong),
        )
        for side in prompts
    }
    turns: list[Turn] = []

    def known() -> list[Fact]:
        return facts + boxes["bull"].facts + boxes["bear"].facts

    def one(side: str, rnd: int) -> Turn:
        box = boxes[side]
        other = "bear" if side == "bull" else "bull"
        last = next((t for t in reversed(turns) if t.side == other), None)
        user = f"Facts so far:\n{_facts_text(known())}\n\n"
        if last:
            user += f"The {other}'s last turn: {last.text}\n\n"
        ask = f"Write your {ROUNDS[rnd]} (under 120 words) and list the fact ids you used."
        kw = dict(
            agent=f"trade_{side}",
            model=cfg.debate_model,
            fallback=cfg.fallback_debate_model,
            schema=TurnDraft,
            meter=meter,
        )
        out, msgs = loop.run(system=system[side], user=user, box=box, ask=ask, **kw)
        by = {f.id: f for f in known()}
        if errs := guard.cited_errors([out.text], out.fact_ids, by) + guard.dash_errors([out.text]):
            out = loop.fix(msgs=msgs, out=out, errors=errs, **kw)
            errs = guard.cited_errors([out.text], out.fact_ids, by) + guard.dash_errors([out.text])
            if errs:
                raise StepError(
                    f"The {side}'s {ROUNDS[rnd]} has numbers with no source: " + "; ".join(errs)
                )
        return Turn(side=side, round=rnd, text=out.text, fact_ids=out.fact_ids)

    with ThreadPoolExecutor(2) as pool:
        for rnd in range(3):
            if rnd:
                for b in boxes.values():
                    b.max_calls = b.calls + cfg.rebuttal_calls
            bull, bear = pool.map(lambda s, r=rnd: one(s, r), ("bull", "bear"))
            turns += [bull, bear]
    return turns, boxes["bull"].facts + boxes["bear"].facts


def moderate(frame: Frame, turns: list[Turn], by: dict[str, Fact], meter: llm.Meter) -> Moderation:
    cfg = get_settings().trade_lab
    said = "\n".join(
        f"{t.side} {ROUNDS[t.round]}: {t.text} [{', '.join(t.fact_ids)}]" for t in turns
    )
    user = f"Thesis: {frame.thesis}\n\nDebate:\n{said}\n\nFacts:\n{_facts_text(list(by.values()))}"
    msgs = [{"role": "system", "content": MODERATOR}, {"role": "user", "content": user}]
    errs: list[str] = []
    for _ in range(2):
        mod = llm.structured(
            "trade_moderator",
            cfg.debate_model,
            msgs,
            Moderation,
            meter,
            fallback=cfg.fallback_debate_model,
        )
        errs = [f"unknown fact {i}" for s in mod.settled for i in s.fact_ids if i not in by]
        if not 2 <= len(mod.open) <= 4:
            errs.append("need 2 to 4 open questions")
        if not errs:
            return mod
        msgs += [
            {"role": "assistant", "content": mod.model_dump_json()},
            {"role": "user", "content": "Fix: " + "; ".join(errs)},
        ]
    raise StepError("The moderator's summary failed its checks: " + "; ".join(errs))
