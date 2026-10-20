import pytest


@pytest.fixture(autouse=True)
def _benchmark_dir(tmp_path, monkeypatch):
    """Keep the benchmark recorder's logs out of the repo's data/ during tests."""
    monkeypatch.setenv("ARC_BENCHMARK_DIR", str(tmp_path / "benchmark"))


@pytest.fixture(autouse=True)
def _no_substack(monkeypatch):
    """No test reaches the real Substack: a push without these is skipped. Tests that need them set their own."""
    for k in ("SUBSTACK_SID", "SUBSTACK_CONNECT_SID", "SUBSTACK_PUBLICATION_URL"):
        monkeypatch.delenv(k, raising=False)
