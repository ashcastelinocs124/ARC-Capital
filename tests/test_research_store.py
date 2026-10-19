import pytest

from castelino.agents.research.deep import store
from castelino.agents.research.deep.models import Clarification, ClarifyQuestion


@pytest.fixture(autouse=True)
def _dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_RESEARCH_DIR", str(tmp_path))


def _clar():
    return Clarification(
        question="How fast are US firms adopting AI?",
        questions=[ClarifyQuestion(question="US only?", why="scope")],
    )


def test_create_and_load_roundtrip():
    s = store.create("  AI adoption ", _clar(), cost=0.0123)
    got = store.load(s.id)
    assert got.topic == "AI adoption" and got.question.startswith("How fast")
    assert got.clarifying_questions[0].question == "US only?"
    assert got.status == "awaiting_answers" and got.cost_usd == 0.0123


def test_edit_saves_under_the_lock():
    s = store.create("AI adoption", _clar())
    with store.edit(s.id) as x:
        x.answers = {"US only?": "yes"}
    assert store.load(s.id).answers == {"US only?": "yes"}


def test_bad_or_unknown_ids_are_key_errors():
    for sid in ("../etc", "nope"):
        with pytest.raises(KeyError):
            store.load(sid)


def test_all_lists_newest_first_and_skips_unreadable(tmp_path):
    a = store.create("first", _clar())
    b = store.create("second", _clar())
    (tmp_path / "old-engine.json").write_text('{"id": "x", "original_query": "old"}')
    assert [s.id for s in store.all()] == [b.id, a.id]
