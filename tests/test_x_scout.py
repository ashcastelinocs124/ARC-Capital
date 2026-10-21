import json
import os
from datetime import datetime

import pandas as pd
import pytest

from castelino import substack, x_post, x_scout
from castelino.agents.update.models import Fact
from castelino.agents.weekly.tools import series_fact
from castelino.x_scout import ET, ScoutPick, ScoutPost

AT = datetime(2026, 10, 16, 12, 15, tzinfo=ET)
GOOD = ScoutPost(
    lead="Chip stocks sit at 116.3 (start = 100).",
    posts=[
        "An unwind of the AI trade, not the market.",
        "Orders still outrun supply, so the selloff is about price, not demand.",
        "Watch the next earnings for whether margins hold.",
    ],
    source="Reuters",
)
FINE = ["Fine.", "Fine.", "Fine."]


def item(n=1, url="https://reuters.com/a"):
    return Fact(
        id=f"N{n}",
        text="AI: Two hyperscalers spread 2027 GPU orders over more quarters",
        numbers=[2027.0],
        provenance="reported",
        source_title="Reuters",
        source_url=url,
    )


def pick(post=True, item_id="N1", series=("yahoo:SMH", "yahoo:^GSPC")):
    return ScoutPick(
        post=post,
        item_id=item_id,
        topic="ai",
        headline="Chip stocks unwind on GPU order reports",
        form="compare",
        series=list(series),
        names=["Chip stocks (SMH)", "S&P 500"],
        window_days=180,
        threshold=None,
        chart_title="Chip stocks vs the S&P 500",
        reason="r",
    )


def fake(monkeypatch, *, items=None, pick_=None, posts=None, chart_ok=True):
    """Scan, Scout, chart and Writer replaced; returns the Writer's calls."""
    monkeypatch.setattr(x_scout, "scan", lambda now, hours=6: items or [item()])
    monkeypatch.setattr(x_scout.Scout, "__call__", lambda self, **k: pick_ or pick())

    def chart(p, now, png, allowed=None):
        if not chart_ok:
            raise RuntimeError("no such series")
        png.write_bytes(b"png")
        return [], "Chip stocks (SMH) leads, 116.3 (start = 100)", p.form, []

    monkeypatch.setattr(x_scout, "chart", chart)
    monkeypatch.setattr(x_scout, "context", lambda item: [])  # no follow-up search in tests
    outs, calls = list(posts or [GOOD]), []
    monkeypatch.setattr(
        x_scout.Writer,
        "__call__",
        lambda self, **k: calls.append(k) or (outs.pop(0) if len(outs) > 1 else outs[0]),
    )
    return calls


def test_check_allows_only_source_and_chart_numbers():
    nums = {116.3, 107.7, 2.1}
    src = "Reuters"
    assert (
        x_scout.check(
            "SMH is at 116.3 vs 107.7 in Q3 after 3 weeks.",
            ["Claims rose 2.1%.", "a", "b"],
            src,
            nums,
        )
        == []
    )
    bad = " ".join(x_scout.check("A $40bn order book, up 12% this year.", FINE, src, nums))
    assert "40" in bad and "12%" in bad
    assert any("280" in p for p in x_scout.check("x" * 300, FINE, src, nums))
    # the lead's room is 280 less the "Source: <name>" line code adds; a post's, less its "2/ "
    assert x_scout.check("x" * 263, ["y" * 277] * 3, src, nums) == []
    assert x_scout.check("x" * 264, FINE, src, nums) == [
        "the lead post with its source line is 281 characters; X allows 280"
    ]
    assert x_scout.check("Fine.", ["y" * 278, "Fine.", "Fine."], src, nums) == [
        "post 2 is 281 characters with its number; X allows 280"
    ]
    assert x_scout.check("Fine.", ["Fine."], src, nums) == ["write exactly 3 analysis posts, not 1"]


def test_check_refuses_links_and_domains_x_would_bill_as_a_link():
    nums = {7.4}
    assert x_scout.check("Rates hit 7.40 in the U.S. at 9 a.m.", FINE, "S&P Global", nums) == []
    for lead, posts, src in [
        ("Per Investing.com, rates rose.", FINE, "Investing"),
        ("Fine.", ["Fine.", "See https://nahb.org/x", "Fine."], "NAHB"),
        ("Fine.", FINE, "Investing.com"),
        ("Fine.", FINE, "www.reuters"),
        ("Fine.", FINE, ""),
    ]:
        assert x_scout.check(lead, posts, src, nums), (lead, posts, src)


def test_chart_numbers_give_the_writer_rebased_and_off_high_figures():
    s = pd.Series(
        [100.0, 120.0, 150.0, 135.0], index=pd.date_range("2026-07-01", periods=4, freq="W")
    )
    f = series_fact("S1", s, provider="yahoo", sid="SMH", title="t", url="u")
    text, nums = x_scout.chart_numbers([f], "SMH leads, 135.0 (start = 100)")
    assert {135.0, 150.0, 35.0, -10.0} <= nums  # last, high, change %, below the high
    assert "10.0% below its window high" in text


