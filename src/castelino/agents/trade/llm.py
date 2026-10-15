"""Trade Lab's model calls: OpenAI directly and DeepSeek through OpenRouter, both with the OpenAI SDK.

Every call is logged (benchmark.record_call) and priced into a Meter. An OpenRouter model needs
OPENROUTER_API_KEY; without it, or after an OpenRouter failure plus one retry, the role's OpenAI fallback
answers and the Meter notes it (shown on the idea)."""

from __future__ import annotations

import os
import threading
import time
from typing import TypeVar

from pydantic import BaseModel

from castelino import benchmark
from castelino.config import get_settings

T = TypeVar("T", bound=BaseModel)
OPENROUTER = "https://openrouter.ai/api/v1"
# $ per million tokens (in, out), list prices on 2026-10-15. ponytail: DeepSeek is priced at a
# no-data-retention host's rate; OpenRouter's own reported cost replaces it whenever the reply carries one.
PRICES: dict[str, tuple[float, float]] = {
    "gpt-6-sol": (2.0, 10.0),
    "gpt-6-luna": (0.10, 0.50),
    "deepseek/deepseek-v4-pro": (1.30, 2.60),
    "claude-opus-5-5": (4.0, 20.0),
}
SEARCH_FEE = 0.01  # assumed $ per OpenAI web search call (2025 rate); confirm on the invoice
# one cited gpt-6-luna search ≈ 65k tokens in, 3.7k out (benchmark medians, 2026-10-15) + the call fee
SEARCH_USD = SEARCH_FEE + (65_000 * 0.10 + 3_700 * 0.50) / 1e6


class Meter:
    """$ spent by one step (desks run in parallel, so it locks) and any fallbacks it used."""

    def __init__(self) -> None:
        self.total = 0.0
        self.fallbacks: list[str] = []
        self._lock = threading.Lock()

    def add(self, usd: float) -> None:
        with self._lock:
            self.total += usd

    def tokens(self, model: str, tin: int | None, tout: int | None) -> None:
        pin, pout = PRICES.get(model, (0.0, 0.0))
        self.add(((tin or 0) * pin + (tout or 0) * pout) / 1e6)

    def fell_back(self, note: str) -> None:
        with self._lock:
            self.fallbacks.append(note)


def is_openrouter(model: str) -> bool:
    return "/" in model


def _has_key() -> bool:
    return bool(os.environ.get("OPENROUTER_API_KEY", "").strip())


def route(model: str, fallback: str | None) -> str:
    return fallback if (is_openrouter(model) and not _has_key() and fallback) else model


def _client(model: str):
    from openai import OpenAI

    if is_openrouter(model):
        return OpenAI(base_url=OPENROUTER, api_key=os.environ["OPENROUTER_API_KEY"], timeout=180)
    return OpenAI(api_key=get_settings().openai_api_key, timeout=180)


def _extra(model: str) -> dict | None:
    if not is_openrouter(model):
        return None
    provider = dict(get_settings().trade_lab.openrouter_provider)
    return {"provider": provider, "usage": {"include": True}}


def _charge(model: str, resp, meter: Meter) -> None:
    u = getattr(resp, "usage", None)
    reported = getattr(u, "cost", None) if u is not None else None
    if isinstance(reported, int | float):
        meter.add(float(reported))
    else:
        meter.tokens(model, *benchmark.usage_of(resp))


def _plan(agent: str, model: str, fallback: str | None, meter: Meter) -> list[str]:
    """Models to try in order: an OpenRouter model twice, then its fallback."""
    if is_openrouter(model) and not _has_key():
        if fallback:
            meter.fell_back(f"{agent}: {model} → {fallback} (no OPENROUTER_API_KEY)")
            return [fallback]
        raise RuntimeError(f"{agent}: {model} needs OPENROUTER_API_KEY and has no fallback")
    tries = [model, model] if is_openrouter(model) else [model]
    return tries + ([fallback] if fallback and fallback != model else [])


def _call(agent: str, kind: str, models: list[str], kw: dict, meter: Meter, note_from: str):
    last: Exception | None = None
    for i, m in enumerate(models):
        if i and m != models[i - 1] and last is not None:
            meter.fell_back(f"{agent}: {note_from} → {m} ({str(last)[:80]})")
        cap = get_settings().trade_lab.max_output_tokens
        args = {**kw, "model": m, "max_completion_tokens": cap}
        if x := _extra(m):
            args["extra_body"] = x
        sent = {k: v for k, v in args.items() if k in ("messages", "tools")}
        started = time.monotonic()
        try:
            completions = _client(m).chat.completions
            resp = completions.parse(**args) if kind == "parse" else completions.create(**args)
        except Exception as e:  # noqa: BLE001 - retried, then the fallback model
            benchmark.record_call(agent, m, sent, started=started, error=str(e)[:500])
            last = e
            continue
        msg = resp.choices[0].message
        tokens = benchmark.usage_of(resp)
        benchmark.record_call(agent, m, sent, msg.model_dump(), started=started, tokens=tokens)
        _charge(m, resp, meter)
        if kind == "parse" and msg.parsed is None:
            last = RuntimeError(f"{agent}: {m} returned no parsed object (refusal: {msg.refusal})")
            continue
        return msg
    raise last or RuntimeError(f"{agent}: no model to call")


def chat(agent, model, messages, meter, *, tools=None, tool_choice=None, fallback=None):
    kw: dict = {"messages": messages}
    if tools:
        kw.update(tools=tools, tool_choice=tool_choice or "auto")
    return _call(agent, "create", _plan(agent, model, fallback, meter), kw, meter, model)


def structured(agent, model, messages, schema: type[T], meter, *, fallback=None) -> T:
    kw = {"messages": messages, "response_format": schema}
    msg = _call(agent, "parse", _plan(agent, model, fallback, meter), kw, meter, model)
    return msg.parsed
