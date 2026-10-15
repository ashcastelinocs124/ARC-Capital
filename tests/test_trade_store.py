import threading

import pytest

from castelino.agents.trade import store


@pytest.fixture(autouse=True)
def _trade_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_TRADE_DIR", str(tmp_path / "trades"))


def test_create_load_roundtrip_and_list_newest_first():
    a = store.create("India is an AI hedge")
    b = store.create("Copper is the AI power trade")
    assert store.load(a.id).idea == "India is an AI hedge"
    assert [i.id for i in store.all()] == [b.id, a.id]
    assert store.charts_dir(a.id).is_dir()


def test_load_unknown_raises_keyerror():
    with pytest.raises(KeyError):
        store.load("nope")


def test_hide_moves_the_folder_out_of_the_list():
    a = store.create("x")
    store.hide(a.id)
    assert store.all() == []
    assert (store.root() / "hidden" / a.id / "idea.json").exists()


def test_edit_serializes_concurrent_writers():
    a = store.create("x")

    def add(n):
        for k in range(20):
            with store.edit(a.id) as idea:
                idea.fallbacks.append(f"{n}-{k}")

    threads = [threading.Thread(target=add, args=(n,)) for n in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(store.load(a.id).fallbacks) == 80  # no lost update
