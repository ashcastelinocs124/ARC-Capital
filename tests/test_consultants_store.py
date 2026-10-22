import multiprocessing as mp
import time
from datetime import date

import pytest

from castelino.agents.consultants import store
from castelino.agents.consultants.models import Company, HistoryLine, Watchlist
from castelino.agents.update.memory import Note
from castelino.agents.update.models import Fact

WL = Watchlist(
    companies=[Company(name="NVIDIA", ticker="NVDA")], series=["fred:DGS10"], queries=["AI chips"]
)


def fact(fid: str) -> Fact:
    return Fact(
        id=fid,
        text=f"text {fid}",
        numbers=[1.0],
        provenance="data",
        source_title="t",
        source_url="u",
    )


def test_create_assigns_slug_code_and_building_status():
    c = store.create("AI models and chips", WL)
    assert (c.slug, c.code, c.status) == ("ai-models-and-chips", "K1", "building")
    d = store.create("AI models and chips", WL)
    assert d.slug != c.slug and d.code == "K2"
    assert store.load(c.slug).topic == "AI models and chips"


def test_code_counts_hidden_consultants():
    c = store.create("India", WL)
    store.hide(c.slug)
    assert [x.slug for x in store.all()] == []
    assert store.create("India", WL).code == "K2"


def test_load_unknown_raises_key_error():
    with pytest.raises(KeyError):
        store.load("nope")


def test_facts_round_trip_and_by_id():
    c = store.create("AI", WL)
    store.write_facts(c.slug, "2026-10-15", [fact("K1-20261015-1")])
    store.write_facts(c.slug, "2026-10-16", [fact("K1-20261016-1")])
    assert [f.id for f in store.read_facts(c.slug, "2026-10-15")] == ["K1-20261015-1"]
    assert [f.id for f in store.facts_by_id(c.slug, ["K1-20261016-1", "K1-20990101-9"])] == [
        "K1-20261016-1"
    ]
    assert [f.id for f in store.recent_facts(c.slug, 1, date(2026, 10, 16))] == ["K1-20261016-1"]


def test_memory_round_trip():
    c = store.create("AI", WL)
    short = [Note("Ramp lags", "Ramp prints lag the news.", 3, date(2026, 10, 15), "lesson")]
    long = [Note("Funding squeeze", "Listings were pulled.", 4, date(2026, 10, 12), "lesson")]
    store.write_memory(c.slug, short, long)
    s, lg = store.read_memory(c.slug)
    assert [n.title for n in s] == ["Ramp lags"] and [n.title for n in lg] == ["Funding squeeze"]


def test_history_appends_in_order():
    c = store.create("AI", WL)
    a = HistoryLine(day="2026-10-14", kind="daily", verdict="held", p_thesis=0.22)
    b = HistoryLine(day="2026-10-15", kind="daily", verdict="updated", p_thesis=0.81)
    store.append_history(c.slug, a)
    store.append_history(c.slug, b)
    assert store.history(c.slug) == [a, b]


def test_active_excludes_paused():
    a = store.create("AI", WL)
    b = store.create("India", WL)
    with store.edit(b.slug) as x:
        x.status = "paused"
    assert [c.slug for c in store.active()] == [a.slug]


def test_day_log_edit_persists():
    c = store.create("AI", WL)
    with store.edit_day(c.slug, "2026-10-15") as d:
        d.cost_usd += 0.4
        d.built = True
    assert store.day_log(c.slug, "2026-10-15").built is True
    assert store.day_log(c.slug, "2026-10-16").built is False


def _hold(root: str, slug: str, ready, seconds: float) -> None:
    import os

    os.environ["ARC_CONSULTANTS_DIR"] = root
    with store.lock(slug):
        ready.set()
        time.sleep(seconds)


def test_lock_blocks_a_second_process_writer():
    c = store.create("AI", WL)
    ctx = mp.get_context("spawn")
    ready = ctx.Event()
    p = ctx.Process(target=_hold, args=(str(store.root()), c.slug, ready, 0.6))
    p.start()
    assert ready.wait(30)
    t = time.monotonic()
    with store.edit(c.slug) as x:
        x.topic = "AI models"
    waited = time.monotonic() - t
    p.join()
    assert waited >= 0.4
    assert store.load(c.slug).topic == "AI models"


def test_root_uses_env(tmp_path):
    assert store.root() == tmp_path / "consultants"
