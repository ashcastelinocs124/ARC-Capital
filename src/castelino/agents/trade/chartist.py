"""Chart agent: 1 to 3 chart ideas for each of the report's 7 sections, each drawn by code from real data,
one marked as its pick. The user picks one per section; "+ Another idea" asks the talk model for one more.
Picks must use at least 6 different forms and at most 2 plain ones (line, compare, bars)."""

from __future__ import annotations

from castelino.agents.trade import forms, llm, store
from castelino.agents.trade.models import (
    SECTIONS,
    ChartOption,
    ChartSpec,
    SpecList,
    StepError,
    TradeIdea,
)
from castelino.agents.update.guard import unsupported
from castelino.agents.update.models import Fact
from castelino.config import get_settings

PURPOSE = {
    "intro": "the cover: why this trade, and where the subject sits against comparable markets",
    "bull": "the strongest evidence for the thesis",
    "bear": "the strongest evidence against it",
    "question": "the user's own questions from the talk, answered with data",
    "technical": "the technical picture: momentum, trend, range, positioning",
    "read": "our read: what holding the trade does to a portfolio",
    "watch": "what to watch: the framer's 'proves it wrong' test, live",
}
SYSTEM = """You are ARC Research's chart editor. For each report section, propose 1 to 3 charts that make its
point fastest, and mark exactly one per section as your pick (agent_pick). Be inventive: prefer the
non-plain forms; across your 7 picks use at least 6 different forms and at most 2 plain ones.
You never supply numbers: name a form, its series (fred:ID or yahoo:TICKER, subject first), a window and,
for threshold_band, the threshold from the framer's test. Titles are short claims, no dashes.
Forms:
{catalog}"""


def variety_errors(specs: list[ChartSpec]) -> list[str]:
    names = [s.form for s in specs]
    errs = []
    if len(set(names)) < 6:
        errs.append(f"use at least 6 different forms across the 7 picks (got {len(set(names))})")
    if sum(n in forms.PLAIN for n in names) > 2:
        errs.append("use at most 2 plain forms (line, compare, bars) across the picks")
    return errs


def _context(idea: TradeIdea) -> str:
    fr = idea.frame
    rnd = idea.current()
    found = [f"{d.desk}: {f.claim}" for d in rnd.desks if d.report for f in d.report.findings]
    asked = [r.text for r in idea.research if r.round == idea.round and not r.removed]
    return "\n\n".join(
        [
            f"Thesis: {fr.thesis}\nTickers: {', '.join(s.ticker for s in fr.stand_ins)}\n"
            f"Proves it wrong: {'; '.join(fr.prove_wrong)}",
            "Debate:\n" + "\n".join(f"{t.side}: {t.text}" for t in idea.turns),
            "User's questions: " + "; ".join(asked),
            "Research findings:\n" + "\n".join(found),
            "Sections:\n" + "\n".join(f"- {k}: {v}" for k, v in PURPOSE.items()),
        ]
    )


def _draw(
    idea: TradeIdea, specs: list[ChartSpec], src, start: int, made: int
) -> tuple[list[ChartOption], list[Fact]]:
    """Draw each spec; `made` = C facts already made this round, so new ids continue after them."""
    options: list[ChartOption] = []
    facts: list[Fact] = []
    for k, spec in enumerate(specs, start):
        oid = f"{spec.section}-{idea.round}-{k}"
        try:
            nums = forms.render(spec, src, store.charts_dir(idea.id) / f"{oid}.png", k)
        except Exception as e:  # noqa: BLE001 - an undrawable idea is dropped, never a crash
            options.append(ChartOption(id=oid, spec=spec, error=str(e)[:200]))
            continue
        known = {v for _, v in nums} | {n for f in idea.facts for n in f.numbers}
        if bad := unsupported([spec.title], known):  # the title is the published caption
            err = f"title figure {', '.join(bad)} is in no fact"
            options.append(ChartOption(id=oid, spec=spec, error=err))
            continue
        fid = f"C{idea.round}.{made + len(facts) + 1}"
        text = f"{spec.title}: " + "; ".join(f"{label} {v:g}" for label, v in nums)
        facts.append(
            Fact(
                id=fid,
                text=text,
                numbers=[v for _, v in nums],
                provenance="data",
                source_title="ARC chart (computed from " + ", ".join(spec.series) + ")",
                source_url="",
            )
        )
        options.append(ChartOption(id=oid, spec=spec, file=f"{oid}.png", fact_ids=[fid]))
    return options, facts


