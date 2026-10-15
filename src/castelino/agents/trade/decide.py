"""Yes/no on a talk message with OpenAI's Decisions API (POST /v1/decisions, gpt-6-luna, public beta since
2026-10-06). No published docs: the request shape was found from the API's validation errors and checked
with our key on 2026-10-15:
  {"model", "input": str, "questions": [{"type": "predicate", "name", "instructions"}]}
  → {"answers": [{"type": "predicate", "name", "probability"}], "usage": {"input_tokens": n, ...}}
Any error falls back to the same question as a structured yes/no on gpt-6-luna, so a talk never breaks."""

from __future__ import annotations

import logging
import time

import httpx
from pydantic import BaseModel

from castelino import benchmark
from castelino.agents.trade import llm
from castelino.config import get_settings

log = logging.getLogger(__name__)
URL = "https://api.openai.com/v1/decisions"
QUESTIONS = {
    "research": (
        "Answering or checking the user's latest message would need new data or new sources beyond the "
        "debate and the facts listed above, and it matters for this trade idea. Questions about why an "
        "agent argued something, questions the listed facts already answer, and small talk do not count."
    ),
    "edit": "The user's latest message asks to change the draft's wording, order, length or emphasis.",
}
PROMPT = "\n".join(f"{k}: {v}" for k, v in QUESTIONS.items())  # shown on /admin → Agents


class YesNo(BaseModel):
    yes: bool


def _post(body: dict) -> dict:
    key = get_settings().openai_api_key
    r = httpx.post(URL, headers={"Authorization": f"Bearer {key}"}, json=body, timeout=30)
    r.raise_for_status()
    return r.json()


def decide(
    context: str, message: str, names: list[str], meter: llm.Meter, *, post=None
) -> dict[str, float]:
    model = get_settings().trade_lab.decide_model
    text = f"{context}\nUser's latest message: {message}"
    body = {
        "model": model,
        "input": text,
        "questions": [
            {"type": "predicate", "name": n, "instructions": QUESTIONS[n]} for n in names
        ],
    }
    started = time.monotonic()
    try:
        r = (post or _post)(body)
        out = {a["name"]: float(a["probability"]) for a in r["answers"]}
        if set(out) != set(names):
            raise ValueError(f"answers for {sorted(out)}, asked {sorted(names)}")
        tin = r.get("usage", {}).get("input_tokens")
        benchmark.record_call("trade_decide", model, body, r, started=started, tokens=(tin, 0))
        meter.tokens(model, tin, 0)
        return out
    except Exception as e:  # noqa: BLE001 - beta endpoint: fall back, never break the talk
        benchmark.record_call("trade_decide", model, body, started=started, error=str(e)[:500])
        log.warning("Decisions API failed (%s); asking %s instead", str(e)[:120], model)
    out = {}
    for n in names:
        msgs = [
            {"role": "system", "content": f"Answer yes or no. Statement: {QUESTIONS[n]}"},
            {"role": "user", "content": text},
        ]
        yn = llm.structured("trade_decide_fallback", model, msgs, YesNo, meter)
        out[n] = 1.0 if yn.yes else 0.0
    return out
