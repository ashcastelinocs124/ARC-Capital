import json
from datetime import datetime

import pandas as pd
import pytest

from castelino import cover
from castelino.agents import themes
from castelino.agents.update.models import Fact, SeriesRef
from castelino.agents.weekly.models import BarPoint
from castelino.agents.weekly.tools import series_fact

NOW = datetime(2026, 10, 14, 8, 0, tzinfo=themes.ET)
FACTS = [
    Fact(
        id="N1",
        text="Oil tops $93 as Gulf supply talks stall",
        numbers=[93.0],
        provenance="reported",
        source_title="Reuters",
        source_url="https://reuters.com/x",
    ),
    Fact(
        id="M1",
        text="BRENT (commodities): 1d +1.20%, 1w +4.10%, 1m +11.80%",
        numbers=[1.2, 4.1, 11.8],
        provenance="data",
        series=SeriesRef(kind="daily", provider="yahoo", id="BZ=F", label="BRENT"),
        source_title="Yahoo Finance BZ=F",
        source_url="https://finance.yahoo.com/quote/BZ=F",
    ),
    Fact(
        id="M2",
        text="SPY (equities): 1d -0.40%, 1w -1.10%",
        numbers=[-0.4, -1.1],
        provenance="data",
        series=SeriesRef(kind="daily", provider="yahoo", id="SPY", label="SPY"),
        source_title="Yahoo Finance SPY",
        source_url="https://finance.yahoo.com/quote/SPY",
    ),
]


def _series(_id: str) -> pd.Series:
    idx = pd.bdate_range(end="2026-10-13", periods=800)
    return pd.Series([80 + i * 0.01 + (i % 7) * 0.3 for i in range(800)], index=idx)


def chart(kind, title, fact_ids, window_days=90, points=(), unit="", names=()):
    return themes.ThemeChart(kind=kind, title=title, fact_ids=fact_ids, window_days=window_days,
                             points=list(points), unit=unit, names=list(names))  # fmt: skip


def fetch(provider, sid, fid, start):
    if sid == "NOPE":
        raise ValueError("no such ticker")
    s = _series(sid)
    return series_fact(fid, s[s.index >= pd.Timestamp(start.date())], provider=provider, sid=sid,
                       title=f"FRED {sid}", url="https://fred.stlouisfed.org")  # fmt: skip


def pick(why="Brent rose 4.1% on the week.", charts=None, same=False):
    line = chart("line", "Brent", ["M1"])
    compare = chart("compare", "Breakevens", ["fred:T5YIE", "yahoo:NOPE"])
    movers = chart("movers", "Who moved", [], 7, unit="%",
                   points=[BarPoint(fact_id="M1", label="Brent", value=4.1),
                           BarPoint(fact_id="M2", label="S&P 500", value=-1.1)])  # fmt: skip
    return themes.ThemePick(
        theme="Oil's run revives the inflation scare",
        why=why,
        lead="coverage",
        signals=[
            themes.Signal(kind="coverage", headline="Most-discussed theme", note="oil, Fed path"),
            themes.Signal(kind="move", headline="Brent +4.1% w/w", note="energy leads"),
            themes.Signal(kind="odds", headline="No Polymarket read", note="nothing moved"),
        ],
        same_as_last=same,
        fact_ids=["N1", "M1"],
        charts=[line, compare, movers] if charts is None else charts,
    )


@pytest.fixture(autouse=True)
def _offline(tmp_path, monkeypatch):
    from castelino.forecast import regime

    monkeypatch.setattr(themes, "_dir", lambda: tmp_path)
    monkeypatch.setattr(regime, "_fetch_yf_close", _series)
    monkeypatch.setattr(regime, "_fetch_fred_series", _series)


