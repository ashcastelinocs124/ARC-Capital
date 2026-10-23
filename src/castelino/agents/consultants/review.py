"""The reviews: how a consultant's thesis and memory change.

Evening (every day, after the Daily Update): one Decisions API call asks two questions — does today change
the thesis, and is anything worth remembering? Each yes rewrites that part; each no leaves it alone. While a
consultant's knob is on it asks a third, whether today has a notable point to post (post.py).
Sunday: one call asks, per note, whether a short-term note still matters a month from now (moved to
long-term) and whether a long-term note is now out of date (deleted). Short-term is then cleared.

The Daily Update's analysts never see consultant facts, so their findings are independent evidence: the
consultant can't end up agreeing with its own advice."""

from __future__ import annotations

from datetime import date, timedelta

from castelino.agents.consultants import post, store, thesis
from castelino.agents.consultants.models import HistoryLine, MemoryNoteDraft, Thesis
from castelino.agents.trade import llm
from castelino.agents.trade.decide import predicates
from castelino.agents.update.memory import Note, rebalance
from castelino.agents.update.models import Fact, Finding
from castelino.config import get_settings

THESIS_Q = (
    "Today's facts and findings change the thesis: part of it is now wrong or out of date, or a new driver "
    "appeared that it does not cover."
)
MEMORY_Q = (
    "Today holds something worth remembering for this topic beyond today: a pattern, a turning point, or a "
    "lesson about a source."
)
KEEP_Q = "Short-term note '{title}' ({text}) will still matter for this topic a month from now."
DROP_Q = "This week's facts show long-term note '{title}' ({text}) is out of date or wrong."
NOTE_SYSTEM = """You keep the memory of an ARC Research topic consultant. Write ONE note worth remembering
from today: a pattern, a turning point, or a lesson about a source. title: under 8 words. text: 1-2
sentences, analysis rather than data points. importance: 1 (minor) to 5 (critical)."""


def last_sunday(day: date) -> date:
    return day - timedelta(days=(day.weekday() + 1) % 7)


def _thesis_md(t: Thesis) -> str:
    return (
        f"What's happening: {t.happening.text}\nLeaning to: {t.lean.text}\n"
        f"Other path: {t.alternative.text}\nWould change our mind: {t.change_mind.text}"
    )


def _notes_md(notes: list[Note]) -> str:
    return "\n".join(f"- {n.title}: {n.text}" for n in notes) or "(empty)"


def _facts_md(facts: list[Fact]) -> str:
    return "\n".join(f"[{f.id}] {f.text}" for f in facts) or "(none)"


def _findings_md(findings: list[Finding]) -> str:
    return "\n".join(f"- {f.claim} ({f.source_title})" for f in findings) or "(none)"


def _cited(t: Thesis) -> list[str]:
    return [
        i for part in (t.happening, t.lean, t.alternative, t.change_mind) for i in part.fact_ids
    ]


