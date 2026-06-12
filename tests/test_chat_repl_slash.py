"""Tests for slash command parsing and dispatch in the chat REPL."""
from castelino.agents.chat.models import CommandName
from castelino.agents.chat.registry import REGISTRY, CommandSpec
from castelino.agents.research.deep.sonar_client import SonarResult


def test_parse_slash_matches_simple():
    from castelino.agents.chat.repl import _parse_slash

    assert _parse_slash("/status") == ("status", "")
    assert _parse_slash("/marketstatus") == ("marketstatus", "")


def test_parse_slash_matches_with_args():
    from castelino.agents.chat.repl import _parse_slash

    result = _parse_slash("/research what's happening with yields")
    assert result == ("research", "what's happening with yields")


def test_parse_slash_ignores_non_slash():
    from castelino.agents.chat.repl import _parse_slash

    assert _parse_slash("how's the market?") is None
    assert _parse_slash("status") is None


def test_parse_slash_handles_extra_whitespace():
    from castelino.agents.chat.repl import _parse_slash

    assert _parse_slash("  /status  ") == ("status", "")


def test_slash_aliases_cover_all_non_none_commands():
    from castelino.agents.chat.repl import SLASH_ALIASES

    expected = set(CommandName) - {CommandName.none}
    assert set(SLASH_ALIASES.values()) == expected


def test_slash_unknown_command_returns_none():
    from castelino.agents.chat.repl import _resolve_slash

    assert _resolve_slash("nonexistent", "") is None


def test_slash_builds_args_for_required():
    from castelino.agents.chat.repl import _resolve_slash

    resolved = _resolve_slash("research", "what's the yield curve doing")
    assert resolved is not None
    cmd, args = resolved
    assert cmd == CommandName.research
    assert args == {"query": "what's the yield curve doing"}


def test_slash_builds_empty_args_for_no_required():
    from castelino.agents.chat.repl import _resolve_slash

    resolved = _resolve_slash("status", "")
    assert resolved is not None
    _cmd, args = resolved
    assert args == {}


def test_slash_status_dispatches(monkeypatch):
    from castelino.agents.chat.repl import _execute_slash

    calls = []
    monkeypatch.setitem(
        REGISTRY, CommandName.status,
        CommandSpec(run=lambda a: (calls.append(a), "NAV $1,000")[1],
                    mutating=False, help="test"),
    )
    result = _execute_slash("status", "", lambda p: True)
    assert result == "NAV $1,000"
    assert calls == [{}]


def test_slash_market_overview_dispatches(monkeypatch):
    from castelino.agents.chat.repl import _execute_slash

    monkeypatch.setitem(
        REGISTRY, CommandName.market_overview,
        CommandSpec(
            run=lambda a: "- Equities: flat\n- Rates: up",
            mutating=False, help="test"),
    )
    result = _execute_slash("marketstatus", "", lambda p: True)
    assert "Equities" in result
    assert "Rates" in result


def test_slash_unknown_returns_error():
    from castelino.agents.chat.repl import _execute_slash

    result = _execute_slash("bogus", "", lambda p: True)
    assert "unknown" in result.lower()


def test_slash_mutating_skipped_when_not_confirmed(monkeypatch):
    from castelino.agents.chat.repl import _execute_slash

    monkeypatch.setitem(
        REGISTRY, CommandName.reset,
        CommandSpec(run=lambda a: "wiped", mutating=True, help="test"),
    )
    result = _execute_slash("reset", "", lambda p: False)
    assert result is None


def test_slash_mutating_runs_when_confirmed(monkeypatch):
    from castelino.agents.chat.repl import _execute_slash

    monkeypatch.setitem(
        REGISTRY, CommandName.reset,
        CommandSpec(run=lambda a: "wiped", mutating=True, help="test"),
    )
    result = _execute_slash("reset", "", lambda p: True)
    assert result == "wiped"
