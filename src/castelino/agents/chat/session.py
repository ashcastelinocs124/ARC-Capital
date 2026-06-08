from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass
from castelino.agents.base import LLMClient, get_llm_client
from castelino.agents.chat.models import AssistantTurn, CommandName
from castelino.agents.chat.router import route
from castelino.agents.chat.registry import REGISTRY
from castelino.config import get_settings

@dataclass
class TurnResult:
    reply: str
    command: CommandName | None = None
    executed: bool = False
    output: str | None = None
    error: str | None = None
    skipped: bool = False

def _default_confirm(prompt: str) -> bool:
    import typer
    return typer.confirm(prompt)

class ChatSession:
    def __init__(self, *, client: LLMClient | None = None,
                confirm: Callable[[str], bool] | None = None):
        self._client = client or get_llm_client()
        self._confirm = confirm or _default_confirm
        self._model = get_settings().models.fast
        self._max_context = get_settings().chat.max_context_turns
        self._transcript: list[tuple[str, str]] = []

    def handle_turn(self, user_input: str) -> TurnResult:
        self._transcript.append(("user", user_input))
        turn = route(
            client=self._client,
            model=self._model,
            transcript=self._transcript[-self._max_context:]
        )
        self._transcript.append(("assistant", turn.reply))
        result = TurnResult(reply=turn.reply)

        if turn.command is None or turn.command is CommandName.none:
            return result

        spec = REGISTRY.get(turn.command)
        if not spec:
            return result

        args = turn.args or {}
        missing_args = [a for a in spec.required_args if not args.get(a)]
        if missing_args:
            result.error = f"Missing args: {', '.join(missing_args)}"
            return result

        if spec.mutating and not self._confirm(
            f"Run: ckm {turn.command.value} with args {args}? [y/N]"
        ):
            result.command = turn.command
            result.skipped = True
            return result

        try:
            result.output = spec.run(args)
            result.executed = True
            result.command = turn.command
            self._transcript.append(
                ("system", f"Executed {turn.command.value}: {result.output[:200]}")
            )
        except Exception as e:
            result.error = f"{type(e).__name__}: {e}"

        return result