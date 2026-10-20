from datetime import date, datetime

import numpy as np
import pandas as pd

from castelino import x_moves, x_post
from castelino.x_moves import ET, Move

TODAY = date(2026, 10, 15)


def closes(last_move: float, end: date = TODAY, crash_at: int | None = None) -> pd.Series:
    """300 business days of ~0.5% daily noise ending on `end`, the last day moving `last_move` %."""
    rets = np.random.default_rng(0).normal(0, 0.5, 300)
    if crash_at is not None:
        rets[crash_at] = -4.0
    rets[-1] = last_move
    idx = pd.bdate_range(end=end, periods=300)
    return pd.Series(100 * np.cumprod(1 + rets / 100), index=idx)


def test_big_move_trips_and_names_the_last_bigger_day():
    s = closes(-3.0, crash_at=200)
    m = x_moves.measure("S&P 500", "%", s, TODAY)
    assert m.change == -3.0 and m.z <= -2.5
    assert m.since == s.index[200].date()


def test_stale_bar_is_skipped():
    # a holiday: Yahoo's last bar is yesterday, which would re-post yesterday's move
    assert x_moves.measure("S&P 500", "%", closes(-3.0, end=date(2026, 10, 14)), TODAY) is None


def test_yields_move_in_bp():
    s = pd.Series(
        4.0 + np.random.default_rng(1).normal(0, 0.03, 300).cumsum(),
        index=pd.bdate_range(end=TODAY, periods=300),
    )
    s.iloc[-1] = s.iloc[-2] + 0.16
    m = x_moves.measure("US 10-year yield", "bp", s, TODAY)
    assert m.change == 16.0 and m.z >= 2.5
    assert x_moves.fmt(m) == "+16bp"


def mv(name="Nasdaq 100", change=-3.4, z=-2.9, unit="%", since=date(2026, 4, 10)):
    return Move(name, unit, change, 100.0, z, since)


def test_compose_keeps_the_why_only_if_the_post_fits():
    post = x_moves.compose([mv(), mv("S&P 500", -2.6, -2.7)], "Chipmakers sold off.", TODAY)
    assert post.startswith(
        "Nasdaq 100 −3.4% today, its biggest one-day drop since Apr 10 (a 2.9σ move)."
    )
    assert "Also moving: S&P 500 −2.6%." in post and "Why: Chipmakers sold off." in post
    long = x_moves.compose([mv()], "x" * 250, TODAY)
    assert "Why:" not in long and x_post.xlen(long) <= 280
    assert "since Apr 10, 2025" in x_moves.compose([mv(since=date(2025, 4, 10))], None, TODAY)
    assert "in 5 years" in x_moves.compose([mv(since=None)], None, TODAY)


def test_explain_drops_an_uncited_answer(monkeypatch):
    from castelino.data import web_search

    text = "Chipmakers fell after new export curbs ([reuters.com](https://reuters.com/a))."
    monkeypatch.setattr(
        web_search,
        "search_cited",
        lambda s, u: (text, [("Reuters", "https://reuters.com/a", 40, 70)]),
    )
    assert x_moves.explain([mv()], TODAY) == "Chipmakers fell after new export curbs."
    monkeypatch.setattr(web_search, "search_cited", lambda s, u: (text, []))
    assert x_moves.explain([mv()], TODAY) is None


def test_run_posts_each_market_once_and_caps_the_day(monkeypatch, tmp_path):
    moves = [mv(), mv("Gold", 0.3, 0.3)]
    monkeypatch.setattr(x_moves, "check", lambda today: moves)
    monkeypatch.setattr(x_moves, "explain", lambda hits, today: "Chipmakers sold off.")
    monkeypatch.setattr(x_moves, "chart", lambda *a: {"kind": None})
    monkeypatch.setenv("X_MOVES_LIVE", "1")
    monkeypatch.setattr(x_post, "can_post", lambda: True)
    sent = []
    monkeypatch.setattr(x_post, "post", lambda text, media_id=None: sent.append(text) or "123")
    at = datetime(2026, 10, 15, 11, 5, tzinfo=ET)

    rec = x_moves.run(now=at, root=tmp_path)
    assert rec["markets"] == ["Nasdaq 100"] and rec["id"] == "123" and len(sent) == 1
    assert x_moves.run(now=at, root=tmp_path) is None  # Nasdaq already posted today
    assert x_moves.run(now=at.replace(hour=8), root=tmp_path) is None  # before 9:35
    assert x_moves.run(now=datetime(2026, 10, 17, 11, tzinfo=ET), root=tmp_path) is None  # Saturday

    for name in ("Gold", "Copper", "Bitcoin"):
        moves.append(mv(name, 5.0, 3.0))
    assert x_moves.run(now=at, root=tmp_path)["markets"] == ["Gold", "Copper", "Bitcoin"]
    moves.append(mv("WTI crude", 6.0, 4.0))
    x_moves.run(now=at, root=tmp_path)
    assert x_moves.run(now=at, root=tmp_path) is None and len(sent) == 3  # 3 a day


