from datetime import date

from castelino.agents.research.deep import tools
from castelino.agents.research.deep.tools import ResearchToolBox, XBudget
from castelino.agents.weekly.board import Board
from castelino.agents.weekly.tools import ToolBox
from tests.research_fakes import fact, xfact


class XFake:
    def __init__(self):
        self.params: list[dict] = []

    def __call__(self, params):
        self.params.append(params)
        n = params["max_results"]
        return {
            "data": [
                {"id": str(i + 1), "author_id": "u1", "text": f"Enterprise usage up {40 + i}%"}
                for i in range(n)
            ],
            "includes": {"users": [{"id": "u1", "username": "sama"}]},
            "meta": {},
        }


def search_fake(seen):
    def fake(system, user, model=None):
        seen.append((system, user))
        line = "- AI use reached 9.2% of firms."
        return line, [("Census BTOS", "https://census.gov/btos", 5, 10)]

    return fake


def box(**kw):
    args = dict(
        agent="A · Adoption rate",
        prefix="A",
        allowed=["x_search", "web_search"],
        board=Board(),
        end=date(2026, 10, 19),
        max_calls=5,
        x_budget=XBudget(100),
        x_get=XFake(),
        x_per_call=10,
    )
    args.update(kw)
    return ResearchToolBox(**args)


def test_x_search_makes_attributed_reported_facts():
    b = box()
    out = b.call("x_search", {"query": "enterprise AI"})
    f = b.facts[0]
    assert out.startswith("[A1] @sama: ")
    assert (f.id, f.source_title, f.source_url) == (
        "A1",
        "@sama on X",
        "https://x.com/sama/status/1",
    )
    assert f.provenance == "reported" and 40.0 in f.numbers
    sent = b._x_get.params[0]
    assert sent["query"] == "enterprise AI -is:retweet" and sent["max_results"] == 10
    assert len(b.facts) == 10 and b.x_posts == 10


def test_x_budget_caps_posts_per_report():
    budget = XBudget(12)
    b = box(x_budget=budget)
    b.call("x_search", {"query": "a"})
    b.call("x_search", {"query": "b"})
    assert len(b.facts) == 12 and budget.left == 0
    assert b.call("x_search", {"query": "c"}) == "Error: X budget for this report is used up"


def test_x_search_only_with_a_token(monkeypatch):
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)
    assert "x_search" not in tools.allowed_tools()
    monkeypatch.setenv("X_BEARER_TOKEN", "t")
    assert "x_search" in tools.allowed_tools() and "web_search" in tools.allowed_tools()


def test_web_search_is_framed_for_any_topic():
    seen = []
    b = box(search=search_fake(seen))
    b.call("web_search", {"query": "AI use by US firms"})
    system, user = seen[0]
    assert system == tools.SEARCH_SYSTEM
    assert user == "Today is 2026-10-19. AI use by US firms"
    assert b.facts[0].id == "A1" and 9.2 in b.facts[0].numbers


def test_weekly_desks_keep_their_week_framing():
    seen = []
    w = ToolBox(
        agent="Rates",
        prefix="R",
        allowed=["web_search"],
        board=Board(),
        end=date(2026, 10, 16),
        max_calls=2,
        search=search_fake(seen),
    )
    w.call("web_search", {"query": "10-year yield"})
    assert seen[0][1] == "Week ending 2026-10-16. 10-year yield"


def test_new_ids_continue_after_the_highest_own_id():
    b = box()
    b.facts = [fact("A3", "x", [1.0]), fact("A12", "y", [2.0]), fact("B4", "z", [3.0])]
    b.call("x_search", {"query": "a"})
    assert b.facts[3].id == "A13"


def test_is_x_and_handle():
    f = xfact("G1", "erikbryn", "gains take years", [])
    assert tools.is_x(f) and tools.handle(f) == "erikbryn"
    assert not tools.is_x(fact("A1", "x", []))


def test_specs_offer_the_board_and_x():
    names = [s["name"] for s in box().specs()]
    assert names == ["x_search", "web_search", "post_to_board", "read_board"]
