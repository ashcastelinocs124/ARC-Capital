from datetime import date

from castelino.agents.update.memory import (
    MemoryStore,
    Note,
    parse_notes,
    rebalance,
    relevance,
    render_note,
)
from castelino.agents.update.models import MarketSnapshot
from tests.update_fixtures import make_snapshot, make_update

D = date(2026, 9, 30)


def note(title, imp, last=D):
    return Note(title=title, text=f"text {title}", importance=imp, last_used=last)


def test_render_parse_roundtrip():
    md = "## Notes\n" + render_note(note("A theme", 4))
    n = parse_notes(md)[0]
    assert (n.title, n.importance, n.last_used, n.text) == ("A theme", 4, D, "text A theme")


def test_parse_skips_malformed_and_handles_empty():
    assert parse_notes("") == []
    assert parse_notes("## Notes\n### broken header\nbody\n") == []


def test_rebalance_keeps_top_by_importance_then_recency():
    notes = [
        note("a", 5),
        note("b", 4),
        note("c", 3),
        note("d", 2),
        note("e", 1),
        note("f", 4, date(2026, 9, 1)),
    ]
    short, long = rebalance(notes, D, short_cap=3, long_cap=20)
    assert [n.title for n in short] == ["a", "b", "f"]
    assert {n.title for n in long} == {"c", "d", "e"}


def test_rebalance_evicts_lowest_relevance_over_long_cap():
    old = date(2026, 1, 1)  # 272 days = 9 thirty-day periods
    notes = [note("keep1", 5), note("keep2", 4), note("stale", 3, old), note("fresh", 2)]
    short, long = rebalance(notes, D, short_cap=1, long_cap=2)
    assert [n.title for n in short] == ["keep1"]
    assert {n.title for n in long} == {"keep2", "fresh"}  # "stale" evicted
    assert relevance(note("stale", 3, old), D) == 3 - 9


def test_apply_creates_both_files_with_tables(tmp_path):
    store = MemoryStore(tmp_path)
    store.apply(make_update(), make_snapshot(), D)
    short, long = store.read_short(), store.read_long()
    assert "## Short-term trend" in short and "XLE" in short and "Leading on oil supply." in short
    assert "## Long-term trend" in long and "bottoming, turning up" in long
    assert "Energy leadership" in short  # new theme lands in short-term
    assert "Inflation re-accelerating" in short  # unknown touched title becomes a note


def test_apply_updates_existing_theme_and_last_used(tmp_path):
    store = MemoryStore(tmp_path)
    store.apply(make_update(), make_snapshot(), date(2026, 9, 1))
    upd = make_update()
    upd.themes_touched[0].text = "Fifth hot print."
    store.apply(upd, make_snapshot(), D)
    n = {x.title: x for x in parse_notes(store.read_short())}["Inflation re-accelerating"]
    assert n.text == "Fifth hot print." and n.last_used == D


def test_long_table_only_rewritten_when_due(tmp_path):
    store = MemoryStore(tmp_path, refresh_days=7)
    store.apply(make_update(), make_snapshot(), date(2026, 9, 28))
    snap2 = make_snapshot()
    snap2.sectors[0].long_label = "CHANGED"
    store.apply(make_update(), snap2, date(2026, 9, 30))  # 2 days later: keep
    assert "CHANGED" not in store.read_long()
    store.apply(make_update(), snap2, date(2026, 10, 6))  # 8 days later: refresh
    assert "CHANGED" in store.read_long()


def test_apply_with_empty_snapshot_and_missing_files(tmp_path):
    store = MemoryStore(tmp_path)
    assert store.read_short() == "" and store.read_long() == ""
    store.apply(make_update(), MarketSnapshot(date="2026-09-30"), D)
    assert "no sector data" in store.read_short()


def test_caps_enforced_in_code(tmp_path):
    store = MemoryStore(tmp_path, short_cap=2, long_cap=1)
    upd = make_update()
    upd.themes_touched = []
    upd.new_themes = [
        type(upd.new_themes[0])(title=f"T{i}", text="x", importance=1 + i % 5) for i in range(6)
    ]
    store.apply(upd, make_snapshot(), D)
    assert len(parse_notes(store.read_short())) == 2
    assert len(parse_notes(store.read_long())) == 1
