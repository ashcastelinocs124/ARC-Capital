"""Pieces the GitHub Actions publish workflow relies on (.github/workflows/publish.yml)."""

import os
import subprocess
from pathlib import Path

from castelino.config import load_settings

ROOT = Path(__file__).resolve().parents[1]


def test_sec_user_agent_comes_from_env_when_set(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "ARC Research ci@example.com")
    load_settings.cache_clear()  # settings are cached; other tests may have loaded them first
    try:
        assert load_settings().adoption.sec_user_agent == "ARC Research ci@example.com"
    finally:
        monkeypatch.delenv("SEC_USER_AGENT")
        load_settings.cache_clear()


def _sync(mode, root, state):
    env = {**os.environ, "ARC_ROOT": str(root)}
    subprocess.run(
        ["bash", str(ROOT / "scripts/state_sync.sh"), mode, str(state)], check=True, env=env
    )


def test_state_round_trips_and_skips_the_lock(tmp_path):
    root, state = tmp_path / "repo", tmp_path / "state"
    (root / "data/updates").mkdir(parents=True)
    (root / "data/updates/2026-10-07.json").write_text("{}")
    (root / "data/update_agent").mkdir(parents=True)
    (root / "data/update_agent/run.lock").write_text("123")
    (root / "data/adoption").mkdir(parents=True)
    (root / "data/adoption/adoption.db").write_bytes(b"db")
    (root / "data/adoption/universe_seed.csv").write_text("tracked in git, not state")
    _sync("push", root, state)
    assert (state / "data/updates/2026-10-07.json").is_file()
    assert (state / "data/adoption/adoption.db").read_bytes() == b"db"
    assert not (state / "data/update_agent/run.lock").exists()
    assert not (state / "data/adoption/universe_seed.csv").exists()

    fresh = tmp_path / "fresh"
    fresh.mkdir()  # in CI this is the code checkout
    _sync("pull", fresh, state)
    assert (fresh / "data/updates/2026-10-07.json").is_file()
    assert (fresh / "data/adoption/adoption.db").read_bytes() == b"db"
