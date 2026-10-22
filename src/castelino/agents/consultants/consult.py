"""How the other systems use a consultant.

- `for_note(day)`: what the Daily Update gets (theses, a few facts, the codes that prefix those facts),
  saved per day under updates/consult/, so an admin rebuild of an old day uses that day's theses.
- `answer(slug, question)`: the `consult()` tool's reply for Weekly, Research and Trade Lab agents. It
  answers only from the consultant's file — no live research — so a question can never change a view, and
  the cost lands on the caller's meter, never the consultant's daily cap.
- `spec()`: the tool definition listing the consultants that have a thesis."""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from castelino.agents.consultants import store
from castelino.agents.consultants.models import Answer, Ask, Consultant, NoteConsult, Thesis
from castelino.agents.trade import llm
from castelino.agents.update.fsio import atomic_write_text
from castelino.agents.update.guard import unsupported
from castelino.agents.update.models import Fact
from castelino.config import get_settings

ANSWER_SYSTEM = """You are an ARC Research topic consultant answering another analyst's question about your
topic. Answer from your thesis, memory and facts only. Give ANALYSIS, NOT DATA POINTS: what you think is
happening and what could happen next, in 2-5 plain sentences. Use a figure only when the argument needs it,
and only a number from the facts you cite in fact_ids. An outlook carries no made-up figure. No buy or sell
advice. If your file doesn't cover the question, say so in one sentence."""


def _cited(t: Thesis) -> list[str]:
    return [i for p in (t.happening, t.lean, t.alternative, t.change_mind) for i in p.fact_ids]


def _with_thesis() -> list[tuple[Consultant, Thesis]]:
    return [(c, t) for c in store.active() if (t := store.read_thesis(c.slug))]


def _thesis_md(t: Thesis) -> str:
    return (
        f"What's happening: {t.happening.text}\nWhat could happen: leaning to {t.lean.text} "
        f"Other path: {t.alternative.text} Would change our mind: {t.change_mind.text}"
    )


def spec() -> dict | None:
    from castelino.agents.weekly.tools import _obj

    if not get_settings().consultants.enabled:  # the kill switch
        return None
    cs = _with_thesis()
    if not cs:
        return None
    listing = "; ".join(f"{c.slug}: {c.topic}" for c, _ in cs)
    return {
        "type": "function",
        "name": "consult",
        "strict": True,
        "description": (
            "Ask an ARC topic consultant for its analysis of what is happening and what could happen on "
            f"its topic. It answers from its own file and returns the facts behind it. Consultants: {listing}"
        ),
        "parameters": _obj(
            {
                "topic": {"type": "string", "enum": [c.slug for c, _ in cs]},
                "question": {"type": "string"},
            }
        ),
    }


def _drop_bad_sentences(text: str, nums: set[float]) -> str:
    keep = [s for s in re.split(r"(?<=[.!?])\s+", text) if not unsupported([s], nums)]
    return " ".join(keep).strip()


def answer(
    slug: str, question: str, *, asker: str, meter: llm.Meter | None = None
) -> tuple[str, list[Fact]]:
    """Analysis from the consultant's file. KeyError for an unknown slug."""
    c = store.load(slug)
    t = store.read_thesis(slug)
    if t is None:
        return f"The {c.topic} consultant has no view yet.", []
    today = date.today()
    short, long = store.read_memory(slug)
    pool = {
        f.id: f for f in [*store.facts_by_id(slug, _cited(t)), *store.recent_facts(slug, 30, today)]
    }
    facts_md = "\n".join(f"[{f.id}] {f.text} — {f.source_title}" for f in pool.values())
    memory = "\n".join(f"- {n.title}: {n.text}" for n in short + long) or "(empty)"
    msgs = [
        {"role": "system", "content": ANSWER_SYSTEM},
        {
            "role": "user",
            "content": f"Topic: {c.topic}\n\n## Thesis\n{_thesis_md(t)}\n\n## Memory\n{memory}"
            f"\n\n## Facts\n{facts_md or '(none)'}\n\n## Question from {asker}\n{question}",
        },
    ]
    model = get_settings().consultants.answer_model
    meter = meter or llm.Meter()
    for _attempt in range(2):  # one retry, then the sentences with a bad figure are dropped
        a = llm.structured("consultant_answer", model, msgs, Answer, meter)
        cited = [pool[i] for i in a.fact_ids if i in pool]
        nums = {n for f in cited for n in f.numbers}
        if not (bad := unsupported([a.text], nums)):
            text = a.text.strip()
            break
        fix = f"These figures are not in the facts you cite: {bad}. Remove them or cite the fact."
        msgs = [*msgs, {"role": "user", "content": fix}]
        text = _drop_bad_sentences(a.text, nums)
    with store.edit_day(slug, today.isoformat()) as d:
        d.asks.append(
            Ask(
                at=datetime.now().isoformat(timespec="seconds"),
                asker=asker,
                question=question,
                fact_ids=[f.id for f in cited],
            )
        )
    return text, cited


def for_note(day: str, updates_dir: Path, create: bool = True) -> NoteConsult:
    """The consultants' input to `day`'s Daily Update, saved on first use and reused after. Only the
    daily run creates it (`create`): a rebuild of a day with no saved input gets none, never today's
    theses."""
    if not get_settings().consultants.enabled:  # the kill switch
        return NoteConsult()
    path = Path(updates_dir) / "consult" / f"{day}.json"
    if path.exists():
        return NoteConsult.model_validate_json(path.read_text())
    if not create:
        return NoteConsult()
    cap = get_settings().consultants.note_facts
    out = NoteConsult()
    watch, blocks = [], []
    for c, t in _with_thesis():
        pool = {
            f.id: f for f in [*store.facts_by_id(c.slug, _cited(t)), *store.read_facts(c.slug, day)]
        }
        facts = list(pool.values())[:cap]
        out.facts += facts
        out.codes[c.slug], out.names[c.slug] = c.code, c.topic
        watch.append(
            f"- {c.topic}: leaning to {t.lean.text} Would change our mind: {t.change_mind.text}"
        )
        lines = "\n".join(f"[{f.id}] {f.text} — {f.source_title}" for f in facts)
        blocks.append(
            f"### {c.topic} (consultant: {c.slug})\n{_thesis_md(t)}\nFacts:\n{lines or '(none)'}"
        )
    out.watch_md, out.prompt_md = "\n".join(watch), "\n\n".join(blocks)
    atomic_write_text(path, out.model_dump_json(indent=1))
    return out
