import pytest

from castelino.backtest_regression.runner import run_figure_deviation_case
from tests.backtest.conftest import load_fixtures


@pytest.mark.backtest
@pytest.mark.parametrize(
    "fixture",
    load_fixtures("figure_deviation"),
    ids=lambda f: f["case_id"],
)
def test_figure_deviation_event(fixture):
    result = run_figure_deviation_case(fixture)
    assert result.passed, (
        f"{fixture['case_id']}: expected {fixture['expected']}, "
        f"got {result.actual}, notes={result.notes}"
    )
