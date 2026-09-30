import pytest

from castelino.agents.base import FakeLLMClient
from castelino.agents.update.agent import write_update
from tests.update_fixtures import make_snapshot, make_update


@pytest.fixture
def fake(monkeypatch):
    client = FakeLLMClient()
    client.register("DailyUpdate", lambda system, user: make_update())
    monkeypatch.setattr("castelino.agents.base._LIVE_CLIENT_SINGLETON", client)
    return client


def test_prompt_contains_snapshot_and_both_memory_tiers(fake):
    out = write_update(make_snapshot(), "SHORT-MEMORY-MARKER", "LONG-MEMORY-MARKER")
    _schema, _model, system, user = fake.call_log[0]
    assert out.headline.startswith("Hot Core PCE")
    assert "SHORT-MEMORY-MARKER" in user and "LONG-MEMORY-MARKER" in user
    assert "Core PCE y/y" in user and "BCOM" in user  # snapshot JSON incl. data_gaps
    assert "only" in system.lower() and "snapshot" in system.lower()


def test_guard_errors_are_fed_back_on_retry(fake):
    write_update(make_snapshot(), "", "", ["+12bp", "9.9%"])
    user = fake.call_log[0][3]
    assert "+12bp" in user and "9.9%" in user


def test_no_guard_section_on_first_attempt(fake):
    write_update(make_snapshot(), "", "")
    assert "not in the snapshot" not in fake.call_log[0][3]


def test_model_tier_comes_from_config(fake):
    write_update(make_snapshot(), "", "")
    assert fake.call_log[0][1]  # a model id was resolved for the configured tier
