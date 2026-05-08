from datetime import datetime, UTC
from castelino.agents.personas.corpus import CorpusDoc, chunk_docs


def test_chunk_respects_max_tokens():
    doc = CorpusDoc(
        source="b1.pdf", date=datetime.now(UTC),
        title="t", text="word " * 1000, url="u",
    )
    chunks = chunk_docs([doc], max_tokens=100, overlap=10)
    assert len(chunks) >= 10
    assert all(c.metadata["source"] == "b1.pdf" for c in chunks)


def test_chunk_overlap_creates_continuity():
    doc = CorpusDoc(
        source="x", date=datetime.now(UTC), title="t",
        text=" ".join(str(i) for i in range(200)), url="u",
    )
    chunks = chunk_docs([doc], max_tokens=50, overlap=10)
    assert any(tok in chunks[1].text.split()[:10]
               for tok in chunks[0].text.split()[-10:])


def test_chunk_id_is_deterministic():
    doc = CorpusDoc(source="x", date=datetime(2026, 1, 1, tzinfo=UTC),
                    title="t", text="hello world", url="u")
    a = chunk_docs([doc], max_tokens=50, overlap=5)
    b = chunk_docs([doc], max_tokens=50, overlap=5)
    assert [c.id for c in a] == [c.id for c in b]


def test_empty_doc_produces_no_chunks():
    doc = CorpusDoc(source="x", date=datetime.now(UTC), title="t",
                    text="", url="u")
    assert chunk_docs([doc], max_tokens=50, overlap=5) == []
