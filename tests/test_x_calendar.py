import json
from datetime import datetime

from castelino import x_calendar, x_post
from castelino.x_calendar import ET, CardRead, ReleaseRead

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
    monkeypatch.setattr(x_calendar, "draw_card", lambda *a, **k: a[-1].write_bytes(b"png"))
    outs, calls = list(reads), []
    monkeypatch.setattr(
        x_calendar.CardWriter,
        "__call__",
        lambda self, **k: (
            calls.append(k) or CardRead(text=outs.pop(0) if len(outs) > 1 else outs[0])
        ),
    )
    return calls


def test_pick_keeps_key_releases_with_a_consensus_and_the_biggest_reporters():
    rows = x_calendar.pick(EVENTS, "2026-10-21", data=4, earnings=5)
    assert [r["name"] for r in rows if r["kind"] != "earnings"] == [
        "Housing Starts",
        "Pending Home Sales",
    ]
    assert [r["ticker"] for r in rows if r["kind"] == "earnings"] == ["META", "TSLA"]


def test_watch_list_is_the_days_four_most_important_rows():
    rows = x_calendar.pick(EVENTS, "2026-10-21", data=4, earnings=5) + [
        us("2026-10-21", "08:30", "CPI", 0.3, 0.4, "%", "inflation"),
        earn("2026-10-21", "LRCX", "Lam Research", 3.47e11, 2.17, "post"),
        earn("2026-10-21", "PM", "Philip Morris", 3.12e11, 2.3, "pre"),
    ]
    assert [x_calendar.key(r) for r in x_calendar.watch_rows(rows)] == [
        "US|08:30|CPI|None",
        "E|META",
        "E|TSLA",
        "E|LRCX",
    ]


def test_a_release_already_out_is_left_off_todays_card(monkeypatch, tmp_path):
    week_file(tmp_path)
    fake_card(monkeypatch)
    x_calendar.card(now=WED.replace(hour=9), root=tmp_path)
    keys = [w["key"] for w in x_calendar.day_record(tmp_path, WED)["watch"]]
    assert "US|08:30|Housing Starts|None" not in keys and "US|10:00|Pending Home Sales|None" in keys


def test_a_label_never_repeats_the_country():
    e = {"kind": "jobs", "country": "CN", "name": "Chinese Unemployment Rate", "measure": None}
    assert x_calendar.label(e) == "Chinese Unemployment Rate"
    assert (
        x_calendar.label({**e, "country": "JP", "name": "National Core CPI"})
        == "Japan National Core CPI"
    )
    assert x_calendar.company({"company": "Travelers Companies (The)"}) == "Travelers Companies"


def test_monday_posts_the_week_and_tuesday_the_day(monkeypatch, tmp_path):
    week_file(tmp_path)
    fake_card(monkeypatch)
    monkeypatch.delenv("X_SCOUT_LIVE", raising=False)
    mon = x_calendar.card(now=MON, root=tmp_path)
    assert mon["kind"] == "week" and mon["text"].startswith("🗓️ WEEK AHEAD · ")
    assert [w["key"] for w in x_calendar.day_record(tmp_path, MON)["watch"]] == ["E|FITB"]
    tue = x_calendar.card(now=TUE, root=tmp_path)
    assert tue["kind"] == "day" and tue["text"].startswith("📅 TODAY · ") and tue["dry_run"]
    keys = [w["key"] for w in x_calendar.day_record(tmp_path, TUE)["watch"]]
    assert set(keys) == {"US|10:00|NAHB Housing Market Index|None", "E|GE", "E|NFLX"}
    assert x_calendar.card(now=TUE, root=tmp_path) is None  # once a day


def test_card_read_with_an_invented_figure_falls_back_to_code(monkeypatch, tmp_path):
    week_file(tmp_path)
    calls = fake_card(monkeypatch, reads=("Housing starts jump 5% this week.",))
    rec = x_calendar.card(now=WED, root=tmp_path)
    assert len(calls) == 2 and "5%" in " ".join(calls[1]["fix"])
    assert rec["text"] == x_calendar.FALLBACK["day"]


def test_another_weeks_file_posts_nothing(monkeypatch, tmp_path):
    week_file(tmp_path, "2026-10-12", "2026-10-16")
    fake_card(monkeypatch)
    assert x_calendar.card(now=TUE, root=tmp_path) is None


def test_draw_card_renders_a_png(tmp_path):
    rows = x_calendar.pick(EVENTS, "2026-10-21", data=4, earnings=5)
    x_calendar.draw_card("Wednesday, Oct 21", "What's out today", *x_calendar.day_table(rows),
                         "TODAY", tmp_path / "c.png")  # fmt: skip
    assert (tmp_path / "c.png").stat().st_size > 10_000


def econ_row(name, actual, cons, prev, t="08:30"):
    return {"country": "United States", "eventName": name, "gmt": t, "actual": actual,
            "consensus": cons, "previous": prev}  # fmt: skip


def fake_watch(monkeypatch, tmp_path, econ, earnings, sentence="Builders are still busy."):
    week_file(tmp_path)
    fake_card(monkeypatch)
    x_calendar.card(now=WED, root=tmp_path)  # sets Wednesday's watch list
    feeds = {"economicevents": econ, "earnings": earnings}
    monkeypatch.setattr(x_calendar.nasdaq, "fetch_day", lambda kind, day: feeds[kind])
    monkeypatch.setattr(
        x_calendar.ReleaseWriter, "__call__", lambda self, **k: ReleaseRead(sentence=sentence)
    )
    return feeds


