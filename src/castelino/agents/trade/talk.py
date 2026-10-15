"""The user's two talks. Talk 1 (after the debate) and Talk 2 (about the draft): DeepSeek V4 Pro answers from
what this idea already holds, never searching; the OpenAI Decisions API says yes/no to "worth researching?"
(and in Talk 2, "is this an edit?"). Yes → a research item (Talk 2: for the next round) or an edit."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel

from castelino.agents.trade import decide, guard, llm
from castelino.agents.trade.models import ResearchItem, TalkMessage, TradeIdea
from castelino.agents.trade.store import now
from castelino.config import get_settings

NO_ANSWER = "I can't answer that from this idea's facts."
SYSTEM = """You are ARC, talking with ARC Research's editor about one trade idea. When the user writes to @Bull,
@Bear or @Moderator, answer as that participant from their own turns. Answer only from the debate, the
research and the facts below: never look anything up and never guess. Every number must come from a fact
you cite by id; if the facts can't answer, say so plainly. Under 120 words, no dashes, no buy or sell calls.
Also fill: research_question, one line a research desk could act on (for a claim the user made, phrase it as
something to verify); research_kind, claim if the user asserted something, else question; and, only when
the user asks to change the draft, edit_part (intro, bull, bear, question, technical, read or watch) and
edit_instruction; otherwise edit_part is none and edit_instruction is empty."""
Part = Literal["none", "intro", "bull", "bear", "question", "technical", "read", "watch"]


class Reply(BaseModel):
    answer: str
    fact_ids: list[str]
    research_question: str
    research_kind: Literal["claim", "question"]
    edit_part: Part
    edit_instruction: str


def context(idea: TradeIdea, talk: int) -> str:
    parts = [f"Idea: {idea.idea}"]
    if idea.frame:
        parts.append(
            f"Thesis: {idea.frame.thesis}\nProves it wrong: {'; '.join(idea.frame.prove_wrong)}"
        )
    parts.append(
        "Debate:\n"
        + "\n".join(
            f"{t.side} turn {t.round}: {t.text} [{', '.join(t.fact_ids)}]" for t in idea.turns
        )
    )
    if idea.moderation:
        parts.append("Still open: " + "; ".join(q.question for q in idea.moderation.open))
    if talk == 2:
        found = [
            f"{d.desk}: {f.claim} [{', '.join(f.fact_ids)}]"
            for r in idea.rounds
            for d in r.desks
            if d.report
            for f in d.report.findings
        ]
        parts.append("Desk findings:\n" + "\n".join(found))
        if idea.report:
            first = [
                f"{s.key}: {s.paragraphs[0][:160]}" for s in idea.report.sections if s.paragraphs
            ]
            parts.append("Draft sections: " + "; ".join(first))
    parts.append("Facts:\n" + "\n".join(f"[{f.id}] {f.text}" for f in idea.facts))
    recent = [m for m in idea.talk if m.talk == talk][-6:]
    if recent:
        parts.append("Recent messages:\n" + "\n".join(f"{m.role}: {m.text}" for m in recent))
    return "\n\n".join(parts)


def _errors(rep: Reply, by) -> list[str]:
    return guard.cited_errors([rep.answer], rep.fact_ids, by) + guard.dash_errors([rep.answer])


def reply(idea: TradeIdea, talk: int, to: str, message: str, meter: llm.Meter, *, decide_fn=None):
    cfg = get_settings().trade_lab
    ctx = context(idea, talk)
    msgs = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"{ctx}\n\nThe user (to {to}): {message}"},
    ]
    by = idea.fact_map()
    kw = dict(fallback=cfg.fallback_talk_model)
    rep = llm.structured("trade_talk", cfg.talk_model, msgs, Reply, meter, **kw)
    if errs := _errors(rep, by):
        msgs += [
            {"role": "assistant", "content": rep.model_dump_json()},
            {
                "role": "user",
                "content": "Fix: " + "; ".join(errs) + ". Use only numbers from cited facts.",
            },
        ]
        rep = llm.structured("trade_talk", cfg.talk_model, msgs, Reply, meter, **kw)
        if _errors(rep, by):
            rep = rep.model_copy(update={"answer": NO_ANSWER, "fact_ids": []})
    names = ["research", "edit"] if talk == 2 else ["research"]
    dec = (decide_fn or decide.decide)(ctx, message, names, meter)
    item, edit, action = None, None, ""
    if talk == 2 and dec.get("edit", 0.0) >= cfg.decide_threshold and rep.edit_part != "none":
        edit, action = (rep.edit_part, rep.edit_instruction or message), f"edit:{rep.edit_part}"
    elif dec.get("research", 0.0) >= cfg.decide_threshold:
        item = ResearchItem(
            id=uuid.uuid4().hex[:8],
            kind=rep.research_kind,
            text=rep.research_question or message,
            round=idea.round + (1 if talk == 2 else 0),
        )
        action = "research"
    t = now()
    out = [
        TalkMessage(talk=talk, role="user", to=to, text=message, at=t),
        TalkMessage(
            talk=talk,
            role="agent",
            to=to,
            text=rep.answer,
            fact_ids=rep.fact_ids,
            decision=dec,
            action=action,
            at=t,
        ),
    ]
    return out, item, edit