def test_run_draws_charts_drops_bad_ticker_and_saves(tmp_path):
    rec = themes.run(NOW, gather_fn=lambda now: FACTS, fetch=fetch, picker=lambda **kw: pick())
    assert rec.run_id == "2026-10-14-am" and rec.streak == 1
    # the compare lost yahoo:NOPE, leaving one series, so the guard dropped it
    assert [e.kind for e in rec.exhibits] == ["line", "movers"]
    assert all((tmp_path / "charts" / rec.run_id / e.file).is_file() for e in rec.exhibits)
    assert {f.id for f in rec.facts} == {"N1", "M1", "M2"}
    assert json.loads((tmp_path / f"{rec.run_id}.json").read_text())["theme"] == rec.theme


def test_unsupported_figure_retries_and_memory_counts_the_streak(tmp_path):
    (tmp_path / "2026-10-13-pm.json").write_text(
        json.dumps(
            {
                "run_id": "2026-10-13-pm",
                "date": "2026-10-13",
                "slot": "pm",
                "theme": "Oil shock reaches the pump",
                "streak": 2,
            }
        )  # fmt: skip
    )
    calls = []

    def picker(**kw):
        calls.append(kw)
        return pick(why="Brent rose 9.9% on the week.") if len(calls) == 1 else pick(same=True)

    rec = themes.run(NOW, gather_fn=lambda now: FACTS, fetch=fetch, picker=picker)
    assert calls[0]["recent"] == ["2026-10-13 pm: Oil shock reaches the pump"]
    assert any("9.9%" in e for e in calls[1]["fix"])
    assert rec.streak == 3
    prompt = themes.ThemePicker().user_prompt(**calls[1])
    assert "Oil shock reaches the pump" in prompt and "9.9%" in prompt


def test_a_saved_run_prunes_last_weeks_same_day_and_older_but_keeps_post_records(tmp_path):
    for run_id in ("2026-10-06-am", "2026-10-07-am", "2026-10-07-pm", "2026-10-08-am"):
        rec = {"run_id": run_id, "date": run_id[:10], "slot": run_id[-2:], "theme": "Oil"}
        (tmp_path / f"{run_id}.json").write_text(json.dumps(rec))
        (tmp_path / "charts" / run_id).mkdir(parents=True)
        (tmp_path / "charts" / run_id / "exhibit_1.png").write_bytes(b"png")
    (tmp_path / "substack").mkdir()
    (tmp_path / "substack" / "2026-10-07-am.json").write_text('{"url": "u"}')
    (tmp_path / "covers").mkdir()
    for run_id in ("2026-10-07-am", "2026-10-08-am"):
        (tmp_path / "covers" / f"{run_id}.png").write_bytes(b"png")
    themes.run(NOW, gather_fn=lambda now: FACTS, fetch=fetch, picker=lambda **kw: pick())  # Wed 14
    left = sorted(p.stem for p in tmp_path.glob("*.json"))
    assert left == ["2026-10-08-am", "2026-10-14-am"]  # last Wednesday's (and older) went
    assert sorted(p.name for p in (tmp_path / "charts").iterdir()) == left
    assert [p.stem for p in (tmp_path / "covers").iterdir()] == ["2026-10-08-am"]
    assert themes.post_url("2026-10-07-am") == "u"  # the never-post-twice record stays


def test_no_drawable_chart_saves_nothing(tmp_path):
    bad = [chart("line", "?", ["yahoo:NOPE"])]
    with pytest.raises(RuntimeError):
        themes.run(
            NOW, gather_fn=lambda now: FACTS, fetch=fetch, picker=lambda **kw: pick(charts=bad)
        )
    assert not list(tmp_path.glob("*.json"))