def test_a_landed_release_posts_once(monkeypatch, tmp_path):
    feeds = fake_watch(
        monkeypatch, tmp_path,
        [econ_row("Housing Starts", "1.32M", "1.3M", "1.275M"),
         econ_row("Pending Home Sales", "&nbsp;", "-0.4%", "0.3%", "10:00")],
        [{"symbol": "TSLA", "eps": "", "epsForecast": "$0.21", "surprise": "N/A"}],
    )  # fmt: skip
    at = WED.replace(hour=8, minute=35)
    out = x_calendar.watch(now=at, root=tmp_path)
    assert [r["text"] for r in out] == [
        "🚨 US Housing Starts: 1.32M vs 1.3M expected (previous 1.275M).\n\nBuilders are still busy."
    ]
    assert x_calendar.watch(now=at, root=tmp_path) == []  # never twice
    feeds["earnings"] = [
        {"symbol": "TSLA", "eps": "$0.25", "epsForecast": "$0.21", "surprise": "19.05"}
    ]
    out = x_calendar.watch(now=at.replace(hour=16, minute=20), root=tmp_path)
    assert out[0]["text"].startswith("💼 Tesla EPS: $0.25 vs $0.21 expected, a 19.05% beat.")


def test_a_releases_mm_and_yy_are_one_watch_slot_and_one_post(monkeypatch, tmp_path):
    ppi = [{**us("2026-10-21", "08:30", "Core PPI", c, p, "%", "inflation"), "measure": m}
           for m, c, p in (("m/m", 0.3, 0.2), ("y/y", 4.4, 4.8))]  # fmt: skip
    rows = x_calendar.pick(EVENTS + ppi, "2026-10-21", data=4, earnings=5)
    keys = [x_calendar.key(r) for r in x_calendar.watch_rows(rows)]
    assert (
        keys[:2] == ["US|08:30|Core PPI|m/m", "US|08:30|Core PPI|y/y"] and len(keys) == 5
    )  # 4 slots
    week_file(tmp_path)
    p = tmp_path / "data" / "week_ahead.json"
    p.write_text(json.dumps({**json.loads(p.read_text()), "events": EVENTS + ppi}))
    fake_card(monkeypatch)
    x_calendar.card(now=WED, root=tmp_path)
    monkeypatch.setattr(x_calendar.nasdaq, "fetch_day", lambda kind, day: [
        econ_row("Core PPI", "0.7%", "0.3%", "0.2%"), econ_row("Core PPI", "5.0%", "4.4%", "4.8%")
    ] if kind == "economicevents" else [])  # fmt: skip
    monkeypatch.setattr(
        x_calendar.ReleaseWriter, "__call__", lambda self, **k: ReleaseRead(sentence="")
    )
    out = x_calendar.watch(now=WED.replace(hour=8, minute=35), root=tmp_path)
    assert [r["text"] for r in out] == [
        "🚨 US Core PPI: 0.7% m/m vs 0.3% expected (previous 0.2%); 5% y/y vs 4.4% expected (previous 4.8%)."
    ]


def test_a_sentence_with_a_digit_is_dropped(monkeypatch, tmp_path):
    fake_watch(monkeypatch, tmp_path, [econ_row("Housing Starts", "1.32M", "1.3M", "1.275M")], [],
               sentence="Starts rose 2% on the month.")  # fmt: skip
    out = x_calendar.watch(now=WED.replace(hour=8, minute=35), root=tmp_path)
    assert out[0]["text"] == "🚨 US Housing Starts: 1.32M vs 1.3M expected (previous 1.275M)."


def test_release_posts_cap_at_four_a_day(monkeypatch, tmp_path):
    fake_watch(
        monkeypatch, tmp_path,
        [econ_row("Housing Starts", "1.32M", "1.3M", "1.275M"),
         econ_row("Pending Home Sales", "0.1%", "-0.4%", "0.3%", "10:00")],
        [{"symbol": "META", "eps": "$7.01", "surprise": "5.1"},
         {"symbol": "TSLA", "eps": "$0.25", "surprise": "19.05"}],
    )  # fmt: skip
    rec = x_calendar.day_record(tmp_path, WED)
    rec["releases"] = [{"key": "earlier", "text": "x"}]  # one already out today
    x_calendar.save_day(tmp_path, WED, rec)
    assert len(x_calendar.watch(now=WED.replace(hour=16, minute=30), root=tmp_path)) == 3


def test_live_watch_posts_on_x(monkeypatch, tmp_path):
    fake_watch(monkeypatch, tmp_path, [econ_row("Housing Starts", "1.32M", "1.3M", "1.275M")], [])
    monkeypatch.setenv("X_SCOUT_LIVE", "1")
    monkeypatch.setattr(x_post, "can_post", lambda: True)
    sent = []
    monkeypatch.setattr(x_post, "post", lambda text, **k: sent.append(text) or "99")
    out = x_calendar.watch(now=WED.replace(hour=8, minute=35), root=tmp_path)
    assert out[0]["id"] == "99" and not out[0]["dry_run"] and len(sent) == 1
