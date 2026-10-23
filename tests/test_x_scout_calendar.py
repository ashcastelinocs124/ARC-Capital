import json
from datetime import datetime

from castelino import substack, x_post, x_scout
from castelino.week_ahead import econ
from castelino.x_scout import ET, CardRead, ReleaseRead

MON = datetime(2026, 10, 19, 7, 0, tzinfo=ET)
TUE = datetime(2026, 10, 20, 7, 0, tzinfo=ET)
WED = datetime(2026, 10, 21, 7, 0, tzinfo=ET)


def us(day, t, name, cons, prev, unit="", kind="other"):
    return {"date": day, "time_et": t, "kind": kind, "country": "US", "name": name, "measure": None,
            "consensus": cons, "previous": prev, "actual": None, "unit": unit}  # fmt: skip


def earn(day, ticker, company, cap, est, session):
    return {"date": day, "time_et": None, "kind": "earnings", "name": company, "ticker": ticker,
            "company": company, "group": "sp500", "market_cap": cap, "eps_est": est,
            "eps_year_ago": None, "session": session}  # fmt: skip


EVENTS = [
    earn("2026-10-19", "FITB", "Fifth Third Bancorp", 4.6e10, 1.09, "pre"),
    us("2026-10-20", "10:00", "NAHB Housing Market Index", 31.0, 32.0),
    earn("2026-10-20", "GE", "GE Aerospace", 3.24e11, 2.02, "pre"),
    earn("2026-10-20", "NFLX", "Netflix", 3.02e11, 0.82, "post"),
    us("2026-10-21", "07:00", "MBA Mortgage Applications", None, -2.7, "%"),
    us("2026-10-21", "08:30", "Housing Starts", 1.3, 1.275, "M"),
    us("2026-10-21", "10:00", "Pending Home Sales", -0.4, 0.3, "%"),
    us("2026-10-21", "10:00", "Pending Home Sales Index", None, 71.2),
    earn("2026-10-21", "TSLA", "Tesla", 1.431e12, 0.21, "post"),
    earn("2026-10-21", "META", "Meta Platforms", 1.877e12, 6.67, "post"),
    us("2026-10-23", "08:30", "Initial Jobless Claims", 200.0, 199.0, "K", "jobs"),
    {
        "date": "2026-10-23",
        "time_et": "19:30",
        "kind": "inflation",
        "country": "JP",
        "name": "National Core CPI",
        "measure": None,
        "consensus": 2.1,
        "previous": 1.7,
        "actual": None,
        "unit": "%",
    },  # fmt: skip
]


def week_file(root, start="2026-10-19", end="2026-10-23"):
    p = root / "data" / "week_ahead.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"week_start": start, "week_end": end, "events": EVENTS}))


def fake_card(monkeypatch, reads=("Big Tech's week: Meta and Tesla report Wednesday.",)):
    """draw_card and the Card Writer replaced; returns the writer's calls."""
    monkeypatch.setattr(x_scout, "draw_card", lambda *a, **k: a[-1].write_bytes(b"png"))
    outs, calls = list(reads), []
    monkeypatch.setattr(
        x_scout.CardWriter,
        "__call__",
        lambda self, **k: (
            calls.append(k) or CardRead(text=outs.pop(0) if len(outs) > 1 else outs[0])
        ),
    )
    return calls


def test_pick_keeps_key_releases_with_a_consensus_and_the_biggest_reporters():
    rows = x_scout.pick(EVENTS, "2026-10-21", data=4, earnings=5)
    assert [r["name"] for r in rows if r["kind"] != "earnings"] == [
        "Housing Starts",
        "Pending Home Sales",
    ]
    assert [r["ticker"] for r in rows if r["kind"] == "earnings"] == ["META", "TSLA"]


def test_a_seventh_slot_fits_inflation_abroad_on_a_busy_earnings_day():
    # 2026-10-22 replayed: jobless claims, five reporters and Japan's CPI at 19:30 ET (not posted that day)
    day = "2026-10-23"
    reps = [earn(day, t, t, cap, 1.0, "pre")
            for t, cap in (("PG", 3.5e11), ("UNP", 1.4e11), ("WDC", 4e10), ("LMT", 1.1e11), ("VLO", 4.5e10))]  # fmt: skip
    keys = [x_scout.key(r) for r in x_scout.watch_rows(x_scout.pick(EVENTS + reps, day, 4, 5))]
    assert len(keys) == 7 and keys[0] == "US|08:30|Initial Jobless Claims|None"
    assert keys[-1] == "JP|19:30|National Core CPI|None"


