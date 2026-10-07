from castelino.agents.update.refit import run_refit
from castelino.agents.update.registry import ModelRegistry
from tests.update_fixtures import make_forecast


def months(m):
    return lambda: {"growth": m, "inflation": m}


def test_first_refit_promotes_and_writes_history(tmp_path):
    reg = ModelRegistry(tmp_path / "models")
    out = run_refit(
        registry=reg, tolerance=0.02, refit_fn=make_forecast, latest_month_fn=months("2026-09")
    )
    assert out == "promoted: growth, inflation"
    assert reg.current() is not None
    assert (tmp_path / "models" / "history.json").is_file()


def test_no_new_data_returns_none_and_does_not_refit(tmp_path):
    reg = ModelRegistry(tmp_path / "models")
    v = reg.save_version(make_forecast(feature_month="2026-08-01"))
    reg.set_pointer("growth", v)
    reg.set_pointer("inflation", v)
    calls = []
    out = run_refit(
        registry=reg,
        tolerance=0.02,
        refit_fn=lambda: calls.append(1) or make_forecast(),
        latest_month_fn=months("2026-08"),
    )
    assert out is None and calls == []


def test_worse_refit_is_kept_but_history_saved(tmp_path):
    reg = ModelRegistry(tmp_path / "models")
    v = reg.save_version(make_forecast(g_brier=0.10, i_brier=0.10, feature_month="2026-07-01"))
    reg.set_pointer("growth", v)
    reg.set_pointer("inflation", v)
    out = run_refit(
        registry=reg,
        tolerance=0.02,
        refit_fn=lambda: make_forecast(g_brier=0.30, i_brier=0.30),
        latest_month_fn=months("2026-09"),
    )
    assert out == "refit kept the champions"
    assert (tmp_path / "models" / "history.json").is_file()


def test_refresh_lists_model_refit_job():
    from castelino.dashboard.endpoints import refresh

    assert "model_refit" in refresh._RUNNERS and refresh.LABELS["model_refit"] == "Model refit"