def test_heatmap_together_and_range_draw_from_series_and_take_reader_names(tmp_path):
    charts = [
        chart("heatmap", "Where oil reaches", ["M1", "M2", "fred:DGS10"], 0,
              names=["Brent", "S&P 500", "10y yield"]),
        chart("together", "Oil against stocks", ["M1", "M2"], 730, names=["Brent", "S&P 500"]),
        chart("range", "How stretched", ["M1", "fred:DGS10"], 0),
        chart("range", "Odds can't range", ["M1", "N1"], 0),  # N1 has no series: dropped
    ]  # fmt: skip
    rec = themes.run(
        NOW, gather_fn=lambda now: FACTS, fetch=fetch, picker=lambda **kw: pick(charts=charts)
    )
    assert [e.kind for e in rec.exhibits] == ["heatmap", "together", "range"]
    assert rec.exhibits[0].subtitle.startswith("Most unusual: ")
    assert "of the last 13 weeks · last 2 years" in rec.exhibits[1].subtitle
    assert "% of its 1-year range" in rec.exhibits[2].subtitle
    assert all((tmp_path / "charts" / rec.run_id / e.file).is_file() for e in rec.exhibits)
    # the browser data carries the same numbers: heatmap cells, weekly same-way shares, 1y ranges
    heat, sc, rng = (e.data for e in rec.exhibits)
    assert [r["name"].split(" · ")[0] for r in heat["rows"]] == ["Brent", "S&P 500", "10y yield"]
    assert all(len(r["cells"]) == 4 for r in heat["rows"]) and heat["rows"][2]["rate"]
    assert sc["names"] == ["Brent", "S&P 500"] and sc["window"] == 730 and len(sc["points"]) > 90
    assert all(r["lo"] <= r["last"] <= r["hi"] for r in rng["rows"])


def test_together_is_the_share_of_the_last_13_weeks_moving_the_same_way():
    from castelino.agents import theme_charts

    idx = pd.bdate_range(end="2026-10-13", periods=400)
    up = pd.Series([100.0 + i + (i % 3) for i in range(400)], index=idx)
    data = {"A": up, "B": up * 2, "C": 1000 - up}  # B moves with A, C against it

    def fact(sid):
        return Fact(id=sid, text=sid, numbers=[], provenance="data", source_title=sid,
                    source_url="", series=SeriesRef(kind="daily", provider="yahoo", id=sid, label=sid))  # fmt: skip

    def series(ref, days):
        s = data[ref.id]
        return s[s.index >= s.index[-1] - pd.Timedelta(days=days)]

    same = theme_charts.together_share([fact("A"), fact("B")], series, 180)
    apart = theme_charts.together_share([fact("A"), fact("C")], series, 180)
    assert (same == 100).all() and (apart == 0).all() and len(same) >= 25
    assert (
        theme_charts._zone(61.5) == theme_charts.GREEN
        and theme_charts._zone(46) == theme_charts.SLATE
    )
    assert theme_charts._zone(38.5) == theme_charts.RED
    short = chart("together", "Too short", ["M1", "M2"], 90)
    assert theme_charts.form_errors(short, {f.id: f for f in FACTS})  # under 180 days


def test_fewer_than_five_charts_retries_then_publishes_what_passed():
    calls = []

    def picker(**kw):
        calls.append(kw)
        return pick()  # 3 charts, 2 drawable (the compare loses yahoo:NOPE)

    rec = themes.run(NOW, gather_fn=lambda now: FACTS, fetch=fetch, picker=picker)
    assert len(calls) == 2
    assert "only 2 of your charts can be drawn; give at least 5" in calls[1]["fix"]
    assert any("compare" in e or "Breakevens" in e for e in calls[1]["fix"])  # told why it dropped
    line, movers = (e.data for e in rec.exhibits)
    assert line["dated"] and line["window"] == 90 and len(line["series"][0]["points"]) > 250
    assert line["series"][0]["name"] == "Brent"
    assert [b["value"] for b in movers["bars"]] == [4.1, -1.1] and movers["unit"] == "%"


