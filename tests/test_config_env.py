"""SEC_USER_AGENT env override (keeps the SEC contact email out of config.yaml)."""

from castelino.config import load_settings


def test_sec_user_agent_comes_from_env_when_set(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "ARC Research ci@example.com")
    load_settings.cache_clear()  # settings are cached; other tests may have loaded them first
    try:
        assert load_settings().adoption.sec_user_agent == "ARC Research ci@example.com"
    finally:
        monkeypatch.delenv("SEC_USER_AGENT")
        load_settings.cache_clear()
