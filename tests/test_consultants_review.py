from datetime import date

from castelino.agents.consultants import review, store, thesis
from castelino.agents.consultants.models import MemoryNoteDraft, Part, Thesis, Watchlist
from castelino.agents.trade import llm
from castelino.agents.update.memory import Note
from castelino.agents.update.models import Finding

DAY = "2026-10-15"
WL = Watchlist(companies=[], series=[], queries=["q"])


def th(text="Funding is the squeeze.", version=1) -> Thesis:
    p = Part(text=text, fact_ids=[])
    return Thesis(
        happening=p, lean=p, alternative=p, change_mind=p, reason="r", updated=DAY, version=version
    )


def finding() -> Finding:
    return Finding(
        id="news-1",
        agent="news",
        claim="AirTrunk REIT listing was pulled.",
        provenance="reported",
        source_title="FT",
        source_url="u",
        fact_ids=["N1"],
    )


def setup(monkeypatch, p: dict[str, float]):
    c = store.create("AI", WL)
    with store.edit(c.slug) as x:
        x.created = "2026-10-01"  # before every week these tests review
    store.write_thesis(c.slug, th())
    asked = []

    def fake_predicates(text, questions, meter, *, agent, post=None):
        asked.append((text, questions, agent))
        return {k: p.get(k, 0.0) for k in questions}

    monkeypatch.setattr(review, "predicates", fake_predicates)
    return c, asked


def note(title: str, imp: int = 3, day: date = date(2026, 10, 12)) -> Note:
    return Note(title, f"{title} text", imp, day, "lesson")


def test_daily_updates_thesis_when_probability_passes(monkeypatch):
    c, asked = setup(monkeypatch, {"thesis": 0.81, "memory": 0.2})
    writes = []

    def fake_write(topic, facts, memory_md, old, today, meter, context=""):
        writes.append(context)
        return th("The squeeze moved to financing.", old.version + 1)

    monkeypatch.setattr(thesis, "write", fake_write)
    line = review.daily(c.slug, DAY, [finding()], llm.Meter())
    assert len(writes) == 1 and "AirTrunk" in writes[0]
    assert (line.verdict, line.p_thesis, line.p_memory) == ("updated", 0.81, 0.2)
    assert (
        line.before == "Funding is the squeeze." and line.after == "The squeeze moved to financing."
    )
    assert store.read_thesis(c.slug).version == 2
    assert store.read_memory(c.slug) == ([], [])
    assert set(asked[0][1]) == {"thesis", "memory"} and asked[0][2] == "consultant_decide"
    assert store.history(c.slug)[-1] == line


def test_daily_holds_below_threshold(monkeypatch):
    c, _ = setup(monkeypatch, {"thesis": 0.22, "memory": 0.1})
    monkeypatch.setattr(thesis, "write", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    line = review.daily(c.slug, DAY, [finding()], llm.Meter())
    assert line.verdict == "held" and store.read_thesis(c.slug).version == 1


def test_daily_memory_note_goes_to_short_term(monkeypatch):
    c, _ = setup(monkeypatch, {"thesis": 0.1, "memory": 0.7})
    monkeypatch.setattr(
        llm,
        "structured",
        lambda *a, **k: MemoryNoteDraft(title="Ramp lags", text="Ramp prints lag.", importance=3),
    )
    review.daily(c.slug, DAY, [finding()], llm.Meter())
    short, long = store.read_memory(c.slug)
    assert [n.title for n in short] == ["Ramp lags"] and long == []
    assert short[0].last_used == date(2026, 10, 15)


def test_daily_rewrite_failure_keeps_old_thesis(monkeypatch):
    c, _ = setup(monkeypatch, {"thesis": 0.9, "memory": 0.0})

    def bad(*a, **k):
        raise ValueError(["9% unsupported"])

    monkeypatch.setattr(thesis, "write", bad)
    line = review.daily(c.slug, DAY, [finding()], llm.Meter())
    assert line.verdict == "held" and "number check" in line.reason
    assert store.read_thesis(c.slug).version == 1


def test_daily_runs_once_per_day(monkeypatch):
    c, asked = setup(monkeypatch, {"thesis": 0.1})
    review.daily(c.slug, DAY, [], llm.Meter())
    assert review.daily(c.slug, DAY, [], llm.Meter()) is None
    assert len(asked) == 1


def test_weekly_moves_keeps_drops_and_clears(monkeypatch):
    c, asked = setup(
        monkeypatch,
        {"keep_s0": 0.9, "keep_s1": 0.2, "keep_s2": 0.6, "drop_l0": 0.8, "drop_l1": 0.1},
    )
    store.write_memory(c.slug, [note("s0"), note("s1"), note("s2")], [note("l0"), note("l1")])
    line = review.weekly(c.slug, date(2026, 10, 18), llm.Meter())
    short, long = store.read_memory(c.slug)
    assert short == [] and sorted(n.title for n in long) == ["l1", "s0", "s2"]
    assert sorted(line.moved) == ["s0", "s2"] and line.deleted == ["l0"]
    assert (line.kind, line.verdict, line.day) == ("weekly", "week", "2026-10-18")
    assert "s1" in line.reason
    assert "s0 text" in asked[0][1]["keep_s0"]


def test_weekly_caps_long_term_at_20(monkeypatch):
    c, _ = setup(monkeypatch, {f"keep_s{i}": 0.9 for i in range(3)})
    store.write_memory(
        c.slug, [note(f"s{i}", 5) for i in range(3)], [note(f"l{j}", 1) for j in range(20)]
    )
    review.weekly(c.slug, date(2026, 10, 18), llm.Meter())
    assert len(store.read_memory(c.slug)[1]) == 20


def test_weekly_once_per_week_and_not_before_created(monkeypatch):
    c, asked = setup(monkeypatch, {})
    with store.edit(c.slug) as x:
        x.created = "2026-10-10"
    assert review.weekly(c.slug, date(2026, 10, 4), llm.Meter()) is None
    assert review.weekly(c.slug, date(2026, 10, 11), llm.Meter()) is not None
    assert review.weekly(c.slug, date(2026, 10, 11), llm.Meter()) is None


def test_weekly_traces_notes_evicted_by_the_cap(monkeypatch):
    c, _ = setup(monkeypatch, {f"keep_s{i}": 0.9 for i in range(2)})
    longs = [note(f"l{j}", 5) for j in range(20)]
    store.write_memory(c.slug, [note("s0", 1), note("s1", 1)], longs)
    line = review.weekly(c.slug, date(2026, 10, 18), llm.Meter())
    kept = {n.title for n in store.read_memory(c.slug)[1]}
    assert len(kept) == 20
    gone = {"s0", "s1", *(f"l{j}" for j in range(20))} - kept
    assert gone <= set(line.deleted)  # nothing lost without a trace
    assert set(line.moved) <= kept


def test_last_sunday():
    assert review.last_sunday(date(2026, 10, 22)) == date(2026, 10, 18)
    assert review.last_sunday(date(2026, 10, 18)) == date(2026, 10, 18)
