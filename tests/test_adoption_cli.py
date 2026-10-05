from typer.testing import CliRunner

from castelino.adoption import cli as adoption_cli
from castelino.adoption.index import aggregate
from castelino.adoption.models import Company, CompanyScore
from castelino.adoption.store import AdoptionStore
from castelino.config import AdoptionCfg, get_settings
from castelino.orchestrator.cli import app as ckm_app

runner = CliRunner()


def test_adoption_is_registered_on_ckm():
    r = runner.invoke(ckm_app, ["adoption", "--help"])
    assert r.exit_code == 0
    assert "universe-refresh" in r.output and "run" in r.output and "show" in r.output


def test_run_fails_fast_without_sec_user_agent(monkeypatch):
    cfg = get_settings().model_copy(update={"adoption": AdoptionCfg(sec_user_agent="")})
    monkeypatch.setattr(adoption_cli, "get_settings", lambda: cfg)
    r = runner.invoke(adoption_cli.app, ["run"])
    assert r.exit_code != 0
    assert "sec_user_agent" in r.output


def test_show_prints_headline(tmp_path, monkeypatch):
    store = AdoptionStore(tmp_path / "a.db")
    scores = [
        CompanyScore(Company("A", "large", "Energy", 10.0), {}, {}, 70.0, 3),
        CompanyScore(Company("B", "small", "Energy", 5.0), {}, {}, 40.0, 3),
    ]
    store.save_period("2026-10-01", scores, aggregate(scores))
    monkeypatch.setattr(adoption_cli, "_store", lambda: store)
    r = runner.invoke(adoption_cli.app, ["show"])
    assert r.exit_code == 0
    assert "2026-10-01" in r.output and "spread" in r.output and "-30.0" in r.output


def test_show_with_no_data(tmp_path, monkeypatch):
    monkeypatch.setattr(adoption_cli, "_store", lambda: AdoptionStore(tmp_path / "empty.db"))
    r = runner.invoke(adoption_cli.app, ["show"])
    assert r.exit_code == 0 and "No adoption data yet" in r.output