def test_morning_run_posts_a_thread_once_and_resumes_a_broken_chain(tmp_path):
    rec = themes.run(NOW, gather_fn=lambda now: FACTS, fetch=fetch, picker=lambda **kw: pick())
    assert len(rec.exhibits) == 2
    sent, uploads, fail = [], [], {"at": 2}

    def post(text, reply_to=None, media_id=None):
        if len(sent) == fail["at"]:
            raise RuntimeError("X said 503")
        sent.append((text, reply_to, media_id))
        return f"id{len(sent)}"

    def upload(data):
        uploads.append(data[:4])
        return f"m{len(uploads)}"

    calls = []

    def explainer(**kw):
        calls.append(kw)
        return themes.ChartLines(
            lines=[themes.ChartLine(n=2, heading="Oil leads", sentence="Brent is doing the work.")]
        )

    with pytest.raises(RuntimeError):  # the link post fails: two posts out, saved
        themes.post_today(NOW, tmp_path, post=post, upload=upload, explainer=explainer)
    fail["at"] = None
    ids = themes.post_today(  # resumes with the link, the saved texts and no second model call
        NOW, tmp_path, post=post, upload=upload, explainer=explainer
    )
    assert len(calls) == 1
    assert ids == ["id1", "id2", "id3"] and uploads == [b"\x89PNG"] * 2
    (t1, r1, m1), (t2, r2, m2), (t3, r3, m3) = sent
    assert (
        t1
        == "Before the open: Oil's run revives the inflation scare\n\nBrent rose 4.1% on the week."
    )
    assert t2.startswith("2/ ") and (r1, m1, r2, m2) == (None, "m1", "id1", "m2")
    assert t2.endswith("\n→ Oil leads. Brent is doing the work.")
    assert t3 == "All 2 charts with sources → https://arcresearch.markets/themes"  # no post yet
    assert (r3, m3) == ("id2", None)
    assert themes.post_today(NOW, tmp_path, post=post, upload=upload, explainer=explainer) == ids
    assert len(sent) == 3
    assert themes.post_today(NOW.replace(day=17), tmp_path, post=post, upload=upload) is None  # Sat


def say(*lines):
    return lambda **kw: themes.ChartLines(lines=list(lines))


def test_reads_may_quote_the_charts_own_levels_and_nothing_else_and_never_block():
    rec = themes.run(NOW, gather_fn=lambda now: FACTS, fetch=fetch, picker=lambda **kw: pick())
    line = themes.ChartLine
    last = rec.exhibits[0].data["series"][0]["points"][-1][1]  # what code drew on chart 1
    assert f"Brent: last {themes._num(last)}" in themes.key_numbers(rec.exhibits[0])[0]
    got = themes.explain(rec, say(
        line(n=1, heading="Level to watch", sentence=f"Brent sits at {last:.1f} into the open."),
        line(n=2, heading="Oil leads", sentence="Brent's 4.1% week tops the S&P 500's slip."),
        line(n=2, heading="Made up", sentence="Brent is 3.2% off its high."),  # computed: dropped
    ))  # fmt: skip
    assert got == {
        1: f"→ Level to watch. Brent sits at {last:.1f} into the open.",
        2: "→ Oil leads. Brent's 4.1% week tops the S&P 500's slip.",  # a fact's number; an index
    }
    assert themes.thread(rec, lines=got)[0].startswith(  # chart 1's read sits under the header
        f"Before the open: {rec.theme}\n\n→ Level to watch."
    )

    def boom(**kw):
        raise RuntimeError("OpenAI 500")

    assert themes.explain(rec, boom) == {}  # the thread posts as before
    assert themes.thread(rec, lines={}) == themes.thread(rec)
    long = {1: "→ Long. " + "word " * 60, 2: "→ Long. " + "word " * 60}
    assert themes.thread(rec, lines=long) == themes.thread(rec)  # past 280: dropped, not cut


def test_untraced_checks_every_number_but_names_tenors_and_calendar_times():
    nums, times = {5.19, 86.5, 0.3}, {(8, 30)}
    ok = "The 10-year at 5.2% and 86.5% odds; the S&P 500 waits on CPI at 8:30, consensus 0.3%."
    assert themes._untraced(ok, nums, times) == []
    bad = "Oil at 157 by 9:15, odds -86.5"  # a level, a time and a sign none of them has
    assert themes._untraced(bad, nums, times) == ["9:15", "157", "-86.5"]


