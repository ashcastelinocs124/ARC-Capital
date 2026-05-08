from typer.testing import CliRunner

from castelino.orchestrator.cli import app


def test_persona_build_help_exists():
    r = CliRunner().invoke(app, ["persona-build", "--help"])
    assert r.exit_code == 0
    assert "persona" in r.stdout.lower()


def test_persona_build_requires_persona_arg():
    r = CliRunner().invoke(app, ["persona-build"])
    assert r.exit_code != 0
