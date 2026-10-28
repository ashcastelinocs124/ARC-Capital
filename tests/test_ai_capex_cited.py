from castelino.dashboards.ai_capex import cited
from castelino.dashboards.ai_capex.cited import Item, Items

LINE1 = "Meta raised $30 billion of bonds at 4.9% due 2036 in April 2026."
LINE2 = "Meta expects 2026 capital expenditures of $115 billion to $135 billion."
TEXT = f"{LINE1}\n{LINE2}\nSome say the rate was 5.1%."  # the last line carries no citation


def search_stub(calls):
    def search(system, user):
        calls.append(user)
        cites = [
            ("Reuters", "https://reuters.com/meta-bonds", 0, 5),
            ("Meta IR", "https://investor.fb.com/q", len(LINE1) + 1, len(LINE1) + 6),
        ]
        return TEXT, cites

    return search


def reader_of(*items):
    class Reader:
        def __call__(self, **ctx):
            assert "[W1]" in ctx["lines"] and "5.1%" not in ctx["lines"]
            return Items(items=list(items))

    return Reader


def item(**kw):
    base = dict(label="10-yr bond", value=None, value_high=None, unit="percent", period="2026", date="2026-04", fact_id="W1")  # fmt: skip
    return Item(**(base | kw))


def test_value_must_be_in_its_line(tmp_path):
    reader = reader_of(item(value=4.9), item(label="made up", value=5.1))
    got = cited.cited_items("Meta", "META", "borrowing", "acc-1", tmp_path, search=search_stub([]), reader=reader)  # fmt: skip
    assert [(i["label"], i["value"]) for i in got] == [("10-yr bond", 4.9)]
    assert got[0]["source"] == {
        "title": "Reuters",
        "url": "https://reuters.com/meta-bonds",
        "line": LINE1,
    }


def test_range_both_ends_checked(tmp_path):
    reader = reader_of(
        item(label="guidance", value=115, value_high=135, unit="billions", fact_id="W2"),
        item(label="guidance bad", value=115, value_high=140, unit="billions", fact_id="W2"),
        item(label="dated event", value=None, unit="none", fact_id="W2"),
        item(label="unknown fact", value=None, unit="none", fact_id="W9"),
    )
    got = cited.cited_items("Meta", "META", "guidance", "acc-1", tmp_path, search=search_stub([]), reader=reader)  # fmt: skip
    assert [i["label"] for i in got] == ["guidance", "dated event"]


def test_cached_topic_not_searched_again(tmp_path):
    calls: list[str] = []
    reader = reader_of(item(value=4.9))
    for _ in range(2):
        cited.cited_items("Meta", "META", "borrowing", "acc-1", tmp_path, search=search_stub(calls), reader=reader)  # fmt: skip
    assert len(calls) == 1
    cited.cited_items("Meta", "META", "borrowing", "acc-2", tmp_path, search=search_stub(calls), reader=reader)  # fmt: skip
    assert len(calls) == 2  # a new filing is a new key