def test_trading_economics_names_rank_like_the_old_ones():
    rank = x_scout._rank
    for name in (
        "Inflation Rate",
        "Core Inflation Rate",
        "Non Farm Payrolls",
        "Core PCE Price Index",
    ):
        assert rank(us("2026-10-23", "08:30", name, 0.3, 0.2)) == 0.0, name
    assert rank(us("2026-10-23", "08:30", "Retail Sales", 0.3, 0.2)) == 1.0


def test_watch_list_is_the_days_seven_most_important_rows_ai_names_first():
    spacex = {**earn("2026-10-21", "SPCX", "SpaceX", None, 0.13, None), "group": "ai_extra"}
    rows = x_scout.pick(EVENTS, "2026-10-21", data=4, earnings=5) + [
        us("2026-10-21", "08:30", "CPI", 0.3, 0.4, "%", "inflation"),
        earn("2026-10-21", "LRCX", "Lam Research", 3.47e11, 2.17, "post"),
        earn("2026-10-21", "PM", "Philip Morris", 3.12e11, 2.3, "pre"),
        spacex,  # no market value from Yahoo's date, but an AI name: first among companies
    ]
    assert [x_scout.key(r) for r in x_scout.watch_rows(rows)] == [
        "US|08:30|CPI|None",
        "E|SPCX",
        "E|META",
        "E|TSLA",
        "E|LRCX",
        "E|PM",
        "US|08:30|Housing Starts|None",
    ]


def test_earnings_are_searched_in_their_session_at_most_every_15_minutes():
    pre, post = {"session": "pre"}, {"session": "post"}
    at = WED.replace(hour=16, minute=10)
    assert x_scout.earnings_due(post, at, []) and not x_scout.earnings_due(pre, at, [])
    assert not x_scout.earnings_due(post, at, ["2026-10-21T16:05-04:00"])  # 5 minutes ago
    assert x_scout.earnings_due(post, at, ["2026-10-21T15:50-04:00"])
    assert x_scout.earnings_due({"session": None}, WED.replace(hour=7), [])  # unknown: both windows
    assert not x_scout.earnings_due(post, at, ["2026-10-21T06:00-04:00"] * 12)  # a day's searches


def test_a_release_already_out_is_left_off_todays_card(monkeypatch, tmp_path):
    week_file(tmp_path)
    fake_card(monkeypatch)
    x_scout.card(now=WED.replace(hour=9), root=tmp_path)
    keys = [w["key"] for w in x_scout.day_record(tmp_path, WED)["watch"]]
    assert "US|08:30|Housing Starts|None" not in keys and "US|10:00|Pending Home Sales|None" in keys


def test_a_label_never_repeats_the_country():
    e = {"kind": "jobs", "country": "CN", "name": "Chinese Unemployment Rate", "measure": None}
    assert x_scout.label(e) == "Chinese Unemployment Rate"
    assert (
        x_scout.label({**e, "country": "JP", "name": "National Core CPI"})
        == "Japan National Core CPI"
    )
    assert x_scout.company({"company": "Travelers Companies (The)"}) == "Travelers Companies"


def test_monday_posts_the_week_and_tuesday_the_day(monkeypatch, tmp_path):
    week_file(tmp_path)
    fake_card(monkeypatch)
    monkeypatch.delenv("X_SCOUT_LIVE", raising=False)
    mon = x_scout.card(now=MON, root=tmp_path)
    assert mon["kind"] == "week" and mon["text"].startswith("WEEK AHEAD · ")
    assert [w["key"] for w in x_scout.day_record(tmp_path, MON)["watch"]] == ["E|FITB"]
    tue = x_scout.card(now=TUE, root=tmp_path)
    assert tue["kind"] == "day" and tue["text"].startswith("TODAY · ") and tue["dry_run"]
    keys = [w["key"] for w in x_scout.day_record(tmp_path, TUE)["watch"]]
    assert set(keys) == {"US|10:00|NAHB Housing Market Index|None", "E|GE", "E|NFLX"}
    assert x_scout.card(now=TUE, root=tmp_path) is None  # once a day


