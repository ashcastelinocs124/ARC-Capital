from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass
from castelino.agents.base import LLMClient, get_llm_client
from castelino.agents.chat.models import AssistantTurn, CommandName
from castelino.agents.chat.router import route
from castelino.agents.chat.registry import REGISTRY
from castelino.config import get_settings

# ── model router ──────────────────────────────────────────────────────────

_COMPLEX_TRIGGERS: list[str] = [
    "research", "analyze", "explain", "recommend", "forecast",
    "predict", "compare", "evaluate", "what if", "how would",
    "strategy", "should i", "is it a good", "backtest",
    "run the pipeline", "trigger the",
]

def _is_simple_query(text: str) -> bool:
    """Heuristic classifier: short queries without complex keywords → simple."""
    words = text.split()
    if len(words) > 12:
        return False
    lower = text.lower()
    if any(t in lower for t in _COMPLEX_TRIGGERS):
        return False
    return True

# ── session ───────────────────────────────────────────────────────────────

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
        self._max_context = get_settings().chat.max_context_turns
        self._transcript: list[tuple[str, str]] = []

    def _select_model(self, user_input: str) -> str:
        cfg = get_settings()
        if _is_simple_query(user_input):
            return cfg.models.chat_lightweight
        return cfg.models.fast

    def handle_turn(self, user_input: str) -> TurnResult:
        self._transcript.append(("user", user_input))
        model = self._select_model(user_input)
        turn = route(
            client=self._client,
            model=model,
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