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
        "📉 Nasdaq 100 −3.4% today, its biggest one-day drop since Apr 10 (a 2.9σ move)."
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
    monkeypatch.setenv("X_MOVES_LIVE", "1")
    monkeypatch.setattr(x_post, "can_post", lambda: True)
    sent = []
    monkeypatch.setattr(x_post, "post", lambda text: sent.append(text) or "123")
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
    monkeypatch.delenv("X_MOVES_LIVE", raising=False)
    monkeypatch.setattr(x_post, "post", lambda text: (_ for _ in ()).throw(AssertionError))
    rec = x_moves.run(now=datetime(2026, 10, 15, 11, 5, tzinfo=ET), root=tmp_path)
    assert rec["dry_run"] and rec["id"] is None and rec["text"].endswith("arcresearch.markets")
