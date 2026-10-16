"""Editor: Claude Opus 5.5 writes the Special Topics report from the debate, the user's talk, the desks'
findings and the charts the user picked; the number check sends it back once. Talk 2 edits revise one part
on the talk model (DeepSeek V4 Pro), with the same check."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from castelino.agents.trade import guard, llm
from castelino.agents.trade.models import BODY, NAMES, Report, StepError, TradeIdea, instruments
from castelino.agents.weekly.editor import AnthropicEditorClient
from castelino.config import get_settings

STYLE = (Path(__file__).parents[1] / "update" / "style.md").read_text()
SECTION_NAMES = {
    "bull": "The bull case",
    "bear": "The bear case",
    "question": "Your question, tested",
    "technical": "The technical picture",
    "read": "Our read",
}
SYSTEM = f"""You are ARC Research's editor. Write a Special Topics report that tests a trade idea. ARC never makes
a buy or sell call. Use only the facts given: every number must be one of their numbers, and each section
lists the fact ids it uses.
Structure:
- title: a short claim; subtitle: one line.
- introduction: exactly 2 paragraphs. First: the idea in the user's words and why it matters now. Second: how
  we tested it (a bull and a bear argued it over three turns, then our desks dug into what was left open;
  name what they dug into) and what the report covers.
- takeaways: exactly 3 one-sentence takeaways.
- sections, in this order with these keys: bull, bear, question, technical, read. Headings: {SECTION_NAMES}.
  Each is 2 or 3 paragraphs written around that section's chart (described below). In question, say which
  of the user's claims the research confirmed and which it could not.
