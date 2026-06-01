"""Shared agent infrastructure — typed structured-output calls to OpenAI.

Two contracts:

1. `LLMClient` — anything that can parse a chat into a Pydantic model.
2. `StructuredAgent` — abstract base every agent subclasses. Owns the
    prompt templates, schema, and tier choice; delegates the actual call.

Real impl uses OpenAI's `chat.completions.parse(response_format=YourModel)`.
Tests pass a `FakeLLMClient` that returns deterministic stub objects.
"""

from __future__ import annotations

import logging
import os
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Generic, TypeVar

from openai import OpenAI
from pydantic import BaseModel

from castelino.config import Settings, get_settings


def _resolve_model_id(cfg: "Settings", tier: str) -> str:
    """Pick the live or backtest model ID for `tier`.

    When `BACKTEST_AS_OF` is set, the gpt-4o family is used (cutoff Oct
    2023 → no hindsight on backtest period). Otherwise live
    `cfg.models.<tier>` is used.

    Tier mapping in backtest mode (matches live mode's reasoning vs cheap split):
        reasoning              → backtest.reasoning_model  (gpt-4o)
        fast, significance     → backtest.fast_model       (gpt-4o-mini)
    """
    if os.environ.get("BACKTEST_AS_OF", "").strip():
        bt = cfg.backtest
        if tier == "reasoning":
            return bt.reasoning_model
        return bt.fast_model
    return getattr(cfg.models, tier)

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


# ────────────────────────────── client interface ──────────────────────────


@dataclass
class CallStats:
    n_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_seconds: float = 0.0
    by_model: dict[str, int] = field(default_factory=dict)


class LLMClient(ABC):
    """Anything that can parse a structured response."""

    stats: CallStats

    @abstractmethod
    def parse(
        self,
        *,
        model: str,
        system: str,
        user: str,
        schema: type[T],
        max_tokens: int | None = None,
    ) -> T: ...


# ────────────────────────────── real OpenAI impl ──────────────────────────


class OpenAIClient(LLMClient):
    """Thin wrapper around `openai.OpenAI` with retries + token bookkeeping."""

    def __init__(self, api_key: str | None = None, max_retries: int = 3):
        self._client = OpenAI(api_key=api_key or get_settings().openai_api_key)
        self._max_retries = max_retries
        self.stats = CallStats()

    def parse(
        self,
        *,
        model: str,
        system: str,
        user: str,
        schema: type[T],
        max_tokens: int | None = None,
    ) -> T:
        """Structured-output call against OpenAI.

        Uses the top-level `chat.completions.parse` (the `.beta` namespace was
        deprecated in newer SDKs). Sends `max_completion_tokens` rather than
        `max_tokens` so the same call works for both gpt-4o-class chat models
        AND o-series reasoning models — the latter rejects `max_tokens`.
        """
        cfg = get_settings()
        cap = max_tokens or cfg.openai.max_output_tokens
        last_err: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                start = time.monotonic()
                resp = self._client.chat.completions.parse(
                    model=model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    response_format=schema,
                    max_completion_tokens=cap,
                )
                elapsed = time.monotonic() - start
                self._record(model, resp, elapsed)
                parsed = resp.choices[0].message.parsed
                if parsed is None:
                    raise LLMError(
                        f"OpenAI returned no parsed object for {schema.__name__} "
                        f"(refusal: {resp.choices[0].message.refusal})"
                    )
                return parsed
            except Exception as e:
                last_err = e
                wait = 2**attempt
                log.warning(
                    "OpenAI parse failed (attempt %d/%d): %s — retrying in %ds",
                    attempt + 1, self._max_retries, e, wait,
                )
                time.sleep(wait)
        raise LLMError(f"OpenAI parse exhausted retries: {last_err}") from last_err

    def _record(self, model: str, resp, elapsed: float) -> None:
        self.stats.n_calls += 1
        self.stats.total_seconds += elapsed
        self.stats.by_model[model] = self.stats.by_model.get(model, 0) + 1
        try:
            usage = resp.usage
            self.stats.total_input_tokens += getattr(usage, "prompt_tokens", 0) or 0
            self.stats.total_output_tokens += getattr(usage, "completion_tokens", 0) or 0
        except Exception:
            pass


# ────────────────────────────── fake impl for tests ───────────────────────


class FakeLLMClient(LLMClient):
    """Deterministic stub for unit/integration tests.

    Register a handler per schema name; falls back to building a minimal valid
    instance via `model_construct` if no handler is set.
    """

    def __init__(self) -> None:
        self.stats = CallStats()
        self._handlers: dict[str, Callable[[str, str], BaseModel]] = {}
        self._call_log: list[tuple[str, str, str, str]] = []

    def register(
        self,
        schema_name: str,
        handler: Callable[[str, str], BaseModel],
    ) -> None:
        self._handlers[schema_name] = handler

    @property
    def call_log(self) -> list[tuple[str, str, str, str]]:
        return list(self._call_log)

    def parse(
        self,
        *,
        model: str,
        system: str,
        user: str,
        schema: type[T],
        max_tokens: int | None = None,
    ) -> T:
        self.stats.n_calls += 1
        self.stats.by_model[model] = self.stats.by_model.get(model, 0) + 1
        self._call_log.append((schema.__name__, model, system, user))
        handler = self._handlers.get(schema.__name__)
        if handler is None:
            raise LLMError(
                f"FakeLLMClient: no handler registered for {schema.__name__}. "
                f"Register one with .register({schema.__name__!r}, fn)."
            )
        result = handler(system, user)
        if not isinstance(result, schema):
            raise LLMError(
                f"FakeLLMClient handler for {schema.__name__} returned "
                f"{type(result).__name__}"
            )
        return result


# ────────────────────────────── agent base ────────────────────────────────


_LIVE_CLIENT_SINGLETON: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _LIVE_CLIENT_SINGLETON
    if _LIVE_CLIENT_SINGLETON is None:
        _LIVE_CLIENT_SINGLETON = OpenAIClient()
    return _LIVE_CLIENT_SINGLETON


def set_llm_client(client: LLMClient) -> None:
    """Override the global LLM client (used by tests / `castelino run --mock`)."""
    global _LIVE_CLIENT_SINGLETON
    _LIVE_CLIENT_SINGLETON = client


class StructuredAgent(Generic[T], ABC):
    """Base for any agent that calls the LLM and returns one Pydantic object."""

    name: str
    output_schema: type[T]
    tier: str  # "reasoning" | "fast"
    # Optional per-agent output ceiling. None → fall back to the global
    # cfg.openai.max_output_tokens (unchanged behaviour for existing agents).
    # Reasoning-heavy agents (e.g. deep-research) override this with a larger
    # value so reasoning tokens don't starve the structured output.
    max_output_tokens: int | None = None

    @abstractmethod
    def system_prompt(self) -> str: ...

    @abstractmethod
    def user_prompt(self, **ctx) -> str: ...

    def __call__(self, **ctx) -> T:
        cfg = get_settings()
        model_id = _resolve_model_id(cfg, self.tier)
        log.info("agent=%s model=%s tier=%s", self.name, model_id, self.tier)
        client = get_llm_client()
        return client.parse(
            model=model_id,
            system=self.system_prompt(),
            user=self.user_prompt(**ctx),
            schema=self.output_schema,
            max_tokens=self.max_output_tokens,
        )
