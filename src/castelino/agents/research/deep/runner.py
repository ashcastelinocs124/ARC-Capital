"""Runs research in background threads (at most session_concurrency sessions at once). The `run` step plans,
researches, checks the findings for gaps, runs one gap round and writes; a Retry reruns it and keeps every
agent that already has findings. Editor-desk questions run in their own threads, one per proposal, outside
the session's job slot. Steps that were running when the server stopped are marked for Retry at startup."""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from castelino.agents.research.deep import (
    charts,
    compact,
    critic,
    editor_desk,
    lead,
    store,
    sub_agent,
    synthesizer,
)
from castelino.agents.research.deep.models import (
    AgentRun,
    Brief,
    Busy,
    Job,
    Point,
    ResearchSession,
    StepError,
)
from castelino.agents.research.deep.tools import XBudget
from castelino.agents.trade import llm
from castelino.agents.weekly.board import Board
from castelino.config import get_settings

log = logging.getLogger(__name__)
LETTERS = "ABCDEFGHIJKLMNOP"
EST = {
    "run": 2.50,
    "compact": 0.0,
    "charts": 0.05,
    "add": 1.00,
}  # $ a step may cost, checked before it starts
RUNNING = {"run": "researching"}
_sem: threading.BoundedSemaphore | None = None
_sem_lock = threading.Lock()


def _semaphore() -> threading.BoundedSemaphore:
    global _sem
    with _sem_lock:
        if _sem is None:
            _sem = threading.BoundedSemaphore(get_settings().deep_research.session_concurrency)
        return _sem


def busy(s: ResearchSession) -> bool:
    return bool(s.job and s.job.state in ("queued", "running"))


def _board(s: ResearchSession) -> Board:
    b = Board()
    b.posts, b.facts = list(s.board), dict(s.board_facts)
    return b


def _round(sid: str, rnd: int, meter: llm.Meter) -> None:
    """Run every agent of a round that has no findings yet; each is saved the moment it finishes."""
    cfg = get_settings().deep_research
    s = store.load(sid)
    todo = [a for a in s.agents if a.round == rnd and not a.findings]
    board = _board(s)
    budget = XBudget(cfg.x_posts_per_report - sum(a.x_posts for a in s.agents))

    def one(a: AgentRun) -> None:
        done = sub_agent.research(a, s.question, board, budget, meter)
        with store.edit(sid) as x:
            x.agents = [done if b.letter == a.letter else b for b in x.agents]
            x.board, x.board_facts = list(board.posts), dict(board.facts)

    with ThreadPoolExecutor(max(1, cfg.agent_concurrency)) as pool:
        list(pool.map(one, todo))


def _add(sid: str, briefs: list[Brief], rnd: int) -> None:
    model = get_settings().deep_research.agent_model
    with store.edit(sid) as x:
        k = len(x.agents)
        x.agents += [
            AgentRun(letter=LETTERS[k + i], round=rnd, brief=b, model=model)
            for i, b in enumerate(briefs)
        ]


def _run(sid: str, meter: llm.Meter) -> None:
    cfg = get_settings().deep_research
    if not store.load(sid).agents:
        _add(sid, lead.plan(store.load(sid), meter), 1)
    _round(sid, 1, meter)
    s = store.load(sid)
    if not any(a.findings for a in s.agents if a.round == 1):
        first = next((a.error for a in s.agents if a.error), "no findings")
        raise StepError(f"Every research agent failed. First error: {first}")
    gaps: list[str] = []
    if not any(a.round == 2 for a in s.agents):
        crit = critic.review(s, meter)
        if not crit.done and crit.gaps:
            if cfg.gap_rounds:
                _add(sid, lead.plan_gaps(s, crit.gaps, meter), 2)
            else:
                gaps = crit.gaps
    _round(sid, 2, meter)
    with store.edit(sid) as x:
        x.status = "writing"
    s = store.load(sid)
    rep = synthesizer.write(s, meter)
    rep = rep.model_copy(update={"points": _charted(rep.points, s, meter), "gaps_remaining": gaps})
    with store.edit(sid) as x:
        x.report = rep
        x.status = "complete"


def _charted(points: list[Point], s: ResearchSession, meter: llm.Meter) -> list[Point]:
    """The points with a chart from their cited facts (charts.py); a point it can't chart keeps none."""
    drawn = charts.chart_points(points, s.fact_map(), meter)
    return [p.model_copy(update={"chart": drawn.get(p.id, p.chart)}) for p in points]


def _charts(sid: str, meter: llm.Meter) -> None:
    """Chart the points that have none yet: reports written before point charts, or a failed chart call."""
    s = store.load(sid)
    todo = [p for p in (s.report.points if s.report else []) if p.chart is None]
    if not todo:
        return
    new = {p.id: p for p in _charted(todo, s, meter)}
    with store.edit(sid) as x:
        x.report.points = [new.get(p.id, p) if p.chart is None else p for p in x.report.points]


