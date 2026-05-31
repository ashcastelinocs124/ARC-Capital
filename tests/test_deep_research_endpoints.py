import pytest
from fastapi.testclient import TestClient

import castelino.dashboard.endpoints.deep_research as dr
from castelino.agents.base import FakeLLMClient, set_llm_client
from castelino.agents.research.deep.models import (
    ClarificationQuestion,
    ClarifierResult,
)
from castelino.dashboard.main import app


@pytest.fixture(autouse=True)
def _reset(tmp_path, monkeypatch):
    # point the store at a temp dir so tests don't write into data/research
    monkeypatch.setattr(dr, "_store_root", tmp_path, raising=False)
    yield
    set_llm_client(None)


def test_start_returns_questions():
    llm = FakeLLMClient()
    llm.register("ClarifierResult", lambda s, u: ClarifierResult(
        reworded_query="Q?", clarifying_questions=[ClarificationQuestion(question="Scope?")]))
    set_llm_client(llm)
    client = TestClient(app)
    r = client.post("/research/start", json={"query": "will the fed cut"})
    assert r.status_code == 200
    body = r.json()
    assert body["reworded_query"] == "Q?"
    assert body["clarifying_questions"][0]["question"] == "Scope?"
    assert "session_id" in body


def test_get_unknown_session_404():
    client = TestClient(app)
    r = client.get("/research/does-not-exist")
    assert r.status_code == 404