def test_commentary_keeps_traced_reads_drops_the_rest_and_never_blocks_the_post():
    rec = themes.run(NOW, gather_fn=lambda now: FACTS, fetch=fetch, picker=lambda **kw: pick())
    line = themes.ChartLine
    got = themes.commentary(rec, say(
        line(n=1, heading="Supply talks", sentence="Brent rose 4.1% on the week as talks stalled."),
        line(n=2, heading="Breakevens", sentence="They jumped 9.9% in a day."),  # traced to nothing
        line(n=9, heading="Nine", sentence="There is no chart nine."),
        line(n=2, heading="Long", sentence="Word " * 60),  # over 280 characters
    ))  # fmt: skip
    assert got == {1: ("Supply talks", "Brent rose 4.1% on the week as talks stalled.")}

    def boom(**kw):
        raise RuntimeError("OpenAI 500")

    assert themes.commentary(rec, boom) == {}  # the post publishes as before
    up = {e.file: {"url": f"https://cdn/{e.file}"} for e in rec.exhibits}
    assert themes.substack_doc(rec, up, {}) == themes.substack_doc(rec, up)


def test_todays_calendar_feeds_the_picker_and_is_listed_by_code(tmp_path):
    ev = {"date": "2026-10-14", "kind": "other", "country": "US", "unit": "%", "actual": None}
    week = {"events": [
        {**ev, "time_et": "08:30", "name": "Retail Sales", "measure": "m/m", "consensus": 0.4,
         "previous": 0.6},
        {**ev, "time_et": "10:00", "kind": "other", "country": "DE", "name": "Ifo"},  # not US
        {**ev, "time_et": "07:00", "name": "MBA Mortgage Applications"},  # out before 08:00
        {"date": "2026-10-14", "kind": "earnings", "company": "JPMorgan Chase", "ticker": "JPM",
         "market_cap": 7e11, "session": "pre", "eps_est": 4.9, "eps_year_ago": 4.4},
        {**ev, "date": "2026-10-15", "time_et": "08:30", "name": "CPI", "consensus": 0.3},
        {"date": "2026-10-14", "kind": "earnings", "company": "Apple", "ticker": "AAPL",
         "market_cap": 3e12, "session": "post", "eps_est": 1.6, "eps_year_ago": 1.4},
    ]}  # fmt: skip
    path = tmp_path / "week_ahead.json"
    path.write_text(json.dumps(week))
    cal = themes.catalysts(NOW, path)
    assert [f.text for f in cal] == [  # in the day's order
        "08:30 ET US Retail Sales m/m · consensus 0.4%, previous 0.6%",
        "JPMorgan Chase (JPM) reports before the open · EPS estimate 4.9, a year ago 4.4",
        "Apple (AAPL) reports after the close · EPS estimate 1.6, a year ago 1.4",
    ]
    assert [f.id for f in cal] == ["C1", "C2", "C3"] and cal[0].numbers == [0.4, 0.6]
    assert themes.catalysts(NOW, tmp_path / "missing.json") == []

    seen = []
    rec = themes.run(NOW, gather_fn=lambda now: FACTS + cal, fetch=fetch,
                     picker=lambda **kw: seen.append(kw) or pick())  # fmt: skip
    assert rec.calendar == cal and "[C1] 08:30 ET" in themes.ThemePicker().user_prompt(**seen[0])
    assert "Today's calendar:\n- 08:30 ET US Retail Sales" in themes._brief(rec)
    read = themes.ChartLine(n=1, heading="Watch 8:30", sentence="Retail sales, consensus 0.4%.")
    assert themes.explain(rec, say(read)) == {1: "→ Watch 8:30. Retail sales, consensus 0.4%."}
    assert themes.thread(rec)[-1] == (
        "On today's calendar: 08:30 ET US Retail Sales m/m · JPMorgan Chase (JPM) reports before"
        " the open · Apple (AAPL) reports after the close"
        "\n\nAll 2 charts with sources → https://arcresearch.markets/themes"
    )
    up = {e.file: {"url": f"https://cdn/{e.file}"} for e in rec.exhibits}
    content = themes.substack_doc(rec, up)["content"]
    i = next(
        i for i, c in enumerate(content) if c["content"][0].get("text") == "On the calendar today"
    )
    assert content[i + 1]["content"][0]["content"][0]["content"][0]["text"] == cal[0].text


