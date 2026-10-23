from pathlib import Path

import pytest

from castelino import x_post, x_scout
from castelino.agents.consultants import post, review, store
from castelino.agents.consultants.models import Watchlist
from castelino.agents.trade import llm
from castelino.agents.update.models import Fact
from tests.test_consultants_review import DAY, finding, setup

WL = Watchlist(companies=[], series=["yahoo:SMH"], queries=["q"])


def fact(fid="K1-20261015-1", text="Digital Realty pulled a 4.1% stake sale.", nums=(4.1,)) -> Fact:
    return Fact(
        id=fid,
        text=text,
        numbers=list(nums),
        provenance="reported",
        source_title="FT",
        source_url="u",
    )


def draft(
    text="Builders are pulling listings while chip makers raise budgets.", ids=()
) -> post.PostDraft:
    return post.PostDraft(
        text=text,
        fact_ids=list(ids),
        form="compare",
        series=["yahoo:SMH", "yahoo:DLR"],
        names=["VanEck Semiconductor ETF", "Digital Realty"],
        window_days=180,
        threshold=None,
        chart_title="Chip makers climb while landlords stall",
    )


@pytest.fixture
def x(monkeypatch):
    """Fake X and chart: records what would go out; tickers always trade."""
    sent = {"posts": [], "charts": []}

    def fake_chart(pick, now, path, allowed=None, kicker=""):
        sent["charts"].append((pick.form, kicker))
        Path(path).write_bytes(b"png")
        return [], "", pick.form, []

    monkeypatch.setattr(x_scout, "chart", fake_chart)
    monkeypatch.setattr(x_scout, "trades", lambda t: True)
    monkeypatch.setattr(x_post, "can_post", lambda: True)
    monkeypatch.setattr(x_post, "upload_image", lambda data: "m1")
    monkeypatch.setattr(
        x_post, "post", lambda text, media_id=None: sent["posts"].append((text, media_id)) or "x1"
    )
    return sent


def drafts(monkeypatch, *ds):
    out = list(ds)
    monkeypatch.setattr(llm, "structured", lambda *a, **k: out.pop(0))


def consultant(knob=True):
    c = store.create("AI models and chips", WL)
    with store.edit(c.slug) as y:
        y.status, y.post_to_x = "active", knob
    return c


def test_errors_flag_untraced_numbers_links_length_and_unknown_ids():
    facts = {"K1-20261015-1": fact()}
    assert post.errors(draft("A 4.1% sale.", ["K1-20261015-1"]), facts, lambda t: True) == []
    assert post.errors(draft("A 37% sale.", ["K1-20261015-1"]), facts, lambda t: True)
    assert post.errors(draft("See ft.com for more."), facts, lambda t: True)
    assert post.errors(draft("x" * 281), facts, lambda t: True)
    assert post.errors(draft("Fine.", ["K9-1"]), facts, lambda t: True)
    assert post.errors(draft("Nvidia (NVDQ) fell."), facts, lambda t: False)


def test_run_retries_once_then_posts_with_its_chart(monkeypatch, x):
    c = consultant()
    drafts(
        monkeypatch,
        draft("Sales fell 37%.", ["K1-20261015-1"]),
        draft("A 4.1% stake sale.", ["K1-20261015-1"]),
    )
    text, form = post.run(c.slug, DAY, "ctx", [fact()], llm.Meter())
    assert (text, form) == ("A 4.1% stake sale.", "compare")
    assert x["posts"] == [("A 4.1% stake sale.", "m1")]
    assert x["charts"] == [("compare", "AI MODELS AND CHIPS")]
    assert store.day_log(c.slug, DAY).post_id == "x1"
    assert (store.cdir(c.slug) / "posts" / f"{DAY}.png").exists()


def test_run_gives_up_after_two_bad_drafts(monkeypatch, x):
    c = consultant()
    drafts(monkeypatch, draft("Up 37%."), draft("Up 38%."))
    with pytest.raises(ValueError):
        post.run(c.slug, DAY, "ctx", [fact()], llm.Meter())
    assert x["posts"] == [] and store.day_log(c.slug, DAY).post_id is None


def test_run_never_posts_without_a_chart(monkeypatch, x):
    c = consultant()
    drafts(monkeypatch, draft())

    def no_chart(*a, **k):
        raise RuntimeError("could not be drawn in any allowed form")

    monkeypatch.setattr(x_scout, "chart", no_chart)
    with pytest.raises(RuntimeError):
        post.run(c.slug, DAY, "ctx", [], llm.Meter())
    assert x["posts"] == []


def test_run_posts_once_a_day(monkeypatch, x):
    c = consultant()
    with store.edit_day(c.slug, DAY) as d:
        d.post_id = "x0"
    drafts(monkeypatch)  # any LLM call would pop from an empty list
    assert post.run(c.slug, DAY, "ctx", [], llm.Meter()) is None
    assert x["posts"] == []


def test_daily_asks_the_post_question_only_when_the_knob_is_on(monkeypatch):
    c, asked = setup(monkeypatch, {"thesis": 0.1, "post": 0.9})
    monkeypatch.setattr(post, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    line = review.daily(c.slug, DAY, [finding()], llm.Meter())
    assert set(asked[0][1]) == {"thesis", "memory"} and line.p_post is None and line.post is None


def test_daily_posts_a_notable_point_when_the_knob_is_on(monkeypatch):
    c, asked = setup(monkeypatch, {"thesis": 0.1, "post": 0.74})
    with store.edit(c.slug) as y:
        y.post_to_x = True
    calls = []

    def fake_run(slug, day, context_md, facts, meter):
        calls.append(context_md)
        return "Builders are pulling listings.", "compare"

    monkeypatch.setattr(post, "run", fake_run)
    line = review.daily(c.slug, DAY, [finding()], llm.Meter())
    assert (
        "post" in asked[0][1] and "AirTrunk" in calls[0] and "Funding is the squeeze." in calls[0]
    )
    assert (line.p_post, line.post, line.chart_form) == (
        0.74,
        "Builders are pulling listings.",
        "compare",
    )


def test_daily_logs_a_failed_post_and_still_finishes(monkeypatch):
    c, _ = setup(monkeypatch, {"thesis": 0.1, "post": 0.9})
    with store.edit(c.slug) as y:
        y.post_to_x = True

    def boom(*a, **k):
        raise RuntimeError("X said 403")

    monkeypatch.setattr(post, "run", boom)
    line = review.daily(c.slug, DAY, [finding()], llm.Meter())
    assert line.post is None and line.p_post == 0.9
    log = store.day_log(c.slug, DAY)
    assert log.reviewed and any("X post skipped" in n and "403" in n for n in log.notes)
