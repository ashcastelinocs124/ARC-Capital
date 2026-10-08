from castelino.agents.update.guard import check_note, unsupported
from castelino.agents.update.models import Fact, Finding, MorningNote, NoteItem


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


def test_dangling_finding_and_foreign_chart_rejected():
    bad = [item(1, "x", ["macro-9"]), item(2, "y", ["macro-1"], chart="macro-2"), OK_ITEMS[2]]
    errs = check_note(note(bad), FINDS, FACTS)
    assert "item 1: unknown finding macro-9" in errs
    assert "item 2: chart macro-2 is not one of its findings" in errs


def test_shape_rules():
    assert "need exactly 3 takeaways" in check_note(note(OK_ITEMS, takeaways=("a",)), FINDS, FACTS)
    assert "need 3-5 items" in check_note(note(OK_ITEMS[:2]), FINDS, FACTS)


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


def test_duplicate_ranks_and_charts_rejected():
    dup = [
        item(1, "x", ["macro-1"], chart="macro-1"),
        item(1, "y", ["macro-1"], chart="macro-1"),
        OK_ITEMS[2],
    ]
    errs = check_note(note(dup), FINDS, FACTS)
    assert "duplicate rank 1" in errs and "finding macro-1 charted twice" in errs


def test_ai_findings_need_an_ai_item():
    ai = finding("ai-1", ["M1"]).model_copy(update={"agent": "ai"})
    errs = check_note(note(OK_ITEMS), [*FINDS, ai], FACTS)
    assert any("(ai) finding" in e for e in errs)
    with_ai = [*OK_ITEMS[:2], item(3, "A new model launched.", ["ai-1"])]
    assert check_note(note(with_ai), [*FINDS, ai], FACTS) == []
    assert check_note(note(OK_ITEMS), FINDS, FACTS) == []  # quiet AI day: no rule
