from datetime import date

from castelino.agents.weekly.board import Board
from castelino.agents.weekly.tools import ToolBox
from tests.weekly_fixtures import series

END = date(2026, 10, 9)


def box(board=None, allowed=("fred_series", "yahoo_prices", "web_search"), **kw):
    return ToolBox(
        agent=kw.pop("agent", "Rates desk"),
        prefix=kw.pop("prefix", "A"),
        allowed=list(allowed),
        board=board or Board(),
        end=END,
        max_calls=kw.pop("max_calls", 12),
        **kw,
    )


def test_fred_rate_series_becomes_fact_with_bp_changes():
    b = box(fred=lambda sid: series([4.10, 4.12, 4.15, 4.17, 4.30, 4.38]))
    out = b.call("fred_series", {"series_id": "DGS10", "start": "2026-07-01"})
    f = b.facts[0]
    assert f.id == "A1" and f.provenance == "data" and f.series.id == "DGS10"
    assert "+28bp" in f.text and 28 in f.numbers and 4.38 in f.numbers
    assert out.startswith("[A1]")


def test_yahoo_price_series_reports_percent_changes():
    b = box(yahoo=lambda t: series([100.0, 101.0, 102.0, 104.6]))
    b.call("yahoo_prices", {"ticker": "^SOX", "start": "2026-07-01"})
    f = b.facts[0]
    assert f.series.provider == "yahoo" and "+4.6%" in f.text and 4.6 in f.numbers


def test_series_with_one_point_in_window_is_a_tool_error():
    b = box(fred=lambda sid: series([4.38]))
    out = b.call("fred_series", {"series_id": "DGS10", "start": "2026-10-09"})
    assert out.startswith("Error:") and b.facts == []


def test_tool_not_granted_is_refused():
    b = box(allowed=("web_search",))
    out = b.call("fred_series", {"series_id": "DGS10", "start": "2026-07-01"})
    assert "not one of your tools" in out


def test_budget_caps_calls():
    b = box(max_calls=1, fred=lambda sid: series([1.0, 2.0]))
    b.call("fred_series", {"series_id": "DGS10", "start": "2026-07-01"})
    assert b.exhausted()
    assert "budget used up" in b.call("fred_series", {"series_id": "DGS2", "start": "2026-07-01"})


def test_web_search_lines_become_renumbered_facts():
    text = "- Brent fell 5.8% after OPEC+ [1]\n- uncited line"
    cites = [("Reuters", "https://reuters.com/x", 2, 30)]
    b = box(search=lambda system, user, model=None: (text, cites))
    b.call("web_search", {"query": "oil this week"})
    assert [f.id for f in b.facts] == ["A1"] and b.facts[0].provenance == "reported"


def test_board_shares_posted_facts_with_other_desks():
    board = Board()
    rates = box(board=board, fred=lambda sid: series([4.10, 4.38]))
    rates.call("fred_series", {"series_id": "DGS10", "start": "2026-07-01"})
    assert rates.call("post_to_board", {"note": "10y up 28bp", "fact_ids": ["A1"]}) == "Posted."
    chips = box(board=board, agent="AI & chips desk", prefix="B")
    out = chips.call("read_board", {})
    assert "Rates desk: 10y up 28bp" in out and "[A1]" in out
    assert [f.id for f in chips.facts] == ["A1"]  # borrowed fact is now citable


def test_cannot_post_facts_you_do_not_own():
    b = box()
    assert b.call("post_to_board", {"note": "x", "fact_ids": ["B1"]}).startswith("Error:")


def test_specs_expose_only_granted_tools_plus_board():
    names = [s["name"] for s in box(allowed=("bls_series",)).specs()]
    assert names == ["bls_series", "post_to_board", "read_board"]