def _angles(sid: str, meter: llm.Meter) -> None:
    """The last addition: plan its agents (round 2 + n), research, write new points, chart them, append.
    The points already in the report are never rewritten; a Retry keeps agents that have findings."""
    add = store.load(sid).additions[-1]
    with store.edit(sid) as x:
        x.additions[-1].status, x.additions[-1].error = "running", ""
    try:
        if not any(a.round == add.round for a in store.load(sid).agents):
            _add(sid, lead.plan_angles(store.load(sid), add.text, meter), add.round)
        _round(sid, add.round, meter)
        s = store.load(sid)
        new = [a for a in s.agents if a.round == add.round]
        if not any(a.findings for a in new):
            first = next((a.error for a in new if a.error), "no findings")
            raise StepError(f"Every new research agent failed. First error: {first}")
        points = synthesizer.write_more(s, [a.letter for a in new], add.n, meter)
        points = _charted(points, s, meter)
        with store.edit(sid) as x:
            x.report.points += points
            x.additions[-1].status = "done"
    except Exception as e:
        with store.edit(sid) as x:
            x.additions[-1].status, x.additions[-1].error = "failed", str(e)[:300]
        raise


STEPS = {"run": _run, "compact": compact.compact, "charts": _charts, "add": _angles}


def _execute(sid: str, step: str) -> None:
    with _semaphore():
        with store.edit(sid) as x:
            x.job = Job(step=step, state="running", at=store.now())
            x.status = RUNNING.get(step, x.status)
        meter, state, msg = llm.Meter(), "done", ""
        try:
            STEPS[step](sid, meter)
        except Exception as e:  # noqa: BLE001 - shown with a Retry button
            log.exception("research %s: %s failed", sid, step)
            state, msg = "failed", str(e)[:400]
        with store.edit(sid) as x:
            x.cost_usd = round(x.cost_usd + meter.total, 4)
            x.fallbacks += meter.fallbacks
            x.job = Job(step=step, state=state, message=msg, at=store.now())


def submit(sid: str, step: str = "run", *, sync: bool = False) -> None:
    cap = get_settings().deep_research.cost_cap_usd
    with store.edit(sid) as x:
        if busy(x):
            raise Busy(f"{x.job.step} is still running")
        if x.cost_usd + EST[step] > cap:
            x.job = Job(
                step=step,
                state="failed",
                at=store.now(),
                message=f"Cost cap: ${x.cost_usd:.2f} spent; this step needs about "
                f"${EST[step]:.2f} and the cap is ${cap:.2f} per report.",
            )
            return
        x.job = Job(step=step, state="queued", at=store.now())
    if sync:
        _execute(sid, step)
    else:
        name = f"research-{sid}-{step}"
        threading.Thread(target=_execute, args=(sid, step), daemon=True, name=name).start()


def _ask(sid: str, n: int) -> None:
    meter = llm.Meter()
    try:
        editor_desk.rethink(sid, n, meter)
    except Exception as e:  # noqa: BLE001 - the proposal shows why, and you can ask again
        log.exception("research %s: ask %s failed", sid, n)
        with store.edit(sid) as x:
            p = x.proposal(n)
            p.status, p.error = "failed", str(e)[:300]
    with store.edit(sid) as x:
        x.cost_usd = round(x.cost_usd + meter.total, 4)
        x.fallbacks += meter.fallbacks
        x.proposal(n).trail.append(f"Cost ${meter.total:.2f}")


def submit_ask(sid: str, n: int, *, sync: bool = False) -> None:
    if sync:
        _ask(sid, n)
    else:
        name = f"research-{sid}-ask{n}"
        threading.Thread(target=_ask, args=(sid, n), daemon=True, name=name).start()


def maybe_compact(s: ResearchSession) -> None:
    if compact.due(s) and not busy(s):
        try:
            submit(s.id, "compact")
        except Busy:
            pass


def recover_interrupted() -> int:
    n = 0
    for s in store.all():
        running = [*s.proposals, *s.additions]
        if not (busy(s) or any(p.status == "running" for p in running)):
            continue
        with store.edit(s.id) as x:
            if busy(x):
                x.job = x.job.model_copy(
                    update={
                        "state": "interrupted",
                        "at": store.now(),
                        "message": "The server restarted while this step ran.",
                    }
                )
            for p in x.proposals:
                if p.status == "running":
                    p.status = "failed"
                    p.error = "The server restarted while this ran. Ask again."
            for a in x.additions:
                if a.status == "running":
                    a.status, a.error = "failed", "The server restarted while this ran. Retry it."
        n += 1
    return n
