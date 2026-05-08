import pytest

pytest.importorskip("chromadb")

from castelino.agents.personas.store import PersonaStore  # noqa: E402
from castelino.agents.personas.corpus import CorpusChunk  # noqa: E402


@pytest.fixture
def store():
    return PersonaStore(persona_id="test", in_memory=True)


def test_add_and_query_round_trip(store, monkeypatch):
    monkeypatch.setattr(
        store, "_embed",
        lambda texts: [[float(ord(t[0])), 0.0, 0.0] for t in texts],
    )
    chunks = [
        CorpusChunk(id="c1", text="apple", metadata={"source": "a"}),
        CorpusChunk(id="c2", text="banana", metadata={"source": "b"}),
        CorpusChunk(id="c3", text="cherry", metadata={"source": "c"}),
    ]
    store.add_chunks(chunks)

    hits = store.query("apple pie", top_k=2)
    assert len(hits) == 2
    assert hits[0].text == "apple"
    assert hits[0].metadata["source"] == "a"


def test_query_returns_empty_when_collection_empty():
    store = PersonaStore(persona_id="empty", in_memory=True)
    assert store.query("anything", top_k=3) == []


def test_collection_isolation_per_persona(monkeypatch):
    a = PersonaStore(persona_id="alpha", in_memory=True)
    b = PersonaStore(persona_id="beta", in_memory=True)
    fake = lambda self, texts: [[1.0, 0.0, 0.0] for _ in texts]
    monkeypatch.setattr(PersonaStore, "_embed", fake)

    a.add_chunks([CorpusChunk(id="x", text="alpha-doc", metadata={})])
    assert b.query("alpha-doc", top_k=1) == []
