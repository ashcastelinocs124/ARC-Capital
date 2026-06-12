from __future__ import annotations

import logging
import re
import select
import sys
import termios
import time
import tty
import warnings

warnings.filterwarnings("ignore", message=".*allowed_objects.*")

from collections.abc import Callable

import pyfiglet
from rich.console import Console
from rich.style import Style
from rich.text import Text

from castelino.agents.base import LLMClient
from castelino.agents.chat.models import CommandName
from castelino.agents.chat.registry import (
    REGISTRY,
    _clear_pending_discuss,
    _clear_pending_research,
    _discuss_pending_persona,
    _handle_discuss_message,
    _research_pending_id,
    _submit_research_answers,
)
from castelino.agents.chat.session import ChatSession

_NOISY_LOGGERS = ["httpx", "openai", "langgraph", "castelino.agents.base", "castelino.data", "castelino.agents.research", "chromadb.telemetry", "chromadb.telemetry.product.posthog"]

_EXIT = {"exit", "quit", ":q"}
_SPLASH_FONT = "big"
_WORD_DELAY = 0.4
_PAUSE_AFTER_LOGO = 0.2

_SLASH_RE = re.compile(r"^/(\w+)\s*(.*)")

SLASH_ALIASES: dict[str, CommandName] = {
    "status": CommandName.status,
    "queue": CommandName.queue,
    "research": CommandName.research,
    "deep-research": CommandName.research,
    "forecast": CommandName.forecast_regime,
    "regime": CommandName.forecast_regime,
    "forecast-risk": CommandName.forecast_risk,
    "risk": CommandName.forecast_risk,
    "marketstatus": CommandName.market_overview,
    "market": CommandName.market_overview,
    "run": CommandName.run,
    "approve": CommandName.approve,
    "reject": CommandName.reject,
    "mark": CommandName.mark,
    "reset": CommandName.reset,
    "discuss": CommandName.discuss,
}


def _parse_slash(text: str) -> tuple[str, str] | None:
    m = _SLASH_RE.match(text.strip())
    if not m:
        return None
    return m.group(1).lower(), m.group(2).strip()


def _resolve_slash(alias: str, raw_args: str) -> tuple[CommandName, dict[str, str]] | None:
    cmd = SLASH_ALIASES.get(alias)
    if cmd is None:
        return None
    spec = REGISTRY.get(cmd)
    if spec is None:
        return None
    args: dict[str, str] = {}
    if spec.required_args:
        args[spec.required_args[0]] = raw_args
    return cmd, args


def _execute_slash(alias: str, raw_args: str, confirm: Callable[[str], bool]) -> str | None:
    resolved = _resolve_slash(alias, raw_args)
    if resolved is None:
        return f"Unknown slash command: /{alias}"
    cmd, args = resolved
    spec = REGISTRY[cmd]
    if spec.mutating and not confirm(f"Run: ckm {cmd.value} with args {args}? [y/N]"):
        return None
    try:
        return spec.run(args)
    except Exception as e:
        return f"{type(e).__name__}: {e}"


def _slash_help() -> str:
    from collections import defaultdict
    groups: dict[CommandName, list[str]] = defaultdict(list)
    for alias, cmd in SLASH_ALIASES.items():
        groups[cmd].append(alias)
    lines = []
    for cmd in CommandName:
        if cmd is CommandName.none:
            continue
        aliases = groups.get(cmd)
        if not aliases:
            continue
        spec = REGISTRY.get(cmd)
        if not spec:
            continue
        primary = min(aliases, key=len)
        others = [a for a in aliases if a != primary]
        label = f"/{primary}"
        if others:
            label += ", /" + ", /".join(sorted(others))
        tail = spec.help
        if spec.mutating:
            tail += "  \u26a0 MUTATING"
        lines.append(f"  {label:<36}  {tail}")
    return "\n".join(lines)


