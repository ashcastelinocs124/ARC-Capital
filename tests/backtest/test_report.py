from pathlib import Path

from castelino.backtest_regression.models import CaseResult
from castelino.backtest_regression.report import write_report


def _r(component, passed, case_id=None):
    return CaseResult(
        case_id=case_id or f"{component}_x",
        component=component,
        passed=passed,
        actual={}, expected={},
    )


def test_write_report_creates_md_and_json(tmp_path):
    results = [
        _r("risk_off", True, "r1"),
        _r("risk_off", False, "r2"),
        _r("figure_deviation", True, "f1"),
        _r("materialize_order", True, "m1"),
    ]
    out_dir = write_report(results, base_dir=tmp_path)
    assert (out_dir / "report.md").exists()
    assert (out_dir / "results.json").exists()
    md = (out_dir / "report.md").read_text()
    assert "risk_off" in md
    assert "1/2 passed" in md


def test_report_handles_empty_input(tmp_path):
    out_dir = write_report([], base_dir=tmp_path)
    assert (out_dir / "report.md").exists()
    md = (out_dir / "report.md").read_text()
    assert "Backtest Regression" in md


def test_report_writes_under_base_dir(tmp_path):
    results = [_r("risk_off", True)]
    out_dir = write_report(results, base_dir=tmp_path)
    # out_dir must be under base_dir, with a timestamp child
    assert tmp_path in out_dir.parents or out_dir.parent == tmp_path