def test_chart_rejects_a_bad_series(tmp_path):
    with pytest.raises(ValueError):
        x_scout.chart(pick(series=["NVDA; rm"]), AT, tmp_path / "c.png")


def test_dry_run_records_without_posting(monkeypatch, tmp_path):
    fake(monkeypatch)
    monkeypatch.delenv("X_SCOUT_LIVE", raising=False)
    monkeypatch.setattr(x_post, "post", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    rec = x_scout.run(now=AT, root=tmp_path)
    assert rec["dry_run"] and rec["ids"] == [] and rec["chart"] == "2026-10-16/1215.png"
    assert rec["lead"].startswith("AI · Chip stocks") and rec["lead"].endswith(
        "\n\nSource: Reuters"
    )
    assert rec["thread"] == ["2/ " + GOOD.posts[0], "3/ " + GOOD.posts[1], "4/ " + GOOD.posts[2]]
    assert rec["source"] == "Reuters"  # no link on X: $0.200 a post
    saved = json.loads((tmp_path / "data/x_posts/scout/2026-10-16.json").read_text())
    assert saved["posts"][0]["source_url"] == "https://reuters.com/a"


def test_live_posts_the_lead_with_its_chart_then_the_thread(monkeypatch, tmp_path):
    fake(monkeypatch)
    monkeypatch.setenv("X_SCOUT_LIVE", "1")
    monkeypatch.setattr(x_post, "can_post", lambda: True)
    monkeypatch.setattr(x_post, "upload_image", lambda data: "m1")
    sent = []

    def post(text, reply_to=None, media_id=None):
        sent.append((text, reply_to, media_id))
        return f"id{len(sent)}"

    monkeypatch.setattr(x_post, "post", post)
    notes = []
    monkeypatch.setattr(substack, "can_note", lambda: True)
    monkeypatch.setattr(substack, "post_note", lambda text, png: notes.append((text, png)) or "n1")
    rec = x_scout.run(now=AT, root=tmp_path)
    lead, *rest = sent
    assert lead[1:] == (None, "m1") and lead[0].startswith("AI · ")
    assert lead[0].endswith("\n\nSource: Reuters") and not any("http" in t for t, _, _ in sent)
    assert rest == [  # each analysis post replies to the one before
        ("2/ " + GOOD.posts[0], "id1", None),
        ("3/ " + GOOD.posts[1], "id2", None),
        ("4/ " + GOOD.posts[2], "id3", None),
    ]
    assert rec["ids"] == ["id1", "id2", "id3", "id4"] and not rec["dry_run"]
    # the same finding as one Substack Note: lead, the analysis as paragraphs, the source's link
    text = lead[0].removesuffix("\n\nSource: Reuters")
    paras = "\n\n".join(GOOD.posts)
    assert notes == [
        (
            f"{text}\n\n{paras}\n\nSource: Reuters (https://reuters.com/a)",
            tmp_path / "data/x_posts/scout/2026-10-16/1215.png",
        )
    ]
    assert rec["note_id"] == "n1"


def test_a_failed_note_never_blocks_x(monkeypatch, tmp_path):
    fake(monkeypatch)
    monkeypatch.setenv("X_SCOUT_LIVE", "1")
    monkeypatch.setattr(x_post, "can_post", lambda: True)
    monkeypatch.setattr(x_post, "upload_image", lambda data: "m1")
    monkeypatch.setattr(x_post, "post", lambda text, **k: "x1")
    monkeypatch.setattr(substack, "can_note", lambda: True)

    def boom(text, png):
        raise RuntimeError("401 from Substack: session cookie expired")

    monkeypatch.setattr(substack, "post_note", boom)
    rec = x_scout.run(now=AT, root=tmp_path)
    assert rec["ids"] == ["x1"] * 4 and rec["note_id"] is None and "expired" in rec["note_error"]


def test_a_dry_run_never_touches_substack(monkeypatch, tmp_path):
    fake(monkeypatch)
    monkeypatch.delenv("X_SCOUT_LIVE", raising=False)
    monkeypatch.setattr(substack, "post_note", lambda *a: (_ for _ in ()).throw(AssertionError))
    assert x_scout.run(dry=True, now=AT, root=tmp_path)["note_id"] is None


def test_scout_saying_nothing_posts_nothing(monkeypatch, tmp_path):
    calls = fake(monkeypatch, pick_=pick(post=False, item_id=""))
    assert x_scout.run(now=AT, root=tmp_path) is None and calls == []


def test_nothing_over_the_bar_searches_a_day_and_must_pick(monkeypatch, tmp_path):
    fake(monkeypatch)
    scans, musts = [], []
    monkeypatch.setattr(x_scout, "scan", lambda now, hours=6: scans.append(hours) or [item()])

    def scout(self, **k):
        musts.append(k["must"])
        return pick() if k["must"] else pick(post=False, item_id="")

    monkeypatch.setattr(x_scout.Scout, "__call__", scout)
    rec = x_scout.run(dry=True, now=AT, root=tmp_path)
    assert rec and scans == [6, 24] and musts == [False, True]
    prompt = x_scout.Scout().user_prompt
    assert x_scout.MUST in prompt(now="n", items=[], posted=[], forms="- dial", must=True)
    assert x_scout.MUST not in prompt(now="n", items=[], posted=[], forms="- dial")


def test_no_chart_no_post(monkeypatch, tmp_path):
    calls = fake(monkeypatch, chart_ok=False)
    assert x_scout.run(now=AT, root=tmp_path) is None and calls == []


def test_an_invented_figure_gets_one_retry_then_no_post(monkeypatch, tmp_path):
    bad = ScoutPost(lead="Chips are down 12% this month.", posts=FINE, source="Reuters")
    calls = fake(monkeypatch, posts=[bad, GOOD])
    assert x_scout.run(dry=True, now=AT, root=tmp_path)["lead"].endswith(
        f"{GOOD.lead}\n\nSource: Reuters"
    )
    assert len(calls) == 2 and "12%" in " ".join(calls[1]["fix"])

    calls = fake(monkeypatch, posts=[bad])  # a draft and a retry on each of the two passes
    assert x_scout.run(dry=True, now=AT, root=tmp_path / "other") is None and len(calls) == 4


def test_a_daily_cap_and_never_the_same_source_twice(monkeypatch, tmp_path):
    fake(monkeypatch)
    monkeypatch.setattr(x_scout, "MAX_PER_DAY", 2)
    seen = []
    monkeypatch.setattr(
        x_scout.Scout, "__call__", lambda self, **k: seen.append(k["posted"]) or pick()
    )
    assert x_scout.run(dry=True, now=AT, root=tmp_path)
    assert x_scout.run(dry=True, now=AT, root=tmp_path) is None  # same Reuters story again
    assert seen[1][0]["headline"] == "Chip stocks unwind on GPU order reports"

    monkeypatch.setattr(x_scout, "scan", lambda now, hours=6: [item(url="https://ft.com/b")])
    assert x_scout.run(dry=True, now=AT, root=tmp_path)
    monkeypatch.setattr(x_scout, "scan", lambda now, hours=6: [item(url="https://wsj.com/c")])
    assert x_scout.run(dry=True, now=AT, root=tmp_path) is None  # the cap


def test_waits_an_hour_after_the_theme_charts_thread(monkeypatch, tmp_path):
    fake(monkeypatch)
    rec = tmp_path / "data/x_posts/themes/2026-10-16-am.json"  # rewritten after each thread post
    rec.parent.mkdir(parents=True)
    rec.write_text("{}")
    os.utime(rec, (AT.timestamp() - 30 * 60,) * 2)
    assert x_scout.run(dry=True, now=AT, root=tmp_path) is None
    os.utime(rec, (AT.timestamp() - 61 * 60,) * 2)
    assert x_scout.run(dry=True, now=AT, root=tmp_path)


def test_scout_sees_a_week_of_its_posts_and_todays_market_alerts(tmp_path):
    base = tmp_path / "data" / "x_posts"
    for sub, day, posts in [
        ("scout", "2026-10-10", [{"headline": "Fed minutes", "source_url": "u1"}]),
        ("scout", "2026-10-01", [{"headline": "Too old", "source_url": "u0"}]),
        ("moves", "2026-10-16", [{"text": "📉 Nasdaq 100 −3.4% today.\nAlso moving: Gold."}]),
    ]:
        (base / sub).mkdir(parents=True, exist_ok=True)
        (base / sub / f"{day}.json").write_text(json.dumps({"posts": posts}))
    seen = x_scout.recent(base, AT)
    assert [p["headline"] for p in seen] == ["Fed minutes", "📉 Nasdaq 100 −3.4% today."]


def test_forms_never_repeat_and_lines_stop_after_two_a_day():
    assert "line" in x_scout.allowed_forms([]) and "dial" in x_scout.allowed_forms([])
    assert "dial" not in x_scout.allowed_forms([{"form": "dial"}])  # never twice in a row
    two = x_scout.allowed_forms(
        [{}, {"form": "dial"}, {"form": "compare"}]
    )  # {} = before forms: a line
    assert "line" not in two and "compare" not in two and "dial" in two and "bars" in two


def test_a_post_records_its_form_for_the_next_runs_rules(monkeypatch, tmp_path):
    fake(monkeypatch, pick_=pick().model_copy(update={"form": "underwater"}))
    rec = x_scout.run(dry=True, now=AT, root=tmp_path)
    assert rec["form"] == "underwater"


def test_chart_numbers_carry_a_forms_own_figures():
    text, nums = x_scout.chart_numbers([], "", "dial", [("Brent crude (BZ=F) range_pos", 85.2)])
    assert text.startswith("Chart form: dial (") and "range_pos: 85.2" in text
    assert {85.2} <= nums and x_scout.check(
        "MACRO · Brent sits at 85.2% of its range.", FINE, "Reuters", nums
    ) == []
