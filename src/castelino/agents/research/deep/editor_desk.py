"""The editor desk: you question or edit one point; the agent that wrote it rethinks in its own saved thread
(or a fresh one briefed from its summary after compaction); Claude Haiku 5.5 rewrites only that point
(Sonnet 5.5 if it fails the number check twice); you approve or reject. An approval changes that point and
nothing else."""

from __future__ import annotations

from castelino.agents.research.deep import guard, store, sub_agent
from castelino.agents.research.deep.models import (
    AgentRun,
    AnswerDraft,
    Busy,
    Point,
    Proposal,
    RevisedPoint,
)
from castelino.agents.research.deep.tools import XBudget
from castelino.agents.trade import llm
from castelino.agents.update.models import Fact
from castelino.config import get_settings

ASK_EST = 0.15  # $ one rethink + one rewrite, checked against the cost cap before a question starts
OPEN = ("running", "pending")
REVISE = """You revise ONE point of an ARC Research report after its researcher re-checked it. Rewrite the
point to reflect the researcher's corrected finding and the analyst's request; change nothing else. Every
figure must be one of the cited facts' numbers, and fact_ids lists every fact the point uses. A figure
from an X post (source "@handle on X") must name that @handle in the same sentence. The headline stays one
sentence; change it only if the finding changed. No dashes as punctuation, no fact ids in the prose."""


def start(sid: str, point_id: str, text: str) -> Proposal:
    cap = get_settings().deep_research.cost_cap_usd
    with store.edit(sid) as s:
        point = s.point(point_id)
        if any(p.point_id == point_id and p.status in OPEN for p in s.proposals):
            raise Busy(f"{point_id} already has a question open")
        # one rethink per agent at a time: two would number their new facts from the same snapshot
        if any(p.agent == point.agent and p.status == "running" for p in s.proposals):
            raise Busy(
                f"Agent {point.agent} is still rechecking another point. Ask again when it's done."
            )
        if s.cost_usd + ASK_EST > cap:
            raise Busy(f"Cost cap: ${s.cost_usd:.2f} of ${cap:.2f} spent on this report")
        p = Proposal(
            n=len(s.proposals) + 1,
            point_id=point_id,
            agent=point.agent,
            text=text.strip(),
            base_version=point.version,
            before=point,
            created_at=store.now(),
        )
        s.proposals.append(p)
    return p


def _facts(ids: list[str], by: dict[str, Fact]) -> str:
    return "\n".join(
        f"[{i}] {by[i].text} — {by[i].source_title}" for i in dict.fromkeys(ids) if i in by
    )


def revise(
    point: Point, text: str, ans: AnswerDraft, by: dict[str, Fact], meter: llm.Meter
) -> tuple[RevisedPoint | None, str, list[str]]:
    """Two tries per model at the guard; without OPENROUTER_API_KEY every call runs on
    revise_openai_model."""
    cfg = get_settings().deep_research
    user = (
        f"The point now:\nHeadline: {point.headline}\nBody: {point.body}\n\n"
        f"The analyst said: {text}\n\nThe researcher's answer: {ans.answer}\n"
        f"Corrected finding: {ans.finding}\n\n"
        f"Facts you may cite:\n{_facts(point.fact_ids + ans.fact_ids, by)}"
    )
    errs: list[str] = []
    model = cfg.revise_model
    for model in dict.fromkeys([cfg.revise_model, cfg.revise_fallback_model]):
        msgs = [{"role": "system", "content": REVISE}, {"role": "user", "content": user}]
        for _ in range(2):
            out = llm.structured(
                "research_revise",
                model,
                msgs,
                RevisedPoint,
                meter,
                fallback=cfg.revise_openai_model,
            )
            out = out.model_copy(
                update={
                    "headline": guard.strip_ids(out.headline),
                    "body": guard.strip_ids(out.body),
                }
            )
            if not (errs := guard.point_errors(out, by)):
                return out, model, []
            msgs += [
                {"role": "assistant", "content": out.model_dump_json()},
                {"role": "user", "content": "Fix: " + "; ".join(errs)},
            ]
    return None, model, errs


def rethink(sid: str, n: int, meter: llm.Meter) -> None:
    cfg = get_settings().deep_research
    s = store.load(sid)
    prop = s.proposal(n)
    point, ar = s.point(prop.point_id), s.agent(prop.agent)
    budget = XBudget(cfg.x_posts_per_report - sum(a.x_posts for a in s.agents))
    r = sub_agent.answer(ar, point, prop.text, s.question, budget, meter)
    how = "Resumed" if ar.transcript else "Re-briefed"
    trail = [
        f"{how} {ar.letter}'s thread · {llm.label(cfg.agent_model)}",
        f"Checked with {r.calls} of {cfg.answer_tool_calls} extra tool calls · "
        f"{len(r.new_facts)} new facts",
    ]
    after, errs = None, []
    if r.answer.change:
        by = s.fact_map() | {f.id: f for f in r.new_facts}
        rev, model, errs = revise(point, prop.text, r.answer, by, meter)
        if rev:
            ids = [i for i in dict.fromkeys(rev.fact_ids) if i in by]
            after = point.model_copy(
                update={
                    "headline": rev.headline,
                    "body": rev.body,
                    "fact_ids": ids,
                    "version": point.version + 1,
                }
            )
            trail.append(f"Rewrote {point.id} only · {llm.label(model)} · passed the number check")
    with store.edit(sid) as x:
        owner = x.agent(prop.agent)
        owner.facts += (
            r.new_facts
        )  # kept even if you reject, so a later rethink never reuses their ids
        owner.transcript = r.transcript
        owner.tool_calls += r.calls
        owner.x_posts += r.x_posts
        p = x.proposal(n)
        p.answer, p.new_facts, p.trail = r.answer.answer, r.new_facts, trail
        if not r.answer.change:
            p.status = "answered"
        elif after:
            p.after, p.status = after, "pending"
        else:
            p.status = "failed"
            p.error = "The rewrite failed the number check: " + "; ".join(errs[:4])


def _note(ar: AgentRun, text: str) -> None:
    if ar.transcript is not None:
        ar.transcript.append({"role": "user", "content": text})


def approve(sid: str, n: int) -> None:
    with store.edit(sid) as s:
        p = s.proposal(n)
        if p.status != "pending":
            raise Busy(f"proposal {n} is {p.status}, not waiting for you")
        point = s.point(p.point_id)
        if point.version != p.base_version:
            raise Busy("The point changed after you asked. Ask again.")
        s.report.points = [p.after if q.id == point.id else q for q in s.report.points]
        p.status, p.decided_at = "approved", store.now()
        _note(s.agent(p.agent), "The analyst approved your revision.")


def reject(sid: str, n: int) -> None:
    with store.edit(sid) as s:
        p = s.proposal(n)
        if p.status != "pending":
            raise Busy(f"proposal {n} is {p.status}, not waiting for you")
        p.status, p.decided_at = "rejected", store.now()
        _note(s.agent(p.agent), "The analyst rejected your revision; the point stays as it was.")
