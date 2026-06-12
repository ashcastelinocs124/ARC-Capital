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
        "ROUTING RULES (follow strictly):\n"
        "- PERSONA OVERRIDE (highest priority): When the user addresses a\n"
        "  persona BY NAME — Dalio, Krugman, El-Erian, Summers, Druckenmiller,\n"
        "  Tudor Jones — route to discuss with args.query = the ENTIRE user\n"
        "  message. This ALWAYS beats market_overview, forecast_regime,\n"
        "  research, and all other routing rules.\n"
        "- ANY question about current general market conditions or 'how the\n"
        "  market is doing' -> market_overview. Do NOT route these to\n"
        "  forecast_regime or forecast_risk.\n"
        "- Explicit regime/risk forecast requests ('what does your model say?',\n"
        "  'run the regime model') -> forecast_regime or forecast_risk.\n"
        "- Specific deep investigative questions -> research.\n\n"
        "ARG RULES:\n"
        "- discuss: put the ENTIRE user message into args.query\n"
        "- research: copy the ENTIRE user query into args.query\n"
        "- run: put the headline into args.headline\n"
        "- approve/reject: use the entry_id the user mentions (e.g. args.entry_id='H-abc123')\n"
        "- Commands without required args (status, queue, forecast_regime, forecast_risk,\n"
        "  market_overview, reset, mark): leave args as {}.\n\n"
        f"COMMANDS:\n{commands}"
    )


def route(*, client: LLMClient, model: str, transcript: list[tuple[str, str]]) -> AssistantTurn:
    return client.parse(
        model=model,
        system=build_system_prompt(),
        user="\n".join(f"{role.upper()}: {text}" for role, text in transcript),
        schema=AssistantTurn,
    )