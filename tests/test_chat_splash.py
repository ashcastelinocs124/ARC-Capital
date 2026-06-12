from __future__ import annotations

import re
from io import StringIO
from unittest.mock import patch

import pyfiglet
from rich.console import Console

from castelino.agents.chat.repl import _SPLASH_FONT, _show_splash

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _plain(text: str) -> str:
    return _ANSI.sub("", text)


def test_pyfiglet_renders_ckm():
    result = pyfiglet.figlet_format("CKM", font="big")
    assert result.strip()


def test_pyfiglet_renders_capital():
    result = pyfiglet.figlet_format("CAPITAL", font="big")
    assert result.strip()


def test_show_splash_prints_tagline():
    output = StringIO()
    console = Console(file=output, force_terminal=True, width=80)
    with patch("time.sleep"):
        _show_splash(console)
    text = _plain(output.getvalue())
    assert "multi-agent macro fund" in text
    assert len(text.split("\n")) > 10
