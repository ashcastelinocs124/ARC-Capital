import pytest


@pytest.fixture(autouse=True)
def _benchmark_dir(tmp_path, monkeypatch):
    """Keep the benchmark recorder's logs out of the repo's data/ during tests."""
    monkeypatch.setenv("ARC_BENCHMARK_DIR", str(tmp_path / "benchmark"))


@pytest.fixture(autouse=True)
def _consultants_dir(tmp_path, monkeypatch):
    """Topic consultants live in a temp dir: no test reads or writes data/consultants/."""
    monkeypatch.setenv("ARC_CONSULTANTS_DIR", str(tmp_path / "consultants"))


@pytest.fixture(autouse=True)
def _no_substack(monkeypatch):
    """No test reaches the real Substack: a push without these is skipped. Tests that need them set their own."""
    for k in ("SUBSTACK_SID", "SUBSTACK_CONNECT_SID", "SUBSTACK_PUBLICATION_URL"):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture(autouse=True)
def _no_visual_decisions(monkeypatch):
    """No test reaches OpenAI's Decisions API: a research point's visual defaults to a chart, as before
    diagrams. Tests of the pick (tests/test_research_diagrams.py) replace it themselves."""
    from castelino.agents.research.deep import visuals

    monkeypatch.setattr(visuals, "_picks_diagram", lambda p, meter: False)
