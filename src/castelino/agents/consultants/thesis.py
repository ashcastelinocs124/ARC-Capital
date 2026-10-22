"""The thesis: a consultant's analysis of its topic in two parts — what is happening, then what could happen
(the path it leans to, the other path that matters, what would change its mind).

The user's rule (2026-10-22): analysis, not data points. Each part cites the facts it rests on; a figure may
appear only when the argument needs it and must be one of those facts' numbers, and the whole thesis carries
at most two unit figures."""

from __future__ import annotations

from castelino.agents.consultants.models import Thesis, ThesisDraft
from castelino.agents.trade import llm
from castelino.agents.update.guard import count_figures, unsupported
from castelino.agents.update.models import Fact
from castelino.config import get_settings

MAX_FIGURES = 2
PARTS = ("happening", "lean", "alternative", "change_mind")

SYSTEM = """You are an ARC Research topic consultant. You follow one topic every day and keep a thesis on it.
Write the thesis as ANALYSIS, NOT DATA POINTS: your reading of what is happening and why, and what could
happen next. The data lives in the facts; your job is what they mean.

Parts (each 1-3 sentences, plain words):
- happening: what is happening on this topic and why: your reading of the situation.
- lean: what could happen: the path you lean to, and why.
- alternative: the other path that matters, and what would set it off.
- change_mind: what would change your mind: the signal you are watching.
- reason: one sentence on what changed from the old thesis (or "first thesis").

Rules:
- Each part lists in fact_ids the facts it rests on. Only use ids from the facts given.
- Use a figure only when the argument needs it, and only a number from the facts that part cites. At most
  two %/bp/pp figures in the whole thesis.
- An outlook carries no made-up figure: write "if cloud spending is trimmed", never "if capex falls 10%". A
  figure in an outlook must be a fact's (e.g. a Polymarket probability).
- No buy or sell advice. No price targets.
- Keep what still holds from the old thesis; change only what today's facts change."""


def errors(d: ThesisDraft, facts: dict[str, Fact]) -> list[str]:
    errs: list[str] = []
    texts = []
    for name in PARTS:
        part = getattr(d, name)
        texts.append(part.text)
        unknown = [i for i in part.fact_ids if i not in facts]
        if unknown:
            errs.append(f"{name} cites unknown fact ids {unknown}")
        nums = {n for i in part.fact_ids if i in facts for n in facts[i].numbers}
        if bad := unsupported([part.text], nums):
            errs.append(f"{name} has figures not in its cited facts: {bad}")
    if (n := count_figures(texts)) > MAX_FIGURES:
        errs.append(f"analysis, not data points: {n} figures (at most {MAX_FIGURES})")
    return errs


def _user(topic: str, facts: list[Fact], memory_md: str, old: Thesis | None, today: str) -> str:
    lines = "\n".join(f"[{f.id}] {f.text} — {f.source_title}" for f in facts)
    parts = [f"Topic: {topic}\nToday: {today}", f"## Facts\n{lines or '(none)'}"]
    parts.append(f"## Memory\n{memory_md or '(empty)'}")
    if old:
        parts.append("## Old thesis\n" + "\n".join(f"{p}: {getattr(old, p).text}" for p in PARTS))
    return "\n\n".join(parts)


def write(
    topic: str,
    facts: list[Fact],
    memory_md: str,
    old: Thesis | None,
    today: str,
    meter: llm.Meter,
) -> Thesis:
    """Write (or rewrite) the thesis; one retry with the check's errors, then ValueError."""
    model = get_settings().consultants.thesis_model
    by_id = {f.id: f for f in facts}
    msgs = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": _user(topic, facts, memory_md, old, today)},
    ]
    errs: list[str] = []
    for attempt in range(2):
        if attempt:
            fix = f"Your draft failed these checks: {'; '.join(errs)}. Fix them."
            msgs = [*msgs, {"role": "user", "content": fix}]
        d = llm.structured("consultant_thesis", model, msgs, ThesisDraft, meter)
        if not (errs := errors(d, by_id)):
            return Thesis(**d.model_dump(), updated=today, version=old.version + 1 if old else 1)
    raise ValueError(errs)
