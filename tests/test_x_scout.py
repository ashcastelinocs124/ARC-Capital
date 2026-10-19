import json
from datetime import datetime

import pandas as pd
import pytest

from castelino import x_post, x_scout
from castelino.agents.update.models import Fact
from castelino.agents.weekly.tools import series_fact
from castelino.x_scout import ET, ScoutPick, ScoutPost

AT = datetime(2026, 10, 16, 12, 15, tzinfo=ET)
GOOD = ScoutPost(
    lead="Chip stocks sit at 116.3 (start = 100).",
    reply="An unwind of the AI trade, not the market.",
)


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
        series=list(series),
        names=["Chip stocks (SMH)", "S&P 500"],
        window_days=180,
        chart_title="Chip stocks vs the S&P 500",
        reason="r",
    )


def fake(monkeypatch, *, items=None, pick_=None, posts=None, chart_ok=True):
    """Scan, Scout, chart and Writer replaced; returns the Writer's calls."""
    monkeypatch.setattr(x_scout, "scan", lambda now: items or [item()])
    monkeypatch.setattr(x_scout.Scout, "__call__", lambda self, **k: pick_ or pick())

    def chart(p, now, png):
        if not chart_ok:
            raise RuntimeError("no such series")
        png.write_bytes(b"png")
        return [], "Chip stocks (SMH) leads, 116.3 (start = 100)"

    monkeypatch.setattr(x_scout, "chart", chart)
    outs, calls = list(posts or [GOOD]), []
    monkeypatch.setattr(
        x_scout.Writer,
        "__call__",
        lambda self, **k: calls.append(k) or (outs.pop(0) if len(outs) > 1 else outs[0]),
    )
    return calls


def test_check_allows_only_source_and_chart_numbers():
    nums = {116.3, 107.7, 2.1}
    src = "Source: https://reuters.com/2026/10/16/a"
    assert (
        x_scout.check(
            "SMH is at 116.3 vs 107.7 in Q3 after 3 weeks.", "Claims rose 2.1%.", src, nums
        )
        == []
    )
    bad = " ".join(x_scout.check("A $40bn order book, up 12% this year.", "Fine.", src, nums))
    assert "40" in bad and "12%" in bad
    assert any("280" in p for p in x_scout.check("x" * 300, "Fine.", src, nums))
    # the reply's room is 280 less the source line code adds (a link counts 23)
    assert x_scout.check("Fine.", "y" * 247, src, nums) == []
    assert x_scout.check("Fine.", "y" * 248, src, nums) == [
        "the reply is 248 characters; it must be at most 247"
    ]


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
    assert rec["lead"].startswith("🤖 AI · Chip stocks")
    assert rec["reply"].endswith("\n\nSource: https://reuters.com/a")
    saved = json.loads((tmp_path / "data/x_posts/scout/2026-10-16.json").read_text())
    assert saved["posts"][0]["source_url"] == "https://reuters.com/a"


def test_live_posts_the_lead_with_its_chart_then_the_reply(monkeypatch, tmp_path):
    fake(monkeypatch)
    monkeypatch.setenv("X_SCOUT_LIVE", "1")
    monkeypatch.setattr(x_post, "can_post", lambda: True)
    monkeypatch.setattr(x_post, "upload_image", lambda data: "m1")
    sent = []

    def post(text, reply_to=None, media_id=None):
        sent.append((text, reply_to, media_id))
        return f"id{len(sent)}"

    monkeypatch.setattr(x_post, "post", post)
    rec = x_scout.run(now=AT, root=tmp_path)
    lead, reply = sent
    assert lead[1:] == (None, "m1") and lead[0].startswith("🤖 AI · ")
    assert reply[1] == "id1" and reply[0].endswith("https://reuters.com/a")
    assert rec["ids"] == ["id1", "id2"] and not rec["dry_run"]


def test_scout_saying_nothing_posts_nothing(monkeypatch, tmp_path):
    calls = fake(monkeypatch, pick_=pick(post=False, item_id=""))
    assert x_scout.run(now=AT, root=tmp_path) is None and calls == []


def test_no_chart_no_post(monkeypatch, tmp_path):
    calls = fake(monkeypatch, chart_ok=False)
    assert x_scout.run(now=AT, root=tmp_path) is None and calls == []


def test_an_invented_figure_gets_one_retry_then_no_post(monkeypatch, tmp_path):
    bad = ScoutPost(lead="Chips are down 12% this month.", reply="Fine.")
    calls = fake(monkeypatch, posts=[bad, GOOD])
    assert x_scout.run(dry=True, now=AT, root=tmp_path)["lead"].endswith(GOOD.lead)
    assert len(calls) == 2 and "12%" in " ".join(calls[1]["fix"])

    calls = fake(monkeypatch, posts=[bad])
    assert x_scout.run(dry=True, now=AT, root=tmp_path / "other") is None and len(calls) == 2


def test_two_a_day_and_never_the_same_source_twice(monkeypatch, tmp_path):
    fake(monkeypatch)
    seen = []
    monkeypatch.setattr(
        x_scout.Scout, "__call__", lambda self, **k: seen.append(k["posted"]) or pick()
    )
    assert x_scout.run(dry=True, now=AT, root=tmp_path)
    assert x_scout.run(dry=True, now=AT, root=tmp_path) is None  # same Reuters story again
    assert seen[1][0]["headline"] == "Chip stocks unwind on GPU order reports"

    monkeypatch.setattr(x_scout, "scan", lambda now: [item(url="https://ft.com/b")])
    assert x_scout.run(dry=True, now=AT, root=tmp_path)
    monkeypatch.setattr(x_scout, "scan", lambda now: [item(url="https://wsj.com/c")])
    assert x_scout.run(dry=True, now=AT, root=tmp_path) is None  # 2 a day


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
