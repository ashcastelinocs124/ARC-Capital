from castelino.agents.update.gate import decide, run_gate
from castelino.agents.update.models import Decision
from tests.update_fixtures import make_forecast


def test_better_challenger_is_promoted():
    assert decide(0.236, 0.231, 0.02).decision == Decision.PROMOTED


def test_worse_beyond_tolerance_is_kept():
    g = decide(0.189, 0.214, 0.02)
    assert g.decision == Decision.KEPT and "0.025" in g.reason


def test_worse_exactly_at_tolerance_is_promoted():
    assert decide(0.189, 0.209, 0.02).decision == Decision.PROMOTED


def test_no_champion_promotes():
    assert decide(None, 0.25, 0.02).decision == Decision.PROMOTED


def test_challenger_without_metrics_is_kept():
    assert decide(0.2, None, 0.02).decision == Decision.KEPT


def test_models_are_judged_independently():
    champion = make_forecast(g_brier=0.236, i_brier=0.189)
    challenger = make_forecast(g_brier=0.231, i_brier=0.214)
    res = run_gate(challenger, champion, 0.02)
    assert res.growth.decision == Decision.PROMOTED
    assert res.inflation.decision == Decision.KEPT


def test_first_run_with_no_champion_promotes_both():
    res = run_gate(make_forecast(), None, 0.02)
    assert res.growth.decision == res.inflation.decision == Decision.PROMOTED
