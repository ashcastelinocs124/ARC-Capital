from __future__ import annotations

from castelino.agents.base import LLMClient
from castelino.agents.chat.models import AssistantTurn
from castelino.agents.chat.registry import REGISTRY


def build_system_prompt() -> str:
    commands = "\n".join(
        f"- {cmd.value}: {spec.help}{' (CONFIRMED)' if spec.mutating else ''}"
        for cmd, spec in REGISTRY.items()
    )
    return (
        "You are the CKM Capital assistant\n"
        "Each turn, reply conversationally AND optionally pick ONE command to run\n"
        "Mutating commands require human confirmation before executing\n"
        f"Available commands:\n{commands}"
    )


def route(*, client: LLMClient, model: str, transcript: list[tuple[str, str]]) -> AssistantTurn:
    return client.parse(
        model=model,
        system=build_system_prompt(),
        user="\n".join(f"{role.upper()}: {text}" for role, text in transcript),
        schema=AssistantTurn,
    )