def test_card_read_with_an_invented_figure_falls_back_to_code(monkeypatch, tmp_path):
    week_file(tmp_path)
    calls = fake_card(monkeypatch, reads=("Housing starts jump 5% this week.",))
    rec = x_scout.card(now=WED, root=tmp_path)
    assert len(calls) == 2 and "5%" in " ".join(calls[1]["fix"])
    assert rec["text"] == x_scout.FALLBACK["day"]


def test_another_weeks_file_posts_nothing(monkeypatch, tmp_path):
    week_file(tmp_path, "2026-10-12", "2026-10-16")
    fake_card(monkeypatch)
    assert x_scout.card(now=TUE, root=tmp_path) is None


def test_draw_card_renders_a_png(tmp_path):
    rows = x_scout.pick(EVENTS, "2026-10-21", data=4, earnings=5)
    x_scout.draw_card("Wednesday, Oct 21", "What's out today", *x_scout.day_table(rows),
                         "TODAY", tmp_path / "c.png")  # fmt: skip
    assert (tmp_path / "c.png").stat().st_size > 10_000


def econ_row(name, actual, cons, prev, t="08:30", measure=None):
    """A release as Trading Economics' live page gives it (te.day_events)."""
    (a, u), (c, _), (p, _) = (econ.parse_num(s) for s in (actual, cons, prev))
    return {"date": "2026-10-21", "time_et": t, "kind": "other", "country": "US", "name": name,
            "measure": measure, "consensus": c, "previous": p, "actual": a, "unit": u}  # fmt: skip


def live_econ(monkeypatch, rows):
    asked = []

    def day_events(day, countries=None, get=None):
        asked.append(set(countries or ()))
        return rows() if callable(rows) else rows

    monkeypatch.setattr(x_scout.te, "day_events", day_events)
    return asked


def fake_watch(monkeypatch, tmp_path, econ, earnings, sentence="Builders are still busy."):
    week_file(tmp_path)
    fake_card(monkeypatch)
    x_scout.card(now=WED, root=tmp_path)  # sets Wednesday's watch list
    feeds = {"economicevents": econ, "earnings": earnings}
    feeds["asked"] = live_econ(monkeypatch, lambda: feeds["economicevents"])
    monkeypatch.setattr(
        x_scout.ReleaseWriter, "__call__", lambda self, **k: ReleaseRead(sentence=sentence)
    )
    # earnings by ticker: the line a cited search found, or None while it hasn't reported
    monkeypatch.setattr(x_scout, "earnings_result", lambda w, day: feeds["earnings"].get(w["ticker"]))  # fmt: skip
    monkeypatch.setattr(
        x_scout.release_charts, "segments", lambda *a: None
    )  # no SEC calls in tests
    return feeds


def test_a_landed_release_posts_once(monkeypatch, tmp_path):
    feeds = fake_watch(
        monkeypatch, tmp_path,
        [econ_row("Housing Starts", "1.32M", "1.3M", "1.275M"),
         econ_row("Pending Home Sales", "&nbsp;", "-0.4%", "0.3%", "10:00")],
        {"TSLA": None},
    )  # fmt: skip
    at = WED.replace(hour=8, minute=35)
    out = x_scout.watch(now=at, root=tmp_path)
    assert [r["text"] for r in out] == [
        "US Housing Starts: 1.32M vs 1.3M expected (previous 1.275M).\n\nBuilders are still busy."
    ]
    assert feeds["asked"][0] == {"US"}  # only the watched releases' countries are read
    assert x_scout.watch(now=at, root=tmp_path) == []  # never twice
    feeds["earnings"] = {"TSLA": "Tesla (TSLA) Q3: EPS $0.25 vs $0.21 expected."}
    out = x_scout.watch(now=at.replace(hour=16, minute=20), root=tmp_path)
    assert out[0]["text"].startswith("Tesla (TSLA) Q3: EPS $0.25 vs $0.21 expected.")


