from typer.testing import CliRunner
from castelino.orchestrator.cli import app


def test_persona_refresh_help_lists_speaker():
    r = CliRunner().invoke(app, ["persona-refresh", "--help"])
    assert r.exit_code == 0
    assert "speaker" in r.stdout.lower()


def test_speech_test_dry_run_command_exists():
    from typer.testing import CliRunner
    from castelino.orchestrator.cli import app
    r = CliRunner().invoke(app, ["speech-test", "--help"])
    assert r.exit_code == 0
    assert "dry-run" in r.stdout.lower() or "dry_run" in r.stdout.lower()
