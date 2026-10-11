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
on what happened in US markets this week. Specialist desks researched the week's trends; each
finding rests on numbered facts (data pulls or cited sources).

GRILL: challenge the findings like a sceptical senior editor. Ask about the evidence behind a
claim, the strongest counter-case, numbers that don't match their facts, and moves that may be
market-wide rather than specific. Ask only questions whose answers could change the report, and
address each to the desk that owns the finding (use the desk name and finding id exactly). Return
done=true when nothing important is left to test.

WRITE (only when asked): the report.
- title: at most 12 words. subtitle: one line on the week's main driver.
- bullets: one per trend: lead = one bold sentence, body = 2-3 sentences, fact_ids it rests on.
- watch: one or two sentences on what to watch next week.
- sections: one per trend (2 to 4 sections): a title, the desk (agent) that researched it, 2-4
  paragraphs of analysis, the fact_ids they rest on, 1-2 exhibits (a fact id from fact_ids whose
  fact has a chartable series, and window_days that tells the story, e.g. 90 or 365), and the
  1-2 most telling challenges from the grill with the desk's answer and your verdict.
Rules: use only figures that appear in the facts you cite, always with their units (%, bp, pp).
Never invent, round differently or compute a number. Describe, don't recommend. No investment
advice."""


class EditorClient(Protocol):
    def parse(self, *, system: str, messages: list[dict], schema: type[T]) -> tuple[T, list]: ...


class AnthropicEditorClient:
    def __init__(self, model: str, effort: str, max_tokens: int):
        import anthropic

        from castelino.config import get_settings

        # explicit long timeout: a high-effort Opus turn on a full week can run several minutes
        self.client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key, timeout=1200)
        self.model, self.effort, self.max_tokens = model, effort, max_tokens

    def check(self) -> None:
        """A tiny call (a fraction of a cent): a missing credit balance only shows on a real
        request; listing models succeeds without one."""
        self.client.messages.create(
            model=self.model, max_tokens=16, messages=[{"role": "user", "content": "Say ok"}]
        )

    def parse(self, *, system: str, messages: list[dict], schema: type[T]) -> tuple[T, list]:
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
        return resp.parsed_output, resp.content


def desk_brief(week: str, plan: DeepPlan, runs: list[AgentRun], posts: list[BoardPost]) -> str:
    goals = {a.name: a.goal for a in plan.agents}
    parts = [f"# Week {week}", "## Trends the Lead picked"]
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