def test_a_releases_mm_and_yy_are_one_watch_slot_and_one_post(monkeypatch, tmp_path):
    ppi = [{**us("2026-10-21", "08:30", "Core PPI", c, p, "%", "inflation"), "measure": m}
           for m, c, p in (("m/m", 0.3, 0.2), ("y/y", 4.4, 4.8))]  # fmt: skip
    rows = x_scout.pick(EVENTS + ppi, "2026-10-21", data=4, earnings=5)
    keys = [x_scout.key(r) for r in x_scout.watch_rows(rows)]
    assert (
        keys[:2] == ["US|08:30|Core PPI|m/m", "US|08:30|Core PPI|y/y"] and len(keys) == 6
    )  # 5 groups fit the 6 slots: the pair is one
    week_file(tmp_path)
    p = tmp_path / "data" / "week_ahead.json"
    p.write_text(json.dumps({**json.loads(p.read_text()), "events": EVENTS + ppi}))
    fake_card(monkeypatch)
    x_scout.card(now=WED, root=tmp_path)
    live_econ(monkeypatch, [econ_row("Core PPI", "0.7%", "0.3%", "0.2%", measure="m/m"),
                            econ_row("Core PPI", "5.0%", "4.4%", "4.8%", measure="y/y")])  # fmt: skip
    monkeypatch.setattr(
        x_scout.ReleaseWriter, "__call__", lambda self, **k: ReleaseRead(sentence="")
    )
    out = x_scout.watch(now=WED.replace(hour=8, minute=35), root=tmp_path)
    assert [r["text"] for r in out] == [
        "US Core PPI: 0.7% m/m vs 0.3% expected (previous 0.2%); 5% y/y vs 4.4% expected (previous 4.8%)."
    ]


def test_a_sentence_with_a_digit_is_dropped(monkeypatch, tmp_path):
    fake_watch(monkeypatch, tmp_path, [econ_row("Housing Starts", "1.32M", "1.3M", "1.275M")], {},
               sentence="Starts rose 2% on the month.")  # fmt: skip
    out = x_scout.watch(now=WED.replace(hour=8, minute=35), root=tmp_path)
    assert out[0]["text"] == "US Housing Starts: 1.32M vs 1.3M expected (previous 1.275M)."


def test_release_posts_cap_at_seven_a_day(monkeypatch, tmp_path):
    fake_watch(
        monkeypatch, tmp_path,
        [econ_row("Housing Starts", "1.32M", "1.3M", "1.275M"),
         econ_row("Pending Home Sales", "0.1%", "-0.4%", "0.3%", "10:00")],
        {"META": "Meta Platforms (META) Q3: EPS $7.01 vs $6.67 expected.",
         "TSLA": "Tesla (TSLA) Q3: EPS $0.25 vs $0.21 expected."},
    )  # fmt: skip
    rec = x_scout.day_record(tmp_path, WED)
    rec["releases"] = [{"key": f"earlier{i}", "text": "x"} for i in range(6)]  # six already out
    x_scout.save_day(tmp_path, WED, rec)
    assert len(x_scout.watch(now=WED.replace(hour=16, minute=30), root=tmp_path)) == 1


def test_live_watch_posts_on_x(monkeypatch, tmp_path):
    fake_watch(monkeypatch, tmp_path, [econ_row("Housing Starts", "1.32M", "1.3M", "1.275M")], {})
    monkeypatch.setenv("X_SCOUT_LIVE", "1")
    monkeypatch.setattr(x_post, "can_post", lambda: True)
    sent = []
    monkeypatch.setattr(x_post, "post", lambda text, **k: sent.append(text) or "99")
    monkeypatch.setattr(substack, "can_note", lambda: True)
    monkeypatch.setattr(substack, "post_note", lambda *a: (_ for _ in ()).throw(AssertionError))
    out = x_scout.watch(now=WED.replace(hour=8, minute=35), root=tmp_path)
    assert (
        out[0]["id"] == "99" and not out[0]["dry_run"] and len(sent) == 1
    )  # release posts: X only


def live_x(monkeypatch, upload=lambda data: "m"):
    monkeypatch.setenv("X_SCOUT_LIVE", "1")
    monkeypatch.setattr(x_post, "can_post", lambda: True)
    monkeypatch.setattr(x_post, "upload_image", upload)
    sent = []
    monkeypatch.setattr(
        x_post, "post", lambda text, **k: sent.append((text, k.get("media_id"))) or "99"
    )
    return sent


def test_a_data_release_posts_with_its_actual_vs_forecast_chart(monkeypatch, tmp_path):
    fake_watch(monkeypatch, tmp_path, [econ_row("Housing Starts", "1.32M", "1.3M", "1.275M")], {})
    sent = live_x(monkeypatch)
    out = x_scout.watch(now=WED.replace(hour=8, minute=35), root=tmp_path)
    assert sent[0][1] == ["m"] and out[0]["charts"] == ["US-Housing-Starts.png"]
    assert (
        tmp_path / "data/x_posts/calendar/2026-10-21/US-Housing-Starts.png"
    ).stat().st_size > 10_000


