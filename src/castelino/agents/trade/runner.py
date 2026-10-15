"""Runs Trade Lab's steps in background threads (at most trade_lab.concurrency ideas at once). Each step
saves through store.edit(); a failed or interrupted step reruns from its start, finished steps never rerun.
The $5 cap stops a step whose estimate would cross it. Talks and "another idea" run in the request."""

from __future__ import annotations

import logging
import threading

from castelino.agents.trade import (
    chartist,
    debate,
    desks,
    editor,
    framer,
    llm,
    orchestrator,
    publish,
    store,
    talk,
)
from castelino.agents.trade.models import (
    SECTIONS,
    ChartOption,
    Frame,
    Job,
    ResearchItem,
    StepError,
    TalkMessage,
    TradeIdea,
)
from castelino.config import get_settings

log = logging.getLogger(__name__)
# $ per step (round 1 estimates from the cost model in the spec's cost.py)
EST = {"frame_debate": 0.40, "rerun_debate": 0.30, "research": 0.80, "write": 1.00}
RUNNING = {
    "frame_debate": "framing",
    "rerun_debate": "debating",
    "research": "researching",
    "write": "writing",
}
_sem: threading.BoundedSemaphore | None = None
_sem_lock = threading.Lock()


class Busy(RuntimeError):  # noqa: N818 - reads as "runner.Busy" at call sites
    pass


def _semaphore() -> threading.BoundedSemaphore:
    global _sem
    with _sem_lock:
        if _sem is None:
            _sem = threading.BoundedSemaphore(get_settings().trade_lab.concurrency)
        return _sem


def busy(idea: TradeIdea) -> bool:
    return bool(idea.job and idea.job.state in ("queued", "running"))


# ── steps ────────────────────────────────────────────────────────────────────
def _debate(idea_id: str, meter: llm.Meter) -> None:
    idea = store.load(idea_id)
    turns, new = debate.run(idea.frame, idea.facts, meter, attempt=idea.debate_attempt)
    mod = debate.moderate(idea.frame, turns, {f.id: f for f in idea.facts + new}, meter)
    with store.edit(idea_id) as i:
        if i.turns:
            i.turns_history.append(i.turns)
        i.turns, i.moderation = turns, mod
        i.facts += new
        i.research = [r for r in i.research if r.kind != "moderator"] + [
            ResearchItem(id=f"m{i.debate_attempt}.{k}", kind="moderator", text=q.question, round=1)
            for k, q in enumerate(mod.open, 1)
        ]
        i.status = "awaiting_view"


def _frame_debate(idea_id: str, meter: llm.Meter) -> None:
    fr, facts = framer.frame(store.load(idea_id).idea, meter)
    with store.edit(idea_id) as i:
        i.frame, i.facts, i.status = fr, facts, "debating"
    _debate(idea_id, meter)


def _rerun_debate(idea_id: str, meter: llm.Meter) -> None:
    with store.edit(idea_id) as i:
        i.debate_attempt += 1
    _debate(idea_id, meter)


def _research(idea_id: str, meter: llm.Meter) -> None:
    briefs = orchestrator.plan(store.load(idea_id), meter)
    with store.edit(idea_id) as i:
        i.current().briefs = briefs
    runs, facts = desks.run(store.load(idea_id), briefs, meter)
    with store.edit(idea_id) as i:
        i.current().desks = runs
        have = {f.id for f in i.facts}
        i.facts += [f for f in facts if f.id not in have]
    options, cfacts = chartist.propose(store.load(idea_id), meter)
    with store.edit(idea_id) as i:
        i.current().options = options
        i.facts += cfacts
        i.status = "awaiting_charts"


def _write(idea_id: str, meter: llm.Meter) -> None:
    idea = store.load(idea_id)
    base = publish.current_text(idea) if idea.round > 1 and idea.substack else None
    rep = editor.write(idea, meter, base_draft=base)
    with store.edit(idea_id) as i:
        i.report = rep
    draft = publish.push(store.load(idea_id))
    with store.edit(idea_id) as i:
        i.substack, i.status = draft, "draft_ready"


STEPS = {
    "frame_debate": _frame_debate,
    "rerun_debate": _rerun_debate,
    "research": _research,
    "write": _write,
}


# ── running ──────────────────────────────────────────────────────────────────
def _run(idea_id: str, step: str) -> None:
    with _semaphore():
        with store.edit(idea_id) as i:
            i.job, i.status = Job(step=step, state="running", at=store.now()), RUNNING[step]
        meter, state, msg = llm.Meter(), "done", ""
        try:
            STEPS[step](idea_id, meter)
        except Exception as e:  # noqa: BLE001 - shown to the user with a Retry button
            log.exception("trade %s: %s failed", idea_id, step)
            state, msg = "failed", str(e)[:400]
        with store.edit(idea_id) as i:
            i.cost_usd = round(i.cost_usd + meter.total, 4)
            i.fallbacks += meter.fallbacks
            i.job = Job(step=step, state=state, message=msg, at=store.now())