def _made(idea: TradeIdea) -> int:
    return sum(f.id.startswith(f"C{idea.round}.") for f in idea.facts)


def _picks(options: list[ChartOption]) -> dict[str, ChartSpec]:
    """Per section, the drawn option the agent marked, else the first drawn one."""
    out: dict[str, ChartSpec] = {}
    for s in SECTIONS:
        drawn = [o for o in options if o.file and o.spec.section == s]
        if drawn:
            out[s] = next((o for o in drawn if o.spec.agent_pick), drawn[0]).spec
    return out


def propose(idea: TradeIdea, meter: llm.Meter, *, src=None) -> tuple[list[ChartOption], list[Fact]]:
    cfg = get_settings().trade_lab
    src = src or forms.Sources.live()
    msgs = [
        {"role": "system", "content": SYSTEM.format(catalog=forms.catalog_text())},
        {"role": "user", "content": _context(idea)},
    ]
    options: list[ChartOption] = []
    facts: list[Fact] = []
    for attempt in range(2):
        out = llm.structured("trade_chartist", cfg.chart_model, msgs, SpecList, meter)
        bad = [f"{s.section} {s.form}: {e}" for s in out.specs for e in forms.spec_errors(s)]
        good = [s for s in out.specs if not forms.spec_errors(s)]
        new, new_facts = _draw(idea, good, src, len(options) + 1, _made(idea) + len(facts))
        options += new
        facts += new_facts
        picks = _picks(options)
        missing = [s for s in SECTIONS if s not in picks]
        errs = bad + [f"section {s} has no chart that could be drawn" for s in missing]
        if not missing:
            errs += variety_errors(list(picks.values()))
        if not errs:
            break
        if attempt == 0:
            msgs += [
                {"role": "assistant", "content": out.model_dump_json()},
                {
                    "role": "user",
                    "content": "Fix these and propose charts again for the sections named: "
                    + "; ".join(errs),
                },
            ]
    picks = _picks(options)
    if missing := [s for s in SECTIONS if s not in picks]:
        raise StepError(
            "No drawable chart for: " + ", ".join(missing) + '. Retry, or use "+ Another idea".'
        )
    for o in options:  # exactly one agent pick per section, among drawn options
        o.spec.agent_pick = o.spec is picks[o.spec.section]
    return options, facts


def another(
    idea: TradeIdea, section: str, meter: llm.Meter, *, src=None
) -> tuple[ChartOption, list[Fact]]:
    cfg = get_settings().trade_lab
    rnd = idea.current()
    have = [o.spec.form for o in rnd.options if o.spec.section == section]
    ask = (
        f"\n\nPropose ONE new chart for section {section} ({PURPOSE[section]}), "
        f"in a form other than {', '.join(have) or 'none'}."
    )
    msgs = [
        {"role": "system", "content": SYSTEM.format(catalog=forms.catalog_text())},
        {"role": "user", "content": _context(idea) + ask},
    ]
    for _ in range(2):
        out = llm.structured(
            "trade_chartist",
            cfg.talk_model,
            msgs,
            SpecList,
            meter,
            fallback=cfg.fallback_talk_model,
        )
        specs = [
            s.model_copy(update={"section": section, "agent_pick": False}) for s in out.specs[:1]
        ]
        if specs and not forms.spec_errors(specs[0]):
            opts, facts = _draw(
                idea, specs, src or forms.Sources.live(), len(rnd.options) + 1, _made(idea)
            )
            if opts[0].file:
                return opts[0], facts
            err = opts[0].error
        else:
            err = "; ".join(forms.spec_errors(specs[0])) if specs else "no chart proposed"
        msgs += [
            {
                "role": "user",
                "content": f"That didn't draw ({err}). Try a different form or series.",
            }
        ]
    raise StepError(f"Couldn't draw another chart for {section}.")
