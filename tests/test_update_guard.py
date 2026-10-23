from castelino.agents.update.guard import (
    check_note,
    clean_picks,
    drop_views,
    unsupported,
    view_errors,
)
from castelino.agents.update.models import Fact, Finding, ItemView, MorningNote, NoteItem


def fact(fid, nums, text="t"):
    return Fact(
        id=fid, text=text, numbers=nums, provenance="data", source_title="s", source_url="u"
    )


def finding(fid, fact_ids):
    return Finding(
        id=fid,
        agent="macro",
        claim="c",
        provenance="data",
        source_title="s",
        source_url="u",
        fact_ids=fact_ids,
    )


def note(items, headline="Inflation firmer", takeaways=("a", "b", "c")):
    return MorningNote(
        headline=headline,
        takeaways=list(takeaways),
        items=items,
        themes_touched=[],
        new_themes=[],
    )


def item(rank, body, fids, chart=None):
    return NoteItem(rank=rank, title="T", body=body, finding_ids=fids, chart=chart)


FACTS = [fact("M1", [3.71, 3.54, 0.17]), fact("M2", [5.27, 3.0])]
FINDS = [finding("macro-1", ["M1"]), finding("macro-2", ["M2"])]
OK_ITEMS = [
    item(1, "CPI 3.71% vs 3.54%, +0.17pp.", ["macro-1"]),
    item(2, "10y at 5.27%, +3bp.", ["macro-2"], chart="macro-2"),
    item(3, "No numbers here.", ["macro-1"]),
    item(4, "Nor here.", ["macro-2"]),
    item(5, "Quiet.", ["macro-1"]),
]


def test_grounded_note_passes():
    assert check_note(note(OK_ITEMS), FINDS, FACTS) == []


def test_number_from_another_items_finding_is_rejected():
    bad = [item(1, "CPI 3.71% and 10y 5.27%.", ["macro-1"]), *OK_ITEMS[1:]]
    assert check_note(note(bad), FINDS, FACTS) == ["item 1: 5.27%"]


def test_headline_may_use_any_cited_fact():
    assert check_note(note(OK_ITEMS, headline="10y hits 5.27%"), FINDS, FACTS) == []
    assert check_note(note(OK_ITEMS, headline="10y hits 5.5%"), FINDS, FACTS) == [
        "headline/takeaways: 5.5%"
    ]


def test_dangling_finding_rejected_but_a_bad_chart_pick_is_not():
    # chart is only a fallback line chart: a bad pick is dropped later, never fails the note
    bad = [item(1, "x", ["macro-9"]), item(2, "y", ["macro-1"], chart="M2"), *OK_ITEMS[2:]]
    assert check_note(note(bad), FINDS, FACTS) == ["item 1: unknown finding macro-9"]


def test_clean_picks_drops_foreign_and_repeated_charts():
    picks = [
        item(1, "x", ["macro-1"], chart="M1"),  # a fact id, not a finding id (2026-10-22)
        item(2, "y", ["macro-2"], chart="macro-2"),
        item(3, "z", ["macro-2"], chart="macro-2"),  # charted twice: the first keeps it
        *OK_ITEMS[3:],
    ]
    out = clean_picks(note(picks), FINDS, FACTS)
    assert [it.chart for it in out.items[:3]] == [None, "macro-2", None]


def test_shape_rules():
    assert "need exactly 3 takeaways" in check_note(note(OK_ITEMS, takeaways=("a",)), FINDS, FACTS)
    assert "need exactly 5 items" in check_note(note(OK_ITEMS[:4]), FINDS, FACTS)


def test_unsupported_precision_sign_and_units():
    nums = {3.74, 17.0, 0.4}
    assert unsupported(["CPI 3.7%"], nums) == []  # 3.74 shown at 1dp
    assert unsupported(["CPI 3.70%"], nums) == ["3.70%"]  # 2dp must match 3.74
    assert unsupported(["+17 basis points"], nums) == []
    assert unsupported(["-0.4%"], nums) == ["-0.4%"]  # explicit sign must match
    assert unsupported(["day 10 of the strike"], nums) == []  # no unit, not checked


def test_common_unit_spellings_are_checked():
    assert unsupported(["yields up 9.9ppt", "a 25-basis-point cut", "up 7 pct"], set()) == [
        "9.9ppt",
        "25-basis-point",
        "7 pct",
    ]
    assert unsupported(["a 25-basis-point cut"], {25.0}) == []


def test_duplicate_ranks_rejected():
    dup = [
        item(1, "x", ["macro-1"], chart="macro-1"),
        item(1, "y", ["macro-1"], chart="macro-1"),
        *OK_ITEMS[2:],
    ]
    assert check_note(note(dup), FINDS, FACTS) == ["duplicate rank 1"]


def test_ai_findings_need_an_ai_item():
    ai = finding("ai-1", ["M1"]).model_copy(update={"agent": "ai"})
    errs = check_note(note(OK_ITEMS), [*FINDS, ai], FACTS)
    assert any("(ai) finding" in e for e in errs)
    with_ai = [*OK_ITEMS[:4], item(5, "A new model launched.", ["ai-1"])]
    assert check_note(note(with_ai), [*FINDS, ai], FACTS) == []
    assert check_note(note(OK_ITEMS), FINDS, FACTS) == []  # quiet AI day: no rule


# ── ARC view (topic consultants) ──
KF = [fact("K1-20261015-1", [41.2]), fact("K2-20261015-1", [6.3])]
CODES = {"ai": "K1", "india": "K2"}


def view_item(rank, text, consultant="ai", fids=("K1-20261015-1",)):
    it = item(rank, "Body.", ["macro-1"])
    return it.model_copy(
        update={"view": ItemView(consultant=consultant, text=text, fact_ids=list(fids))}
    )


def test_view_errors_unknown_slug_foreign_fact_and_invented_figure():
    items = [
        view_item(1, "Funding is the squeeze.", consultant="nope"),
        view_item(2, "Funding is the squeeze.", fids=("K2-20261015-1",)),
        view_item(3, "Revenue grew 9%, so the squeeze moves to financing."),
        view_item(4, "Revenue grew 41.2%; the squeeze moves to financing."),
        item(5, "Quiet.", ["macro-1"]),
    ]
    errs = view_errors(note(items), FACTS + KF, CODES, max_words=100, max_figures=2)
    assert set(errs) == {1, 2, 3}
    assert "nope" in errs[1][0] and "K2-20261015-1" in errs[2][0] and "9%" in errs[3][0]


def test_view_errors_too_long_and_too_many_figures():
    long_text = " ".join(["word"] * 101)
    figs = "Up 41.2%, then 41.2%, then 41.2% again."
    n = note([view_item(1, long_text), view_item(2, figs), *OK_ITEMS[2:]])
    assert set(view_errors(n, FACTS + KF, CODES, max_words=100, max_figures=2)) == {1, 2}


def test_drop_views_keeps_everything_else():
    n = note([view_item(1, "a"), view_item(2, "b"), *OK_ITEMS[2:]])
    out = drop_views(n, {1})
    assert out.items[0].view is None and out.items[1].view.text == "b"
    assert out.items[0].body == n.items[0].body and out.headline == n.headline
