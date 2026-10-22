"""Deep Editor: Claude Opus 5.5 grills the trend desk, then writes the Weekly Deep Dive.

One conversation, append-only: Opus 5.5 rejects edited history, so turns are only ever added."""

from __future__ import annotations

import logging
from typing import Protocol, TypeVar

from pydantic import BaseModel

from castelino.agents.update.models import Fact
from castelino.agents.weekly.models import (
    AgentRun,
    BoardPost,
    DeepPlan,
    Grill,
    GrillExchange,
    WeeklyReport,
)

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

SYSTEM = """You are the Deep Editor of ARC Research's Weekly Deep Dive, a sell-side style report
on what happened in US markets this week, read by investors. You get this week's Daily Updates
(ARC's own daily notes, with their facts N1, N2, ...) and the deep research of specialist desks;
every finding rests on numbered facts (data pulls or cited sources).

GRILL: challenge each desk's research like a sceptical senior editor. Test it against what our
Daily Updates reported: does the desk's explanation account for what we saw? Ask about the
evidence behind a claim, the strongest counter-case, a breakdown that is missing, numbers that
don't match their facts, and moves that may be market-wide rather than specific. Ask only
questions whose answers could change the report, and address each to the desk that owns the
finding (use the desk name and finding id exactly). Return done=true when nothing important is
left to test.

WRITE (only when asked): the report, for an investor deciding what the week means.
- title: at most 12 words. subtitle: one line on the week's main driver.
- The report covers every one of the Lead's trends (10 to 12), in the Lead's order. A trend may
  be reframed or merged only if the grill showed its premise was wrong; keep at least 10. Write
  the corrected story; never narrate the Lead's mistake or the grill to the reader.
- bullets: exactly one per section, same order: lead = one bold sentence, body = 1-2 sentences,
  fact_ids it rests on.
- watch: one or two sentences on what to watch next week.
- sections: one per trend (10 to 12), each with:
  - title, and the desk (agent) that researched it.
  - HIGH LEVEL — what_happened: 1 paragraph, what we saw this week, from our Daily Updates
    (N facts) and headline data. Plain and factual.
  - DEEP RESEARCH, from the desk:
    - why: 1-2 paragraphs on the drivers. Explain the mechanism as a chain (cause, how it
      transmits, effect), not a list of numbers.
    - under_the_surface: 1-2 paragraphs on the breakdown: which sectors, components, regions or
      cohorts drove it (e.g. which industries' wages rose). If the desk found no breakdown, say
      what is missing in one sentence rather than guessing.
    - market_impact: 1-2 paragraphs on what it means for markets: rates and the Fed path, the
      dollar, equity sectors, credit, commodities, as the evidence supports. Describe the
      implication; never recommend a trade.
    - watch: 1 paragraph: the releases, levels or events that would confirm or break the story.
  - fact_ids every part rests on, and the 1-2 most telling grill challenges with the desk's
    answer and your verdict.
  - exhibits: 1-2 charts. Pick the form that tells the story best, and only facts from fact_ids:
    - line: 1 fact with a daily series; window_days 30-365.
    - compare: 2-4 facts with daily series, plotted together (prices rebased to 100).
    - release: 1 fact with a release history (e.g. a BLS or FRED release).
    - breakdown: 2-12 bars ranking components or sectors; one point per bar.
    - movers: 2-12 bars of moves across assets, positive and negative.
    - dumbbell: exactly 2 points, a before and an after.
    For bar forms each point is {fact_id, label, value} and value must be one of that fact's
    numbers, exactly as written there. title: a short chart title. unit: the unit of the values.
Rules: use only figures that appear in the facts you cite, always with their units (%, bp, pp).
Never invent, round differently or compute a number. Describe, don't recommend. No investment
advice."""


class EditorClient(Protocol):
    def parse(self, *, system: str, messages: list[dict], schema: type[T]) -> tuple[T, list]: ...


