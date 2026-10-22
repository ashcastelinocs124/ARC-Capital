"""One research agent: a tool loop (trade/loop.py, Chat Completions, so it runs on DeepSeek via OpenRouter
and on OpenAI alike) over the ResearchToolBox, then findings. Its whole message list is saved, so the editor
desk can resume it later; after compaction a fresh thread is briefed from its summary instead."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from castelino.agents.research.deep import guard
from castelino.agents.research.deep.models import (
    AgentRun,
    AnswerDraft,
    Finding,
    FindingDrafts,
    Point,
)
from castelino.agents.research.deep.tools import ResearchToolBox, XBudget, allowed_tools
from castelino.agents.trade import llm, loop
from castelino.agents.update.models import Fact
from castelino.agents.weekly.board import Board
from castelino.config import get_settings

SYSTEM = """You are researcher {letter} ({name}) on ARC Research's deep-research team.
The team's research question: {question}
Your angle: {angle}
Your brief: {brief}
Today is {today}.
Rules:
- Every number you rely on must come from a tool result, cited by its fact id (like {letter}3).
- Use the most recent data: search for the latest release of each survey or series first, with the year
  in the query. Use a figure from before {fresh} only when nothing newer exists, and say so. Every
  finding says when its figures are from.
- Prefer the data tools for anything measurable: the Ramp AI Index (U.S. business AI adoption by vendor,
  industry and size, monthly to the latest month, and weekly token spend by model maker), OpenRouter's
  rankings (the most-used models now, open-weight or closed), ARC's own AI Adoption Index (52 U.S.
  companies scored from SEC filings, AI hiring and spend), FRED, Yahoo, BLS and Polymarket. Use web
  search for studies, surveys, causes and context.
- x_search reaches only the last 7 days of X. A post is what its author said, not a fact: use it as
  "@handle says ...".
- Read the board before you finish, and post anything other researchers could use.
- You have at most {calls} tool calls. Stop when your angle is answered."""

FINDINGS_ASK = """Now give your findings: at most 6, each one claim with the ids of the facts it rests on
(only ids from tool results above)."""

ANSWER_ASK = """The analyst asks about a point of the report that rests on your research.
Point: {headline}
{body}
Facts it cites: {fact_ids}
The analyst says: "{text}"
You may make up to {calls} more tool calls to check. Then answer in 2 to 4 sentences. Set change to true
only if the point should change: a figure is out of date or wrong, a claim is missing or overstated, or the
analyst asks for an edit your facts support. Then finding is the corrected claim and fact_ids lists every
fact the corrected point should cite. If the point stands, change is false, finding is "" and fact_ids
lists the facts behind your answer."""


@dataclass
class Rethink:
    answer: AnswerDraft
    new_facts: list[Fact]
    transcript: list[dict]
    calls: int
    x_posts: int


def _box(
    ar: AgentRun, board: Board, meter: llm.Meter, *, max_calls: int, x_budget: XBudget
) -> ResearchToolBox:
    cfg = get_settings().deep_research
    box = ResearchToolBox(
        agent=f"{ar.letter} · {ar.brief.name}",
        prefix=ar.letter,
        allowed=allowed_tools(),
        board=board,
        end=date.today(),
        max_calls=max_calls,
        meter=meter,
        search_model=cfg.search_model,
        x_budget=x_budget,
        x_per_call=cfg.x_posts_per_call,
    )
    box.facts = list(ar.facts)
    return box


def _system(ar: AgentRun, question: str, calls: int | None = None) -> str:
    b = ar.brief
    return SYSTEM.format(
        letter=ar.letter,
        name=b.name,
        question=question,
        angle=b.angle,
        brief=b.brief,
        today=date.today(),
        fresh=guard.fresh_year(date.today()),
        calls=calls or get_settings().deep_research.max_tool_calls,
    )


def _model_used(meter: llm.Meter, agent: str) -> str:
    cfg = get_settings().deep_research
    fell = any(n.startswith(f"{agent}: ") for n in meter.fallbacks)
    return cfg.agent_fallback_model if fell else cfg.agent_model


def research(
    ar: AgentRun,
    question: str,
    board: Board,
    x_budget: XBudget,
    meter: llm.Meter,
    max_calls: int | None = None,
) -> AgentRun:
    """Research one brief. Never raises: a failure comes back as the run's error. `max_calls` overrides the
    configured cap (topic consultants' daily build uses fewer)."""
    cfg = get_settings().deep_research
    agent = f"research_agent:{ar.letter}"
    calls = max_calls or cfg.max_tool_calls
    box = _box(ar, board, meter, max_calls=calls, x_budget=x_budget)
    try:
        out, msgs = loop.run(
            agent=agent,
            model=cfg.agent_model,
            fallback=cfg.agent_fallback_model,
            system=_system(ar, question, calls),
            user="Start your research.",
            box=box,
            meter=meter,
            schema=FindingDrafts,
            ask=FINDINGS_ASK,
        )
    except Exception as e:  # noqa: BLE001 - one failed agent never stops the others
        return ar.model_copy(
            update={
                "error": str(e)[:300],
                "tool_calls": box.calls,
                "x_posts": box.x_posts,
                "facts": box.facts,
            }
        )
    known = {f.id for f in box.facts}
    findings = [
        Finding(
            id=f"{ar.letter}-f{k}", claim=d.claim, fact_ids=[i for i in d.fact_ids if i in known]
        )
        for k, d in enumerate(out.findings[:6], 1)
    ]
    findings = [f for f in findings if f.fact_ids]
    return ar.model_copy(
        update={
            "model": _model_used(meter, agent),
            "tool_calls": box.calls,
            "x_posts": box.x_posts,
            "facts": box.facts,
            "findings": findings,
            "transcript": [*msgs, {"role": "assistant", "content": out.model_dump_json()}],
            "error": None if findings else "no findings that cite facts from its tool results",
        }
    )


def answer(
    ar: AgentRun, point: Point, text: str, question: str, x_budget: XBudget, meter: llm.Meter
) -> Rethink:
    """The owner rechecks one point: its own saved thread, or a fresh one briefed from its summary."""
    cfg = get_settings().deep_research
    box = _box(ar, Board(), meter, max_calls=cfg.answer_tool_calls, x_budget=x_budget)
    ask = ANSWER_ASK.format(
        headline=point.headline,
        body=point.body,
        fact_ids=", ".join(point.fact_ids),
        text=text,
        calls=cfg.answer_tool_calls,
    )
    if ar.transcript:
        system, history = "", ar.transcript
    else:  # compacted: the summary and the facts the report cites
        facts = "\n".join(f"[{f.id}] {f.text} — {f.source_title}" for f in ar.facts)
        system = (
            f"{_system(ar, question)}\n\nWhat you found earlier:\n{ar.summary or ''}\n\n"
            f"Your facts:\n{facts}"
        )
        history = None
    out, msgs = loop.run(
        agent=f"research_agent:{ar.letter}",
        model=cfg.agent_model,
        fallback=cfg.agent_fallback_model,
        system=system,
        user=ask,
        box=box,
        meter=meter,
        schema=AnswerDraft,
        ask="Give your answer now.",
        history=history,
    )
    have = {f.id for f in ar.facts}
    new = [f for f in box.facts if f.id not in have]
    known = have | {f.id for f in new}
    out = out.model_copy(update={"fact_ids": [i for i in out.fact_ids if i in known]})
    return Rethink(
        answer=out,
        new_facts=new,
        transcript=[*msgs, {"role": "assistant", "content": out.model_dump_json()}],
        calls=box.calls,
        x_posts=box.x_posts,
    )
