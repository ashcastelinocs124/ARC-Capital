"""A trend sub-agent: an OpenAI Responses function-calling loop over its own tools, then findings.

The conversation is kept with previous_response_id, so a grill answer continues the same desk's
research with everything it already pulled."""

from __future__ import annotations

import json
import re
from datetime import date

from castelino.agents.update.models import Fact
from castelino.agents.weekly.models import (
    AgentRun,
    AnswerDraft,
    FindingDrafts,
    GrillExchange,
    GrillQuestion,
    SubAgentSpec,
    WeeklyFinding,
)
from castelino.agents.weekly.tools import ToolBox

SYSTEM = """You are {name}, a specialist on ARC Research's weekly deep-dive desk.
{description}
Goal for the week of {start} to {end}: {goal}
The trends you own (cover each one; findings for every trend): {trends}

Work like an analyst:
- Pull the data that tests the story; prefer data tools to web search for anything measurable.
- Every number you rely on must come from a tool result, cited by its fact id (like {prefix}3).
- {board_rule}
- You have at most {max_calls} tool calls. Stop when the story is clear."""

BOARD_RELATED = (
    "Desks on related topics: {related}. Call read_board before you finish, and post_to_board "
    "anything they could use."
)
BOARD_ALONE = "Post to the board anything another desk could use."

FINDINGS_ASK = """Now give your findings for the editor: at most {cap}. Each has a one-sentence
claim, its headline figure and unit (or null and ""), and the ids of the facts it rests on (only
ids from tool results above). Use only numbers that appear in those facts."""

ANSWER_ASK = """The editor challenges your finding {finding_id}:
"{question}"
You may make up to {calls} more tool calls to check it, then answer in 2-4 sentences citing the
fact ids that support your answer. If the challenge is right, say so."""


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def to_weekly_findings(
    drafts: FindingDrafts, facts: list[Fact], agent: str, cap: int
) -> list[WeeklyFinding]:
    by_id = {f.id: f for f in facts}
    out: list[WeeklyFinding] = []
    for d in drafts.findings:
        ids = [i for i in d.fact_ids if i in by_id]
        if not ids:
            continue  # cited nothing real: drop it
        first = by_id[ids[0]]
        out.append(
            WeeklyFinding(
                id=f"{slug(agent)}-{len(out) + 1}",
                agent=agent,
                claim=d.claim,
                figure=d.figure,
                unit=d.unit,
                provenance=first.provenance,
                series=next((by_id[i].series for i in ids if by_id[i].series), None),
                source_title=first.source_title,
                source_url=first.source_url,
                fact_ids=ids,
            )
        )
        if len(out) == cap:
            break
    return out


class AgentSession:
    def __init__(
        self,
        spec: SubAgentSpec,
        toolbox: ToolBox,
        *,
        client,
        model: str,
        start: date,
        end: date,
        answer_calls: int,
        cap: int,
    ):
        self.spec, self.toolbox, self.client, self.model = spec, toolbox, client, model
        self.answer_calls, self.cap = answer_calls, cap
        if spec.related:
            rule = BOARD_RELATED.format(related=", ".join(spec.related))
        else:
            rule = BOARD_ALONE
        self.system = SYSTEM.format(
            name=spec.name,
            description=spec.description,
            start=start,
            end=end,
            goal=spec.goal,
            trends="; ".join(spec.trends) or "(as in your goal)",
            prefix=toolbox.prefix,
            board_rule=rule,
            max_calls=toolbox.max_calls,
        )
        self.prev: str | None = None

    def _create(self, input_: list, prev: str | None):
        return self.client.responses.create(
            model=self.model,
            instructions=self.system,
            input=input_,
            tools=self.toolbox.specs(),
            tool_choice="none" if self.toolbox.exhausted() else "auto",
            previous_response_id=prev,
        )

    def _loop(self, text: str) -> None:
        resp = self._create([{"role": "user", "content": text}], self.prev)
        while calls := [o for o in resp.output if getattr(o, "type", "") == "function_call"]:
            outputs = []
            for c in calls:
                try:
                    args = json.loads(c.arguments or "{}")
                except json.JSONDecodeError:
                    self.toolbox.calls += 1  # counts against the budget, so the loop always ends
                    result = "Error: arguments were not valid JSON"
                else:
                    result = self.toolbox.call(c.name, args)
                outputs.append(
                    {"type": "function_call_output", "call_id": c.call_id, "output": result}
                )
            resp = self._create(outputs, resp.id)
        self.prev = resp.id

    def _parse(self, ask: str, schema):
        r = self.client.responses.parse(
            model=self.model,
            instructions=self.system,
            input=[{"role": "user", "content": ask}],
            previous_response_id=self.prev,
            text_format=schema,
        )
        self.prev = r.id
        if r.output_parsed is None:
            raise RuntimeError(f"{self.spec.name}: no {schema.__name__} returned")
        return r.output_parsed

    def run(self, brief: str) -> AgentRun:
        self._loop(brief)
        drafts = self._parse(FINDINGS_ASK.format(cap=self.cap), FindingDrafts)
        findings = to_weekly_findings(drafts, self.toolbox.facts, self.spec.name, self.cap)
        if not findings:
            raise RuntimeError(f"{self.spec.name}: no findings that cite real facts")
        return AgentRun(
            agent=self.spec.name,
            facts=list(self.toolbox.facts),
            findings=findings,
            tool_calls=self.toolbox.calls,
        )

    def answer(self, q: GrillQuestion) -> GrillExchange:
        self.toolbox.max_calls = self.toolbox.calls + self.answer_calls
        ask = ANSWER_ASK.format(
            finding_id=q.finding_id, question=q.question, calls=self.answer_calls
        )
        self._loop(ask)
        a: AnswerDraft = self._parse("Give your answer now.", AnswerDraft)
        known = {f.id for f in self.toolbox.facts}
        return GrillExchange(
            agent=self.spec.name,
            finding_id=q.finding_id,
            question=q.question,
            answer=a.answer,
            fact_ids=[i for i in a.fact_ids if i in known],
        )
