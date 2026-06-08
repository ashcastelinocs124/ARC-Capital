from __future__ import annotations

from collections.abc import Callable

from rich.console import Console

from castelino.agents.base import LLMClient
from castelino.agents.chat.session import ChatSession

_EXIT = {"exit", "quit", ":q"}


def _default_read_line(prompt: str) -> str:  # pragma: no cover (interactive)
    return input(prompt)


def run_repl(*, client: LLMClient | None = None,
             confirm: Callable[[str], bool] | None = None,
             read_line: Callable[[str], str] | None = None) -> None:
    console = Console()
    read_line = read_line or _default_read_line
    sess = ChatSession(client=client, confirm=confirm)
    console.print("CKM Capital assistant — type 'exit' to quit.", style="bold")
    while True:
        try:
            user = read_line("\nyou ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user:
            continue
        if user.lower() in _EXIT:
            break
        res = sess.handle_turn(user)
        console.print(res.reply, markup=False)
        if res.error:
            console.print(f"\u26a0 {res.error}", markup=False, style="yellow")
        elif res.skipped:
            console.print("(skipped — not confirmed)", markup=False, style="dim")
        elif res.output:
            console.print(res.output, markup=False, style="cyan")
    console.print("bye.", style="dim")
