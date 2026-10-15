"""Orchestrator (gpt-6-sol): turns the debate, the user's talk and the research list into exactly three
briefs: two news desks and the technical desk. Every research-list item must land in a brief."""

from __future__ import annotations

from castelino.agents.trade import llm
from castelino.agents.trade.models import Brief, Briefs, ResearchItem, StepError, TradeIdea
from castelino.config import get_settings

SYSTEM = """You run ARC Research's research desks for one trade idea. Write exactly three briefs:
news_1 and news_2 (news desks that search widely across outlets; split the work so they don't overlap) and
technical (a desk that explains the price action with technical indicators and positioning).
Every research item listed must be covered: put its id in item_ids of the desk that answers it and turn it
into a must_answer question. The user's claims are to be verified with sources, never assumed true.
The technical brief names 1 to 4 Yahoo tickers, the subject first; the news briefs have no tickers."""
ORDER = ("news_1", "news_2", "technical")


def active_items(idea: TradeIdea) -> list[ResearchItem]:
    return [r for r in idea.research if r.round == idea.round and not r.removed]


def _yahoo(t):
    from castelino.forecast.regime import _fetch_yf_close

    return _fetch_yf_close(t)


def _context(idea: TradeIdea, items: list[ResearchItem]) -> str:
    fr = idea.frame
    parts = [f"Thesis: {fr.thesis}" if fr else f"Idea: {idea.idea}"]
    if fr:
        parts.append("Tickers: " + ", ".join(f"{s.ticker} ({s.role})" for s in fr.stand_ins))
    parts.append("Debate:\n" + "\n".join(f"{t.side} {t.round}: {t.text}" for t in idea.turns))
    if idea.moderation:
        parts.append("Open questions: " + "; ".join(q.question for q in idea.moderation.open))
    parts.append("The user's talk:\n" + "\n".join(f"{m.role}: {m.text}" for m in idea.talk))
    parts.append("Research items:\n" + "\n".join(f"[{i.id}] ({i.kind}) {i.text}" for i in items))
    if idea.round > 1:
        prev = [b for r in idea.rounds if r.n < idea.round for b in r.briefs]
        parts.append(
            "Earlier rounds' briefs (don't repeat them):\n"
            + "\n".join(f"{b.desk}: {b.brief}" for b in prev)
        )
    return "\n\n".join(parts)


def plan(idea: TradeIdea, meter: llm.Meter, *, prices=None) -> list[Brief]:
    cfg = get_settings().trade_lab
    items = active_items(idea)
    msgs = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": _context(idea, items)},
    ]
    errs: list[str] = []
    for _ in range(2):
        out = llm.structured("trade_orchestrator", cfg.orchestrator_model, msgs, Briefs, meter)
        errs = []
        got = sorted(b.desk for b in out.briefs)
        if got != sorted(ORDER):
            errs.append(f"need exactly one brief each for {', '.join(ORDER)}, got {got}")
        covered = {i for b in out.briefs for i in b.item_ids}
        errs += [f"research item {i.id} is in no brief" for i in items if i.id not in covered]
        tech = next((b for b in out.briefs if b.desk == "technical"), None)
        if tech is not None:
            if not 1 <= len(tech.tickers) <= 4:
                errs.append("the technical brief needs 1 to 4 tickers")
            for t in tech.tickers:
                try:
                    (prices or _yahoo)(t)
                except Exception:  # noqa: BLE001
                    errs.append(f"ticker {t} returned no Yahoo prices")
        if not errs:
            return sorted(out.briefs, key=lambda b: ORDER.index(b.desk))
        msgs += [
            {"role": "assistant", "content": out.model_dump_json()},
            {"role": "user", "content": "Fix these and answer again: " + "; ".join(errs)},
        ]
    raise StepError("The orchestrator's briefs failed their checks: " + "; ".join(errs))