def test_thread_keeps_whole_sentences_under_280():
    rec = themes.ThemeRun.model_validate(
        {"run_id": "2026-10-14-am", "date": "2026-10-14", "slot": "am", "generated_at": "",
         "theme": "Oil", "why": "A" * 200 + ". " + "B" * 100 + ".", "lead": "move",
         "signals": [], "streak": 1, "fact_ids": [], "facts": [],
         "exhibits": [{"n": 1, "kind": "line", "title": "Exhibit 1: Brent", "subtitle": "x",
                       "file": "f"}]}
    )  # fmt: skip
    first, link = themes.thread(rec)
    assert first.endswith("A.") and "BBB" not in first
    assert link.startswith("The chart with sources")


def test_published_run_is_a_substack_card_and_the_thread_links_its_post(tmp_path, monkeypatch):
    from castelino import substack
    from castelino.dashboard.endpoints import themes as ep
    from castelino.dashboard.endpoints.themes import themes_posts

    monkeypatch.setattr(ep, "_dir", lambda: tmp_path)
    rec = themes.run(NOW, gather_fn=lambda now: FACTS, fetch=fetch, picker=lambda **kw: pick())
    assert themes_posts() == []  # drawn but not on Substack: no card
    got = {}

    def push(*, marker, title, subtitle, pngs, body, label, cover):
        got["doc"] = body({f: {"url": f"https://cdn/{f}"} for f in pngs})
        got["title"], got["subtitle"], got["cover"] = title, subtitle, cover
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({"draft_id": 7}))

    def publish(marker, *, section_id=None, send=False):
        got["section"], got["send"] = section_id, send
        url = "https://archresearch.substack.com/p/oils-run"
        marker.write_text(json.dumps({"draft_id": 7, "url": url}))
        return url

    monkeypatch.setattr(substack, "push", push)
    monkeypatch.setattr(substack, "publish", publish)
    note = themes.ChartLine(n=1, heading="Supply", sentence="Brent is climbing as talks stall.")
    url = themes.publish_substack(rec, say(note))
    assert url == "https://archresearch.substack.com/p/oils-run"
    assert got["title"] == f"Daily Chart | {rec.theme}" and got["subtitle"].startswith(
        "ARC Theme Charts · Wednesday"
    )
    assert (got["section"], got["send"]) == (themes.SECTION, False)
    drawn = {}  # the cover: the Morning Note's style, from the theme, its why and its signals
    monkeypatch.setattr(cover, "make", lambda path, headline, stories, **kw: drawn.update(locals()))
    got["cover"]()
    assert drawn["headline"] == rec.theme and drawn["stories"][0] == rec.why
    assert len(drawn["stories"]) == 4 and drawn["path"].name == f"{rec.run_id}.png"
    content = got["doc"]["content"]
    images = [i for i, c in enumerate(content) if c["type"] == "captionedImage"]
    assert len(images) == len(rec.exhibits)
    under = content[images[0] + 1]["content"]  # right under chart 1: the bold read, then the rest
    assert [t["text"] for t in under] == ["Supply. ", note.sentence]
    assert themes.thread(rec, themes.post_url(rec.run_id))[-1].endswith(url)
    [card] = themes_posts()
    assert card["url"] == url and card["title"] == rec.theme
    assert card["image"] == f"/api/themes/{rec.run_id}/charts/{rec.exhibits[0].file}"
