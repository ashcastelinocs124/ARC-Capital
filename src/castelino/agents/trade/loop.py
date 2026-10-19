"""A tool loop on the Chat Completions API, so it runs on OpenAI and on OpenRouter alike (the Weekly
desks' Responses-API loop keeps state server-side with previous_response_id, which OpenRouter can't).
The full message list is resent each turn; the box's call budget ends the loop."""

from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel

from castelino.agents.trade import llm
from castelino.agents.trade.tools import chat_tools

T = TypeVar("T", bound=BaseModel)


def run(
    *, agent, model, fallback, system, user, box, meter, schema: type[T], ask: str, history=None
) -> tuple[T, list[dict]]:
    # history: a saved message list to continue (Deep Research's editor desk); system is then unused
    if history:
        msgs: list[dict] = [*history, {"role": "user", "content": user}]
    else:
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    specs = chat_tools(box)
    # each turn calls a budgeted tool or stops; +3 turns for models that ignore tool_choice="none"
    for _ in range(box.max_calls + 3):
        choice = "none" if box.exhausted() else "auto"
        msg = llm.chat(
            agent, model, msgs, meter, tools=specs, tool_choice=choice, fallback=fallback
        )
        if not msg.tool_calls:
            break
        # keep only the calls the budget can take (at least one, so the loop still ends): a news desk asked
        # for 560 in one turn on 2026-10-18 and the API refused the resent message (at most 128 tool calls)
        tcs = msg.tool_calls[: max(1, box.max_calls - box.calls)]
        calls = [t.model_dump() for t in tcs]
        msgs.append({"role": "assistant", "content": msg.content or "", "tool_calls": calls})
        parsed: list[dict | None] = []
        for tc in tcs:
            try:
                parsed.append(json.loads(tc.function.arguments or "{}"))
            except json.JSONDecodeError:
                parsed.append(None)
        box.prefetch([(tc.function.name, a) for tc, a in zip(tcs, parsed, strict=True)])
        for tc, args in zip(tcs, parsed, strict=True):
            if args is None:
                box.calls += 1  # counts against the budget, so the loop always ends
                result = "Error: arguments were not valid JSON"
            else:
                result = box.call(tc.function.name, args)
            msgs.append({"role": "tool", "tool_call_id": tc.id, "content": result})
    msgs.append({"role": "user", "content": ask})
    return llm.structured(agent, model, msgs, schema, meter, fallback=fallback), msgs


def fix(
    *, agent, model, fallback, msgs, out: BaseModel, errors: list[str], schema: type[T], meter
) -> T:
    more = msgs + [
        {"role": "assistant", "content": out.model_dump_json()},
        {
            "role": "user",
            "content": "These figures are not in the facts you cited, or the ids are unknown: "
            + "; ".join(errors)
            + ". Rewrite using only numbers from the facts you cite, and cite them.",
        },
    ]
    return llm.structured(agent, model, more, schema, meter, fallback=fallback)
