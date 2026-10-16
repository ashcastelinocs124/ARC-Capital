"""Runs Trade Lab's steps in background threads (at most trade_lab.concurrency ideas at once). Each step
saves through store.edit(); a failed or interrupted step reruns from its start, finished steps never rerun.
The $5 cap stops a step whose estimate would cross it. Talk 1 and "another idea" run in the request; a
Talk 2 message is a "talk" job (search if needed, answer, edit, push) whose live step is job.message."""

from __future__ import annotations

import logging
import threading

from castelino.agents.trade import (
    chartist,
    debate,
    decide,
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
EST = {"frame_debate": 0.40, "rerun_debate": 0.30, "research": 0.80, "write": 1.00, "talk": 0.15}
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
    # a Retry keeps this round's saved briefs and desks: rerunning the desks would reuse their fact ids
    if not (briefs := store.load(idea_id).current().briefs):
        briefs = orchestrator.plan(store.load(idea_id), meter)
        with store.edit(idea_id) as i:
            i.current().briefs = briefs
    if not store.load(idea_id).current().desks:
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
    if idea.report_round != idea.round:  # else a Retry after a failed push: the report is written
        base = publish.current_text(idea) if idea.round > 1 else None
        rep = editor.write(idea, meter, base_draft=base)
        with store.edit(idea_id) as i:
            i.report, i.report_round = rep, i.round
    draft = publish.push(store.load(idea_id))
    with store.edit(idea_id) as i:
        i.substack, i.status = draft, "draft_ready"


PART_NAMES = {**editor.SECTION_NAMES, "intro": "The introduction", "watch": "What to watch"}


def _step(idea_id: str, text: str) -> None:
    """The live line the Talk 2 panel shows while the talk job runs."""
    with store.edit(idea_id) as i:
        i.job = i.job.model_copy(update={"message": text})


def _talk(idea_id: str, meter: llm.Meter) -> None:
    """One Talk 2 message: search first if it needs new facts, answer, edit each part asked (the talk model,
    then the fallback after two failed number checks), push the draft. The trail says what happened."""
    cfg = get_settings().trade_lab
    idea = store.load(idea_id)
    ask = idea.talk[-1] if idea.talk else None
    if ask is None or ask.talk != 2 or ask.role != "user":
        raise StepError("There is no message waiting for an answer.")
    trail: list[str] = []
    spent = meter.total

    def cost() -> str:
        nonlocal spent
        step, spent = meter.total - spent, meter.total
        return f"${step:.3f}"

    _step(idea_id, "Reading your message")
    dec = decide.decide(talk.context(idea, 2), ask.text, ["research", "edit"], meter)
    searched = dec.get("research", 0.0) >= cfg.decide_threshold
    if searched:
        _step(idea_id, f"Searching the news: up to {cfg.talk_research_calls} searches")
        try:
            run, facts = desks.ask(idea, ask.text, meter)
        except StepError as e:
            trail.append(f"Searched, found nothing usable ({str(e)[:80]}) · {cost()}")
        else:
            with store.edit(idea_id) as i:
                i.facts += facts
            idea = store.load(idea_id)
            n = len(run.domains)
            got = (
                f"added {facts[0].id}" + (f" to {facts[-1].id}" if len(facts) > 1 else "")
                if facts
                else "nothing citable"
            )
            where = ", ".join(run.domains[:4]) or "none"
            trail.append(f"Searched {n} source{'' if n == 1 else 's'}: {where} · {got} · {cost()}")
    _step(idea_id, "Writing the answer")
    msgs, _, edits = talk.reply(idea, 2, ask.to, ask.text, meter, decide_fn=lambda *a: dec)
    reply = msgs[1]
    known = "with the new facts" if searched else "from the facts we have"
    trail.append(f"Answered {known} · {llm.label(cfg.talk_model)} · {cost()}")
    if edits:
        try:
            mine = publish.hand_edited(idea)
        except StepError:
            mine = True  # can't tell, so don't risk overwriting the user's words
        if mine:
            reply.text += (
                " (Not edited: you've edited the Substack draft since we last updated it, so this "
                "would overwrite your edits. Make this change in Substack.)"
            )
            reply.action = ""
        else:
            rep = idea.report
            for part, instruction in edits:
                name = PART_NAMES[part]
                _step(idea_id, f"Editing {name}")
                try:
                    rep, model = editor.revise(
                        idea.model_copy(update={"report": rep}), part, instruction, meter
                    )
                except (StepError, ValueError) as e:
                    trail.append(f"Not edited {name}: {str(e)[:120]} · {cost()}")
                    continue
                fell = model != cfg.talk_model
                why = (
                    f" after {llm.label(cfg.talk_model)} failed the number check twice"
                    if fell
                    else ""
                )
                trail.append(f"Edited {name} · {llm.label(model)}{why} · {cost()}")
            if rep is idea.report:
                reply.text += " (The edit couldn't be applied; see below.)"
                reply.action = ""
            else:
                with store.edit(idea_id) as i:
                    i.report = rep
                _step(idea_id, "Updating the Substack draft")
                try:
                    draft = publish.push(store.load(idea_id))  # a deleted draft comes back
                except Exception as e:  # noqa: BLE001 - the edit is saved; the next edit pushes it
                    trail.append(f"The Substack draft didn't update: {str(e)[:120]}")
                else:
                    with store.edit(idea_id) as i:
                        i.substack = draft
                    trail.append("Draft updated in Substack")
    reply.trail = trail
    with store.edit(idea_id) as i:
        i.talk.append(reply)


STEPS = {
    "frame_debate": _frame_debate,
    "rerun_debate": _rerun_debate,
    "research": _research,
    "write": _write,
    "talk": _talk,
}


# ── running ──────────────────────────────────────────────────────────────────
def _run(idea_id: str, step: str) -> None:
    with _semaphore():
        with store.edit(idea_id) as i:
            # a talk job leaves the idea as it was (draft ready)
            i.job, i.status = (
                Job(step=step, state="running", at=store.now()),
                RUNNING.get(step, i.status),
            )
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


def _over_cap(idea: TradeIdea, step: str) -> str:
    cap = get_settings().trade_lab.cost_cap_usd
    if idea.cost_usd + EST[step] <= cap:
        return ""
    return (
        f"Cost cap: ${idea.cost_usd:.2f} spent; this step needs about "
        f"${EST[step]:.2f} and the cap is ${cap:.2f} per idea."
    )


def submit(idea_id: str, step: str, *, sync: bool = False) -> None:
    with store.edit(idea_id) as i:
        if busy(i):
            raise Busy(f"{i.job.step} is still running")
        if msg := _over_cap(i, step):
            i.job = Job(step=step, state="failed", at=store.now(), message=msg)
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


def say(idea_id: str, talk_n: int, to: str, message: str) -> list[TalkMessage]:
    """Talk 1 answers in the request. A Talk 2 message is saved, then answered by a talk job."""
    idea = store.load(idea_id)
    if talk_n == 2:
        _need(idea, "draft_ready")
        ask = TalkMessage(talk=2, role="user", to=to, text=message, at=store.now())
        with store.edit(idea_id) as i:
            i.talk.append(ask)
        submit(idea_id, "talk")
        return [ask]
    _need(idea, "awaiting_view")
    meter = llm.Meter()
    msgs, item, _ = talk.reply(idea, 1, to, message, meter)
    with store.edit(idea_id) as i:
        i.talk += msgs
        i.research += [item] if item else []
        i.cost_usd = round(i.cost_usd + meter.total, 4)
        i.fallbacks += meter.fallbacks
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