def _read_line(console: Console) -> str:
    """Read a line with live slash-command completion."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    completions_visible = False
    buf = ""
    selected = -1
    last_partial = ""

    def _show(partial: str, sel: int) -> None:
        nonlocal completions_visible
        matches = [a for a in sorted(SLASH_ALIASES) if a.startswith(partial)]
        max_lines = min(max(len(matches), 1), 10)
        sys.stdout.write("\033[s")
        sys.stdout.write("\n\n")
        for i in range(10):
            sys.stdout.write("\r\033[K")
            if i < len(matches):
                m = matches[i]
                cmd = SLASH_ALIASES[m]
                spec = REGISTRY[cmd]
                mut = " ⚠" if spec.mutating else ""
                if i == sel:
                    sys.stdout.write(f"\033[7m  /{m}{mut}\033[0m")
                else:
                    sys.stdout.write(f"  /{m}{mut}")
            sys.stdout.write("\n")
        sys.stdout.write(f"\033[{max_lines + 1}A")
        sys.stdout.write("\033[u")
        sys.stdout.flush()
        completions_visible = True

    def _clear() -> None:
        nonlocal completions_visible
        if not completions_visible:
            return
        sys.stdout.write("\033[s")
        sys.stdout.write("\n\n")
        for _ in range(10):
            sys.stdout.write("\r\033[K\n")
        sys.stdout.write("\033[11A\033[u")
        sys.stdout.flush()
        completions_visible = False

    try:
        tty.setraw(fd)
        while True:
            ch = sys.stdin.read(1)
            if ch in ("\r", "\n"):
                _clear()
                sys.stdout.write("\n")
                break
            elif ch == "\x7f":
                if buf:
                    buf = buf[:-1]
                    sys.stdout.write("\b \b")
            elif ch == "\x03":
                _clear()
                sys.stdout.write("\n")
                raise KeyboardInterrupt
            elif ch == "\x04":
                if not buf:
                    _clear()
                    raise EOFError
                buf += ch
                sys.stdout.write(ch)
            elif ch == "\t":
                if buf.startswith("/") and completions_visible:
                    partial = buf[1:]
                    matches = [a for a in sorted(SLASH_ALIASES) if a.startswith(partial)]
                    idx = selected if 0 <= selected < len(matches) else 0
                    if matches:
                        new_buf = f"/{matches[idx]} "
                        buf = new_buf
                        sys.stdout.write(f"\r\033[K> {new_buf}")
            elif ch == "\x1b":
                if select.select([fd], [], [], 0.05)[0]:
                    if sys.stdin.read(1) == "[":
                        code = sys.stdin.read(1)
                        if code == "A":
                            if completions_visible:
                                partial = buf[1:]
                                matches = [a for a in sorted(SLASH_ALIASES) if a.startswith(partial)]
                                if matches:
                                    selected = (selected - 1) % len(matches)
                                    _show(partial, selected)
                        elif code == "B":
                            if completions_visible:
                                partial = buf[1:]
                                matches = [a for a in sorted(SLASH_ALIASES) if a.startswith(partial)]
                                if matches:
                                    selected = (selected + 1) % len(matches)
                                    _show(partial, selected)
                        else:
                            while True:
                                c = sys.stdin.read(1)
                                if c.isalpha() or c == "~":
                                    break
                else:
                    _clear()
                    sys.stdout.write("\n")
                    raise KeyboardInterrupt
            elif ch.isprintable():
                buf += ch
                sys.stdout.write(ch)
            sys.stdout.flush()
            if buf.startswith("/"):
                partial = buf[1:]
                if partial != last_partial:
                    selected = -1
                last_partial = partial
                _show(partial, selected)
            elif completions_visible:
                _clear()
                selected = -1
        return buf
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


_MARKET_SHORTCUTS = [
    "how's the market", "how is the market", "how are markets",
    "general market", "market update", "what are markets doing",
    "what is the market doing", "market overview", "market snapshot",
    "broad market", "how's markets", "give me a market",
]


def _is_market_shortcut(text: str) -> bool:
    lower = text.lower()
    if any(m in lower for m in _MARKET_SHORTCUTS):
        from castelino.agents.chat.registry import _PERSONAS
        for pid in _PERSONAS:
            if pid in lower:
                return False
        return True
    return False


def _rule(console: Console) -> None:
    console.print("─" * max(console.width - 1, 20), style=Style(color="blue", dim=True))


def _quiet_logging() -> None:
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    logging.getLogger("chromadb.telemetry").setLevel(logging.CRITICAL)
    logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)
    warnings.filterwarnings("ignore", message=".*allowed_objects.*", category=DeprecationWarning)


def _show_splash(console: Console) -> None:
    ckm = pyfiglet.figlet_format("CKM", font=_SPLASH_FONT).rstrip()
    capital = pyfiglet.figlet_format("CAPITAL", font=_SPLASH_FONT).rstrip()
    console.print(ckm, style=Style(color="blue", bold=True))
    time.sleep(_WORD_DELAY)
    console.print(capital, style=Style(color="blue", bold=True))
    time.sleep(_PAUSE_AFTER_LOGO)
    tagline = Text("multi-agent macro fund", style=Style(color="blue", dim=True, italic=True))
    console.print(tagline, justify="center")
    console.print()


def _show_footer(console: Console) -> None:
    cmds = " ".join(sorted(SLASH_ALIASES.keys()))
    console.print(f"? for shortcuts | /{cmds}", style=Style(color="blue", dim=True))


def run_repl(*, client: LLMClient | None = None,
             confirm: Callable[[str], bool] | None = None) -> None:
    _quiet_logging()
    console = Console()
    _show_splash(console)
    sess = ChatSession(client=client, confirm=confirm)
    console.print("CKM Capital assistant — type 'exit' to quit.", style="bold")
    while True:
        _rule(console)
        sys.stdout.write("> \n")
        sys.stdout.flush()
        _rule(console)
        sys.stdout.write("\033[2F\r> ")
        sys.stdout.flush()
        try:
            user = _read_line(console).strip()
        except (EOFError, KeyboardInterrupt):
            break
        console.print()
        _show_footer(console)
        console.print()
        if not user:
            continue
        if user.lower() in _EXIT:
            _clear_pending_research()
            _clear_pending_discuss()
            break
        slash = _parse_slash(user)
        if slash:
            _clear_pending_research()
            _clear_pending_discuss()
            alias, raw_args = slash
            if alias in _EXIT:
                break
            result = _execute_slash(alias, raw_args, sess._confirm)
            if result is None:
                console.print("(skipped — not confirmed)", markup=False, style="dim")
            else:
                console.print(result, markup=False, style="cyan")
        elif _is_market_shortcut(user):
            result = _execute_slash("marketstatus", "", sess._confirm)
            console.print(result, markup=False, style="cyan")
        elif _research_pending_id:
            console.print(_submit_research_answers(user), markup=False, style="cyan")
        elif _discuss_pending_persona:
            console.print(_handle_discuss_message(user), markup=False, style="cyan")
        else:
            with console.status("[bold green]thinking...[/]", spinner="dots"):
                res = sess.handle_turn(user)
            console.print(res.reply, markup=False)
            if res.error:
                console.print(f"\u26a0 {res.error}", markup=False, style="yellow")
            elif res.skipped:
                console.print("(skipped — not confirmed)", markup=False, style="dim")
            elif res.output:
                console.print(res.output, markup=False, style="cyan")
    console.print("bye.", style="dim")
