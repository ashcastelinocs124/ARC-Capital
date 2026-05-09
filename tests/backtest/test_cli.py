from pathlib import Path
from typer.testing import CliRunner

from castelino.orchestrator.cli import app


def test_backtest_regression_command_runs_materialize_only(tmp_path):
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["backtest-regression", "--components", "materialize_order",
         "--out-dir", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    # report dir written under tmp_path
    children = list(tmp_path.iterdir())
    assert len(children) == 1
    assert (children[0] / "report.md").exists()


def test_backtest_regression_filters_components(tmp_path):
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["backtest-regression", "--components", "risk_off",
         "--out-dir", str(tmp_path)],
    )
    assert result.exit_code == 0
    md = next(iter(tmp_path.iterdir())) / "report.md"
    text = md.read_text()
    assert "risk_off" in text
    assert "figure_deviation" not in text
    assert "materialize_order" not in text