def test_dry_run_records_without_posting(monkeypatch, tmp_path):
    monkeypatch.setattr(x_moves, "check", lambda today: [mv()])
    monkeypatch.setattr(x_moves, "explain", lambda hits, today: None)
    monkeypatch.setattr(x_moves, "chart", lambda *a: {"kind": None})
    monkeypatch.delenv("X_MOVES_LIVE", raising=False)
    monkeypatch.setattr(x_post, "post", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    rec = x_moves.run(now=datetime(2026, 10, 15, 11, 5, tzinfo=ET), root=tmp_path)
    assert rec["dry_run"] and rec["id"] is None and rec["text"].endswith("arcresearch.markets")


def pick(choice="context", series="fred:DGS10"):
    return x_moves.ChartChoice(
        choice=choice, series=series, name="US 10-year yield", window_days=30, reason="r"
    )


def test_chart_follows_the_picker_and_falls_back(monkeypatch, tmp_path):
    drawn = []
    monkeypatch.setattr(x_moves, "context_chart", lambda c, p, now: drawn.append(c.series))
    monkeypatch.setattr(x_moves, "intraday_chart", lambda moves, p: drawn.append("intraday"))
    at, png = datetime(2026, 10, 15, 11, 5, tzinfo=ET), tmp_path / "c.png"

    monkeypatch.setattr(x_moves.ChartPicker, "__call__", lambda self, **k: pick())
    assert x_moves.chart([mv()], "post", at, png)["kind"] == "context"
    monkeypatch.setattr(x_moves.ChartPicker, "__call__", lambda self, **k: pick("intraday", ""))
    assert x_moves.chart([mv()], "post", at, png)["kind"] == "intraday"
    assert drawn == ["fred:DGS10", "intraday"]

    def boom(*a):
        raise RuntimeError("no such series")

    monkeypatch.setattr(x_moves.ChartPicker, "__call__", lambda self, **k: pick())
    monkeypatch.setattr(x_moves, "context_chart", boom)
    rec = x_moves.chart([mv()], "post", at, png)  # a failed context chart → intraday
    assert rec["kind"] == "intraday" and "no such series" in rec["error"]
    monkeypatch.setattr(x_moves.ChartPicker, "__call__", boom)  # a failed picker → intraday
    assert x_moves.chart([mv()], "post", at, png)["kind"] == "intraday"
    monkeypatch.setattr(x_moves, "intraday_chart", boom)  # nothing drawable → no chart
    assert x_moves.chart([mv()], "post", at, png)["kind"] is None


def test_context_chart_rejects_a_bad_series(tmp_path):
    import pytest

    with pytest.raises(ValueError):
        x_moves.context_chart(pick(series="DGS10; rm"), tmp_path / "c.png", datetime(2026, 10, 15))


def test_intraday_chart_draws_the_lead_unit_only(monkeypatch, tmp_path):
    idx = pd.date_range("2026-10-15 09:30", periods=78, freq="5min", tz="America/New_York")
    asked = []

    def bars(sym):
        asked.append(sym)
        return pd.Series(np.linspace(100, 96.6, 78), index=idx)

    monkeypatch.setattr(x_moves, "fetch_bars", bars)
    lead = Move("Nasdaq 100", "%", -3.4, 96.6, -2.9, None, "^NDX", 100.0)
    rates = Move("US 10-year yield", "bp", 12, 4.4, 2.6, None, "^TNX", 4.28)
    x_moves.intraday_chart([lead, rates], tmp_path / "c.png")
    assert (tmp_path / "c.png").stat().st_size > 10_000 and asked == ["^NDX"]


def test_run_attaches_the_chart_and_survives_a_failed_upload(monkeypatch, tmp_path):
    monkeypatch.setattr(x_moves, "check", lambda today: [mv()])
    monkeypatch.setattr(x_moves, "explain", lambda hits, today: None)

    def fake_chart(moves, post, now, png):
        png.write_bytes(b"png")
        return {"kind": "intraday"}

    monkeypatch.setattr(x_moves, "chart", fake_chart)
    monkeypatch.setenv("X_MOVES_LIVE", "1")
    monkeypatch.setattr(x_post, "can_post", lambda: True)
    sent = []
    monkeypatch.setattr(x_post, "post", lambda text, media_id=None: sent.append(media_id) or "1")
    monkeypatch.setattr(x_post, "upload_image", lambda data: "m1")
    at = datetime(2026, 10, 15, 11, 5, tzinfo=ET)
    rec = x_moves.run(now=at, root=tmp_path)
    assert sent == ["m1"] and rec["chart"]["file"] == "2026-10-15/1105.png"

    def no_upload(data):
        raise RuntimeError("X image upload said 503")

    monkeypatch.setattr(x_moves, "check", lambda today: [mv("Gold", 3.0, 3.0)])
    monkeypatch.setattr(x_post, "upload_image", no_upload)
    x_moves.run(now=at.replace(minute=35), root=tmp_path)
    assert sent == ["m1", None]  # posted text-only
