import pytest


@pytest.fixture(autouse=True)
def _benchmark_dir(tmp_path, monkeypatch):
    """Keep the benchmark recorder's logs out of the repo's data/ during tests."""
    monkeypatch.setenv("ARC_BENCHMARK_DIR", str(tmp_path / "benchmark"))