- what_to_watch: one paragraph that starts from the framer's prove-it-wrong test.
- changes: [] unless a current draft is given; then list each place you changed the user's wording, and why.
House style:
{STYLE}
{NAMES}"""


def _facts(idea: TradeIdea) -> str:
    return "\n".join(f"[{f.id}] {f.text} ({f.source_title})" for f in idea.facts)


def brief(idea: TradeIdea, base_draft: str | None) -> str:
    fr, rnd = idea.frame, idea.current()
    chosen = {o.spec.section: o for o in rnd.options if o.chosen}
    charts = "\n".join(
        f'- {s}: "{o.spec.title}" ({o.spec.form}); its numbers: '
        + ", ".join(f"[{i}]" for i in o.fact_ids)
        for s, o in chosen.items()
    )
    desks = []
    for r in idea.rounds:
        for d in r.desks:
            if not d.report:
                continue
            found = "; ".join(f"{f.claim} [{', '.join(f.fact_ids)}]" for f in d.report.findings)
            line = f"{d.desk}: {d.report.summary} Findings: {found}"
            if d.report.unanswered:
                line += f" Unanswered: {'; '.join(d.report.unanswered)}"
            desks.append(line)
    talk = "\n".join(f"Talk {m.talk} {m.role}: {m.text}" for m in idea.talk)
    items = "\n".join(f"({r.kind}) {r.text}" for r in idea.research if not r.removed)
    names = instruments(fr.stand_ins)
    parts = [
        f"The user's idea: {idea.idea}",
        f"Thesis: {fr.thesis}\nInstruments: {names}\nProves it wrong: {'; '.join(fr.prove_wrong)}",
        "Debate:\n" + "\n".join(f"{t.side} turn {t.round}: {t.text}" for t in idea.turns),
        f"The user's talk:\n{talk}",
        "Research list (the user's claims are only true if a finding confirms them):\n" + items,
        "Desk findings:\n" + "\n".join(desks),
        f"Charts, one per section (the intro's is the cover):\n{charts}",
        f"Facts:\n{_facts(idea)}",
    ]
    if base_draft:
        parts.append(
            "The current Substack draft, which may include the user's hand edits: keep the user's "
            "wording except where new facts contradict it, and list each change in changes.\n"
            + base_draft
        )
    return "\n\n".join(parts)


def _charge(meter: llm.Meter, client) -> None:
    tokens = getattr(client, "last_usage", (None, None))
    meter.tokens(get_settings().trade_lab.editor_model, *tokens)


def write(
    idea: TradeIdea, meter: llm.Meter, *, client=None, base_draft: str | None = None
) -> Report:
    cfg = get_settings().trade_lab
    client = client or AnthropicEditorClient(
        cfg.editor_model, cfg.editor_effort, cfg.editor_max_tokens, agent="trade_editor"
    )
    msgs = [{"role": "user", "content": brief(idea, base_draft)}]
    by = idea.fact_map()
    yours = frozenset(guard.figures(base_draft or ""))  # figures the user typed in Substack pass
    out, _ = client.parse(system=SYSTEM, messages=msgs, schema=Report)
    _charge(meter, client)
    if errs := guard.report_errors(out, by, yours):
        msgs += [
            {"role": "assistant", "content": out.model_dump_json()},
            {
                "role": "user",
                "content": "Fix these and write the whole report again: " + "; ".join(errs),
            },
        ]
        out, _ = client.parse(system=SYSTEM, messages=msgs, schema=Report)
        _charge(meter, client)
        if errs := guard.report_errors(out, by, yours):
            raise StepError("The editor's report failed the number check: " + "; ".join(errs[:8]))
    kept = (
        guard.report_errors(out, by) if yours else []
    )  # what passed only thanks to the user's figures
    if kept:
        figs = ", ".join(e.split(": ", 1)[-1] for e in kept)
        out.changes.append(
            f"Kept figures that are yours, from the Substack draft, not our data: {figs}"
        )
    return out


class Revision(BaseModel):
    paragraphs: list[str]
    fact_ids: list[str]


REVISE = f"""You revise one part of an ARC Research report exactly as the user asks. Keep every number tied to
the facts and cite their ids; change nothing the user didn't ask about. House style:
{STYLE}
{NAMES}"""


def revise(idea: TradeIdea, part: str, instruction: str, meter: llm.Meter) -> tuple[Report, str]:
    """One part rewritten as asked, and the model that wrote it: the talk model gets two tries at the number
    check, then the fallback model gets two."""
    cfg = get_settings().trade_lab
    rep = idea.report
    if part in BODY:
        current = next(s for s in rep.sections if s.key == part).paragraphs
    elif part == "intro":
        current = rep.introduction
    elif part == "watch":
        current = [rep.what_to_watch]
    else:
        raise ValueError(f"unknown part {part}")
    user = (
        f"Part: {part}\nCurrent text:\n"
        + "\n\n".join(current)
        + f"\n\nThe user asks: {instruction}\n\nFacts:\n{_facts(idea)}"
    )
    by = idea.fact_map()
    errs: list[str] = []
    out = None
    for model in dict.fromkeys([cfg.talk_model, cfg.fallback_talk_model]):
        msgs = [{"role": "system", "content": REVISE}, {"role": "user", "content": user}]
        for _ in range(2):
            out = llm.structured(
                "trade_revise", model, msgs, Revision, meter, fallback=cfg.fallback_talk_model
            )
            ids = out.fact_ids if part in BODY else list(by)
            errs = guard.cited_errors(out.paragraphs, ids, by) + guard.dash_errors(out.paragraphs)
            if part == "intro" and len(out.paragraphs) != 2:
                errs.append("the introduction must stay 2 paragraphs")
            if not errs:
                break
            msgs += [
                {"role": "assistant", "content": out.model_dump_json()},
                {"role": "user", "content": "Fix: " + "; ".join(errs)},
            ]
        if not errs:
            break
    else:
        raise StepError("The edit failed the number check: " + "; ".join(errs))
    out = out.model_copy(update={"paragraphs": [guard.strip_ids(p) for p in out.paragraphs]})
    if part in BODY:
        secs = [
            s.model_copy(update={"paragraphs": out.paragraphs, "fact_ids": out.fact_ids})
            if s.key == part
            else s
            for s in rep.sections
        ]
        return rep.model_copy(update={"sections": secs}), model
    if part == "intro":
        return rep.model_copy(update={"introduction": out.paragraphs}), model
    return rep.model_copy(update={"what_to_watch": " ".join(out.paragraphs)}), model