class AnthropicEditorClient:
    def __init__(self, model: str, effort: str, max_tokens: int, agent: str = "deep_editor"):
        import anthropic

        from castelino.config import get_settings

        # explicit long timeout: a high-effort Opus turn on a full week can run several minutes
        self.client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key, timeout=1200)
        self.model, self.effort, self.max_tokens, self.agent = model, effort, max_tokens, agent
        self.last_usage: tuple[int | None, int | None] = (
            None,
            None,
        )  # for callers that price calls

    def check(self) -> None:
        """A tiny call (a fraction of a cent): a missing credit balance only shows on a real
        request; listing models succeeds without one."""
        self.client.messages.create(
            model=self.model, max_tokens=16, messages=[{"role": "user", "content": "Say ok"}]
        )

    def parse(self, *, system: str, messages: list[dict], schema: type[T]) -> tuple[T, list]:
        import time

        from castelino import benchmark

        sent = {"system": system, "messages": messages, "schema": schema.__name__}
        started = time.monotonic()
        try:
            out, content, usage = self._parse(system=system, messages=messages, schema=schema)
        except Exception as e:
            benchmark.record_call(self.agent, self.model, sent, started=started, error=str(e)[:500])
            raise
        tokens = (getattr(usage, "input_tokens", None), getattr(usage, "output_tokens", None))
        self.last_usage = tokens
        benchmark.record_call(self.agent, self.model, sent, out, started=started, tokens=tokens)
        return out, content

    def _parse(self, *, system: str, messages: list[dict], schema: type[T]):
        kw = dict(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=messages,
            output_format=schema,
            output_config={"effort": self.effort},
        )
        try:  # server-side refusal fallback (beta); older SDKs lack the kwargs
            resp = self.client.beta.messages.parse(
                **kw, betas=["server-side-fallback-2026-07-01"], fallbacks="default"
            )
        except TypeError:
            log.warning("anthropic SDK has no fallbacks on parse; calling without")
            resp = self.client.messages.parse(**kw)
        if resp.stop_reason == "refusal":
            raise RuntimeError(f"editor refused: {getattr(resp, 'stop_details', None)}")
        if resp.parsed_output is None:
            raise RuntimeError(f"editor returned no {schema.__name__} (stop: {resp.stop_reason})")
        return resp.parsed_output, resp.content, getattr(resp, "usage", None)


def desk_brief(
    week: str,
    plan: DeepPlan,
    runs: list[AgentRun],
    posts: list[BoardPost],
    *,
    notes_md: str = "",
    notes: list[Fact] = (),
) -> str:
    goals = {a.name: a.goal for a in plan.agents}
    parts = [f"# Week {week}"]
    if notes_md or notes:
        parts.append(f"## This week's Daily Updates (our data, for the high level)\n{notes_md}")
        parts.append("### Daily Update facts")
        parts += [f"[{x.id}] {x.text} — {x.source_title}" for x in notes]
    parts.append("## Trends the Lead picked")
    parts += [f"- {t.title}: {t.why}" for t in plan.trends]
    for r in runs:
        parts.append(f"## Desk: {r.agent}\nGoal: {goals.get(r.agent, '')}\n### Findings")
        for f in r.findings:
            fig = f" ({f.figure:g}{f.unit})" if f.figure is not None else ""
            parts.append(f"[{f.id}] {f.claim}{fig} — facts: {', '.join(f.fact_ids)}")
        parts.append("### Facts")
        parts += [f"[{x.id}] {x.text} — {x.source_title}" for x in r.facts]
    if posts:
        parts.append("## Board")
        parts += [f"- {p.agent}: {p.note} (facts: {', '.join(p.fact_ids)})" for p in posts]
    return "\n".join(parts)


def answers_brief(answers: list[GrillExchange], facts: dict[str, Fact]) -> str:
    parts = ["## Answers"]
    for a in answers:
        parts.append(f"[{a.finding_id}] Q: {a.question}\nA ({a.agent}): {a.answer}")
        parts += [
            f"  [{i}] {facts[i].text} — {facts[i].source_title}" for i in a.fact_ids if i in facts
        ]
    return "\n".join(parts)


class DeepEditor:
    def __init__(self, client: EditorClient):
        self.client = client
        self.messages: list[dict] = []

    def _ask(self, text: str, schema: type[T]) -> T:
        self.messages.append({"role": "user", "content": text})
        parsed, content = self.client.parse(
            system=SYSTEM, messages=list(self.messages), schema=schema
        )
        self.messages.append({"role": "assistant", "content": content})
        return parsed

    def open(self, desk_md: str) -> Grill:
        return self._ask(f"{desk_md}\n\nGRILL: your first round of questions.", Grill)

    def followup(self, answers_md: str, last: bool) -> Grill:
        if last:
            tail = "That was the last grill round; return done=true."
        else:
            tail = "GRILL: next round, or done=true."
        return self._ask(f"{answers_md}\n\n{tail}", Grill)

    def write(self, guard_errors: list[str] | None) -> WeeklyReport:
        if guard_errors:
            text = (
                "Your report failed these checks: "
                + "; ".join(guard_errors)
                + ". WRITE it again, fixing them using only figures from the cited facts."
            )
        else:
            text = "WRITE the report now."
        return self._ask(text, WeeklyReport)