def submit(idea_id: str, step: str, *, sync: bool = False) -> None:
    cfg = get_settings().trade_lab
    with store.edit(idea_id) as i:
        if busy(i):
            raise Busy(f"{i.job.step} is still running")
        if i.cost_usd + EST[step] > cfg.cost_cap_usd:
            i.job = Job(
                step=step,
                state="failed",
                at=store.now(),
                message=f"Cost cap: ${i.cost_usd:.2f} spent; this step needs about "
                f"${EST[step]:.2f} and the cap is ${cfg.cost_cap_usd:.2f} per idea.",
            )
            return
        i.job = Job(step=step, state="queued", at=store.now())
    if sync:
        _run(idea_id, step)
    else:
        name = f"trade-{idea_id}-{step}"
        threading.Thread(target=_run, args=(idea_id, step), daemon=True, name=name).start()


def recover_interrupted() -> int:
    n = 0
    for idea in store.all():
        if busy(idea):
            with store.edit(idea.id) as i:
                i.job = i.job.model_copy(
                    update={
                        "state": "interrupted",
                        "message": "The server restarted while this step ran.",
                        "at": store.now(),
                    }
                )
            n += 1
    return n


def _need(idea: TradeIdea, *statuses: str) -> None:
    if busy(idea):
        raise Busy(f"{idea.job.step} is still running")
    if idea.status not in statuses:
        raise ValueError(f"not possible while the idea is {idea.status.replace('_', ' ')}")


def send_research(idea_id: str) -> None:
    _need(store.load(idea_id), "awaiting_view")
    submit(idea_id, "research")


def rerun_debate(idea_id: str) -> None:
    _need(store.load(idea_id), "awaiting_view")
    submit(idea_id, "rerun_debate")


def retry(idea_id: str) -> None:
    idea = store.load(idea_id)
    if not idea.job or idea.job.state not in ("failed", "interrupted"):
        raise ValueError("there is no failed step to retry")
    submit(idea_id, idea.job.step)


def choose(idea_id: str, picks: dict[str, str]) -> None:
    with store.edit(idea_id) as i:
        _need(i, "awaiting_charts")
        opts = {o.id: o for o in i.current().options}
        if missing := [s for s in SECTIONS if s not in picks]:
            raise ValueError("pick a chart for: " + ", ".join(missing))
        for s, oid in picks.items():
            o = opts.get(oid)
            if o is None or o.spec.section != s:
                raise ValueError(f"{oid} is not an option for {s}")
            if not o.file:
                raise ValueError(f"{oid} could not be drawn; pick another")
        if errs := chartist.variety_errors([opts[picks[s]].spec for s in SECTIONS]):
            raise ValueError("; ".join(errs))
        for o in i.current().options:
            o.chosen = picks.get(o.spec.section) == o.id
    submit(idea_id, "write")


def start_round(idea_id: str) -> None:
    cfg = get_settings().trade_lab
    with store.edit(idea_id) as i:
        _need(i, "draft_ready")
        if i.round >= cfg.max_rounds:
            raise ValueError(f"this idea has used all {cfg.max_rounds} rounds")
        if not [r for r in i.research if r.round == i.round + 1 and not r.removed]:
            raise ValueError("add something to research in Talk 2 first")
        i.round += 1
    submit(idea_id, "research")


def say(idea_id: str, talk_n: int, to: str, message: str) -> list[TalkMessage]:
    idea = store.load(idea_id)
    _need(idea, "awaiting_view" if talk_n == 1 else "draft_ready")
    meter = llm.Meter()
    msgs, item, edit = talk.reply(idea, talk_n, to, message, meter)
    rep = None
    if edit:
        try:
            rep = editor.revise(idea, edit[0], edit[1], meter)
        except (StepError, ValueError) as e:
            msgs[-1].text += f" (The edit couldn't be applied: {e})"
            msgs[-1].action = ""
    with store.edit(idea_id) as i:
        i.talk += msgs
        i.research += [item] if item else []
        i.cost_usd = round(i.cost_usd + meter.total, 4)
        i.fallbacks += meter.fallbacks
        if rep:
            i.report = rep
    if rep:
        try:
            publish.push(store.load(idea_id))
        except Exception as e:  # noqa: BLE001 - the edit is saved; the draft can be pushed again
            with store.edit(idea_id) as i:
                i.talk[-1].text += f" The Substack draft didn't update: {str(e)[:120]}"
    return msgs


def another(idea_id: str, section: str) -> ChartOption:
    if section not in SECTIONS:
        raise ValueError(f"unknown section {section}")
    idea = store.load(idea_id)
    _need(idea, "awaiting_charts")
    meter = llm.Meter()
    opt, facts = chartist.another(idea, section, meter)
    with store.edit(idea_id) as i:
        i.current().options.append(opt)
        i.facts += facts
        i.cost_usd = round(i.cost_usd + meter.total, 4)
    return opt


def remove_item(idea_id: str, item_id: str) -> None:
    with store.edit(idea_id) as i:
        item = next((r for r in i.research if r.id == item_id), None)
        if item is None:
            raise KeyError(item_id)
        item.removed = True


def set_frame(idea_id: str, frame: Frame) -> None:
    with store.edit(idea_id) as i:
        _need(i, "awaiting_view")
        i.frame = frame
