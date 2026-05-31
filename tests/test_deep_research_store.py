from datetime import UTC, datetime

from castelino.agents.research.deep.models import ResearchSession, ResearchStatus
from castelino.agents.research.deep.store import ResearchStore


def _sess(id_="s1"):
    return ResearchSession(
        id=id_, original_query="q",
        created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
    )


def test_store_roundtrip(tmp_path):
    store = ResearchStore(root=tmp_path)
    sess = _sess()
    store.save(sess)
    loaded = store.load("s1")
    assert loaded.id == "s1"
    assert loaded.status == ResearchStatus.CREATED


def test_store_list_and_missing(tmp_path):
    store = ResearchStore(root=tmp_path)
    store.save(_sess("a"))
    store.save(_sess("b"))
    ids = {s.id for s in store.list()}
    assert ids == {"a", "b"}
    assert store.load("nope") is None