def daily(slug: str, day: str, findings: list[Finding], meter: llm.Meter) -> HistoryLine | None:
    """The evening review. None when already done today or there is no thesis yet."""
    cfg = get_settings().consultants
    c = store.load(slug)
    old = store.read_thesis(slug)
    if old is None or store.day_log(slug, day).reviewed:
        return None
    short, long = store.read_memory(slug)
    own = store.read_facts(slug, day)
    text = (
        f"Topic: {c.topic}\n\n## Thesis\n{_thesis_md(old)}\n\n## Memory\n{_notes_md(short + long)}"
        f"\n\n## Today's Daily Update findings\n{_findings_md(findings)}\n\n## Today's facts\n{_facts_md(own)}"
    )
    questions = {"thesis": THESIS_Q, "memory": MEMORY_Q} | (
        {"post": post.POST_Q} if c.post_to_x else {}
    )
    p = predicates(text, questions, meter, agent="consultant_decide")
    verdict, reason, before, after = "held", "", None, None
    if p["thesis"] >= cfg.threshold:
        pool = {
            f.id: f
            for f in [
                *store.facts_by_id(slug, _cited(old)),
                *store.recent_facts(slug, 7, date.fromisoformat(day)),
            ]
        }
        try:
            new = thesis.write(
                c.topic,
                list(pool.values()),
                _notes_md(short + long),
                old,
                day,
                meter,
                context=_findings_md(findings),
            )
            store.write_thesis(slug, new)
            verdict, reason = "updated", new.reason
            before, after = old.happening.text, new.happening.text
        except ValueError:
            reason = "rewrite failed the number check; the thesis stands"
    if p["memory"] >= cfg.threshold:
        msgs = [{"role": "system", "content": NOTE_SYSTEM}, {"role": "user", "content": text}]
        try:
            n = llm.structured("consultant_note", cfg.note_model, msgs, MemoryNoteDraft, meter)
            imp = min(5, max(1, n.importance))
            short.append(
                Note(n.title.strip(), n.text.strip(), imp, date.fromisoformat(day), "lesson")
            )
            store.write_memory(slug, short, long)
        except Exception as e:  # noqa: BLE001 - a lost note never fails the review
            with store.edit_day(slug, day) as d:
                d.notes.append(f"memory note failed: {str(e)[:120]}")
    posted = form = None
    if p.get("post", 0.0) >= cfg.threshold:
        now = store.read_thesis(slug) or old  # the rewritten thesis, if today changed it
        facts = {f.id: f for f in [*store.facts_by_id(slug, _cited(now)), *own]}
        ctx = f"## Thesis\n{_thesis_md(now)}\n\n## Today's Daily Update findings\n{_findings_md(findings)}"
        try:
            posted, form = post.run(slug, day, ctx, list(facts.values()), meter) or (None, None)
        except Exception as e:  # noqa: BLE001 - a failed post never fails the review
            with store.edit_day(slug, day) as d:
                d.notes.append(f"X post skipped: {str(e)[:160]}")
    line = HistoryLine(
        day=day,
        kind="daily",
        verdict=verdict,
        p_thesis=p["thesis"],
        p_memory=p["memory"],
        reason=reason,
        before=before,
        after=after,
        p_post=p.get("post"),
        post=posted,
        chart_form=form,
    )
    store.append_history(slug, line)
    with store.edit_day(slug, day) as d:
        d.reviewed = True
    return line


def weekly(slug: str, week_end: date, meter: llm.Meter) -> HistoryLine | None:
    """The Sunday memory review for the week ending `week_end`. None when already done, or when the
    consultant didn't exist that week."""
    cfg = get_settings().consultants
    c = store.load(slug)
    we = week_end.isoformat()
    hist = store.history(slug)
    if we < c.created or any(h.kind == "weekly" and h.day == we for h in hist):
        return None
    short, long = store.read_memory(slug)
    start = (week_end - timedelta(days=6)).isoformat()
    week = [h for h in hist if start <= h.day <= we]
    questions = {
        f"keep_s{i}": KEEP_Q.format(title=n.title, text=n.text) for i, n in enumerate(short)
    }
    questions |= {
        f"drop_l{j}": DROP_Q.format(title=n.title, text=n.text) for j, n in enumerate(long)
    }
    p: dict[str, float] = {}
    if questions:
        text = (
            f"Topic: {c.topic}\n\n## This week's reviews\n"
            + ("\n".join(f"{h.day} {h.verdict}: {h.reason}" for h in week) or "(none)")
            + f"\n\n## This week's facts\n{_facts_md(store.recent_facts(slug, 7, week_end))}"
        )
        p = predicates(text, questions, meter, agent="consultant_decide")
    kept = [n for i, n in enumerate(short) if p.get(f"keep_s{i}", 0.0) >= cfg.threshold]
    cleared = [n for n in short if n not in kept]
    dropped = [n for j, n in enumerate(long) if p.get(f"drop_l{j}", 0.0) >= cfg.threshold]
    moved = [Note(n.title, n.text, n.importance, week_end, n.type) for n in kept]
    merged = [n for n in long if n not in dropped] + moved
    new_long = rebalance(merged, week_end, short_cap=0, long_cap=cfg.long_term_notes)[1]
    evicted = [n for n in merged if n not in new_long]  # over the cap: traced like any deletion
    store.write_memory(slug, [], new_long)
    reason = f"{len(cleared)} short-term notes cleared"
    if cleared:
        reason += ": " + "; ".join(n.title for n in cleared)
    line = HistoryLine(
        day=we,
        kind="weekly",
        verdict="week",
        reason=reason + ".",
        moved=[n.title for n in moved if n in new_long],
        deleted=[n.title for n in dropped + evicted],
    )
    store.append_history(slug, line)
    return line
