from __future__ import annotations

from castelino.agents.base import LLMClient
from castelino.agents.chat.models import AssistantTurn
from castelino.agents.chat.registry import REGISTRY


def build_system_prompt() -> str:
    commands = "\n".join(
        f"- {cmd.value}{' (' + ', '.join(spec.required_args) + ')' if spec.required_args else ''}: "
        f"{spec.help}{'  [MUTATING — confirmed before running]' if spec.mutating else ''}"
        for cmd, spec in REGISTRY.items()
    )
    return (
        "You are the CKM Capital assistant, a CLI for a multi-agent macro fund.\n"
        "Each turn, reply conversationally AND optionally dispatch ONE command.\n"
        "Set command=null to just chat. If a required arg is missing from what\n"
        "the user said, ask for it in your reply and leave command=null.\n\n"
        "ARG RULES:\n"
        "- research: copy the ENTIRE user query into args.query\n"
        "- run: put the headline into args.headline\n"
        "- approve/reject: use the entry_id the user mentions (e.g. args.entry_id='H-abc123')\n"
        "- Commands without required args (status, queue, forecast_regime, forecast_risk,\n"
        "  reset, mark): leave args as {}.\n\n"
        f"COMMANDS:\n{commands}"
    )


def route(*, client: LLMClient, model: str, transcript: list[tuple[str, str]]) -> AssistantTurn:
    return client.parse(
        model=model,
        system=build_system_prompt(),
        user="\n".join(f"{role.upper()}: {text}" for role, text in transcript),
        schema=AssistantTurn,
    )