"""Maps each chat CommandName to a thin callable + safety metadata.

Mutating-ness lives HERE, never in the LLM output — the confirm gate trusts
this table, not the model.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from castelino.agents.chat.models import CommandName


@dataclass(frozen=True)
class CommandSpec:
    run: Callable[[dict[str, str]], str]   # takes args, returns printable summary
    mutating: bool
    help: str
    required_args: list[str] = field(default_factory=list)


# Stub callables — real bodies wired in Task 4.
def _todo(_args: dict[str, str]) -> str:
    return "(not implemented yet)"


REGISTRY: dict[CommandName, CommandSpec] = {
    CommandName.status: CommandSpec(_todo, False, "Show NAV, exposure, positions, journal counts."),
    CommandName.queue: CommandSpec(_todo, False, "List pending approval items."),
    CommandName.research: CommandSpec(_todo, False, "Run the deep-research engine.", ["query"]),
    CommandName.forecast_regime: CommandSpec(_todo, False, "Growth+inflation next-month MoM forecast."),
    CommandName.forecast_risk: CommandSpec(_todo, False, "Risk-off probability forecast."),
    CommandName.run: CommandSpec(_todo, True, "Fire the trading pipeline from a headline.", ["headline"]),
    CommandName.approve: CommandSpec(_todo, True, "Approve a pending item.", ["entry_id"]),
    CommandName.reject: CommandSpec(_todo, True, "Reject a pending item.", ["entry_id"]),
    CommandName.reset: CommandSpec(_todo, True, "Wipe journals + portfolio (demo only)."),
    CommandName.mark: CommandSpec(_todo, True, "Run the daily mark loop."),
}