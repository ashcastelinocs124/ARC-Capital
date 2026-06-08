from castelino.agents.chat.models import CommandName
from castelino.agents.chat.registry import REGISTRY, CommandSpec

READ = {CommandName.status, CommandName.queue, CommandName.research,
        CommandName.forecast_regime, CommandName.forecast_risk}
MUTATING = {CommandName.run, CommandName.approve, CommandName.reject,
            CommandName.reset, CommandName.mark}


def test_every_command_except_none_has_a_spec():
    expected = set(CommandName) - {CommandName.none}
    assert set(REGISTRY.keys()) == expected


def test_specs_are_command_specs_with_callable():
    for spec in REGISTRY.values():
        assert isinstance(spec, CommandSpec)
        assert callable(spec.run)


def test_read_commands_not_marked_mutating():
    for c in READ:
        assert REGISTRY[c].mutating is False, f"{c} must be read-only"


def test_mutating_commands_marked_mutating():
    for c in MUTATING:
        assert REGISTRY[c].mutating is True, f"{c} must be mutating"


def test_run_requires_headline_arg():
    assert "headline" in REGISTRY[CommandName.run].required_args
    assert "entry_id" in REGISTRY[CommandName.approve].required_args