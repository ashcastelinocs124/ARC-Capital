import json
from datetime import datetime

import pandas as pd
import pytest

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


def test_no_drawable_chart_saves_nothing(tmp_path):
    bad = [chart("line", "?", ["yahoo:NOPE"])]
    with pytest.raises(RuntimeError):
        themes.run(
            NOW, gather_fn=lambda now: FACTS, fetch=fetch, picker=lambda **kw: pick(charts=bad)
        )
    assert not list(tmp_path.glob("*.json"))


def test_heatmap_scatter_and_range_draw_from_series_and_take_reader_names(tmp_path):
    charts = [
        chart("heatmap", "Where oil reaches", ["M1", "M2", "fred:DGS10"], 0,
              names=["Brent", "S&P 500", "10y yield"]),
        chart("scatter", "Oil against stocks", ["M1", "M2"], 180, names=["Brent", "S&P 500"]),
        chart("range", "How stretched", ["M1", "fred:DGS10"], 0),
        chart("range", "Odds can't range", ["M1", "N1"], 0),  # N1 has no series: dropped
    ]  # fmt: skip
    rec = themes.run(
        NOW, gather_fn=lambda now: FACTS, fetch=fetch, picker=lambda **kw: pick(charts=charts)
    )
    assert [e.kind for e in rec.exhibits] == ["heatmap", "scatter", "range"]
    assert rec.exhibits[0].subtitle.startswith("Most unusual: ")
    assert "correlate" in rec.exhibits[1].subtitle
    assert "% of its 1-year range" in rec.exhibits[2].subtitle
    assert all((tmp_path / "charts" / rec.run_id / e.file).is_file() for e in rec.exhibits)
    # the browser draws the same numbers: heatmap cells, weekly scatter points, 1-year ranges
    heat, sc, rng = (e.data for e in rec.exhibits)
    assert [r["name"].split(" · ")[0] for r in heat["rows"]] == ["Brent", "S&P 500", "10y yield"]
    assert all(len(r["cells"]) == 4 for r in heat["rows"]) and heat["rows"][2]["rate"]
    assert sc["names"] == ["Brent", "S&P 500"] and sc["window"] == 180 and len(sc["points"]) > 26
    assert all(r["lo"] <= r["last"] <= r["hi"] for r in rng["rows"])


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

    with pytest.raises(RuntimeError):  # the link post fails: two posts out, saved
        themes.post_today(NOW, tmp_path, post=post, upload=upload)
    fail["at"] = None
    ids = themes.post_today(NOW, tmp_path, post=post, upload=upload)  # resumes with the link
    assert ids == ["id1", "id2", "id3"] and uploads == [b"\x89PNG"] * 2
    (t1, r1, m1), (t2, r2, m2), (t3, r3, m3) = sent
    assert (
        t1
        == "Before the open: Oil's run revives the inflation scare 🧵\n\nBrent rose 4.1% on the week."
    )
    assert t2.startswith("2/ ") and (r1, m1, r2, m2) == (None, "m1", "id1", "m2")
    assert t3.startswith("All 2 charts") and t3.endswith("/themes?run=2026-10-14-am")
    assert (r3, m3) == ("id2", None)
    assert themes.post_today(NOW, tmp_path, post=post, upload=upload) == ids  # never twice
    assert len(sent) == 3
    assert themes.post_today(NOW.replace(day=17), tmp_path, post=post, upload=upload) is None  # Sat


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
    assert link.startswith("The chart, interactive")