def test_an_earnings_post_carries_up_to_three_charts(monkeypatch, tmp_path):
    fake_watch(monkeypatch, tmp_path, [], {"TSLA": "$TSLA Q3: EPS 48 cents vs 45 cents expected."})
    pngs = [tmp_path / f"{n}.png" for n in ("sales", "profit", "vs")]
    for q in pngs:
        q.write_bytes(b"png")
    monkeypatch.setattr(x_scout.release_charts, "earnings_charts", lambda *a: pngs)
    ids = iter(["a", "b", "c"])
    sent = live_x(monkeypatch, upload=lambda data: next(ids))
    x_scout.watch(now=WED.replace(hour=16, minute=20), root=tmp_path)
    assert sent[0][1] == ["a", "b", "c"]


def test_charts_that_fail_never_hold_up_the_post(monkeypatch, tmp_path):
    fake_watch(monkeypatch, tmp_path, [econ_row("Housing Starts", "1.32M", "1.3M", "1.275M")], {})
    monkeypatch.setattr(x_scout.release_charts, "data_chart", lambda *a: 1 / 0)
    sent = live_x(monkeypatch)
    out = x_scout.watch(now=WED.replace(hour=8, minute=35), root=tmp_path)
    assert sent[0][1] is None and out[0]["charts"] == [] and out[0]["id"] == "99"


def test_an_upload_that_fails_posts_without_that_chart(monkeypatch, tmp_path):
    fake_watch(monkeypatch, tmp_path, [econ_row("Housing Starts", "1.32M", "1.3M", "1.275M")], {})
    sent = live_x(monkeypatch, upload=lambda data: 1 / 0)
    x_scout.watch(now=WED.replace(hour=8, minute=35), root=tmp_path)
    assert sent[0][1] is None


def test_live_card_also_posts_a_note_with_the_card(monkeypatch, tmp_path):
    week_file(tmp_path)
    fake_card(monkeypatch)
    monkeypatch.setenv("X_SCOUT_LIVE", "1")
    monkeypatch.setattr(x_post, "can_post", lambda: True)
    monkeypatch.setattr(x_post, "upload_image", lambda data: "m1")
    monkeypatch.setattr(x_post, "post", lambda text, **k: "x1")
    notes = []
    monkeypatch.setattr(substack, "can_note", lambda: True)
    monkeypatch.setattr(substack, "post_note", lambda text, png: notes.append((text, png)) or "n1")
    rec = x_scout.card(now=TUE, root=tmp_path)
    assert rec["id"] == "x1" and rec["note_id"] == "n1"
    assert notes == [(rec["text"], tmp_path / "data/x_posts/calendar/2026-10-20/card.png")]


def test_an_earnings_line_needs_today_and_every_figure_from_a_cited_line(monkeypatch):
    from castelino.agents.update.models import Fact
    from castelino.data import web_search
    from castelino.x_scout import EarningsRead

    fact = Fact(id="E1", text="SpaceX posted EPS of $0.35 vs $0.13 expected [Reuters]",
                numbers=[0.35, 0.13], provenance="reported", source_title="Reuters", source_url="u")  # fmt: skip
    monkeypatch.setattr(web_search, "search_cited", lambda *a, **k: ("text", []))
    monkeypatch.setattr(x_scout, "facts_from_search", lambda *a: [fact])
    monkeypatch.setattr(x_scout, "trades", lambda t: True)
    w = {**earn("2026-10-20", "SPCX", "SpaceX", None, 0.13, None), "group": "ai_extra"}
    reads = {
        "not yet": EarningsRead(reported=False, line=""),
        "invented": EarningsRead(
            reported=True, line="SpaceX (SPCX) Q3: EPS $0.41 vs $0.13 expected"
        ),
        "good": EarningsRead(reported=True, line="SpaceX (SPCX) Q3: EPS $0.35 vs $0.13 expected"),
    }
    for case, read in reads.items():
        monkeypatch.setattr(x_scout.EarningsReader, "__call__", lambda self, read=read, **k: read)
        got = x_scout.earnings_result(w, TUE.date())
        assert got == (
            "SpaceX (SPCX) Q3: EPS $0.35 vs $0.13 expected." if case == "good" else None
        ), case
