from typer.testing import CliRunner
from castelino.orchestrator.cli import app


def test_persona_refresh_help_lists_speaker():
    r = CliRunner().invoke(app, ["persona-refresh", "--help"])
    assert r.exit_code == 0
    assert "speaker" in r.stdout.lower()
