"""Market Fear & Greed (0-100), CNN's recipe on free data.

Five daily signals, each ranked against its own trailing 2 years (0 = its most fearful day in
that window, 100 = its most greedy); the index is their average:

  momentum  S&P 500 vs its 125-day average
  breadth   share of the Sector Sentiment stocks above their 200-day average
  volatility VIX vs its 50-day average (inverted)
  junk      high-yield spread, FRED BAMLH0A0HYM2 (inverted)
  haven     S&P 500 minus IEF (Treasuries) return over 20 days

CNN's other two (put/call ratio, NYSE highs vs lows) have no free source. Computed by the
Sector Sentiment refresh; a failure leaves the snapshot's fear_greed empty.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import pandas as pd
from pydantic import BaseModel

WINDOW = 504  # trading days, about 2 years
MIN_OBS = 252  # a signal needs a year of history before it is ranked
ZONES = ((25, "Extreme fear"), (45, "Fear"), (55, "Neutral"), (75, "Greed"))
INDEX = ("^GSPC", "^VIX", "IEF")


class FGComponent(BaseModel):
    key: str
    name: str
    score: int
    raw: str  # the reading in words, e.g. "VIX 21.4 vs its 50-day average 17.9"
    previous: int | None = None  # the session before (the Daily Update says which signal moved)
    week_ago: int | None = None


class FearGreed(BaseModel):
    score: int
    zone: str
    as_of: date
    components: list[FGComponent]
    previous: int | None = None
    week_ago: int | None = None
    month_ago: int | None = None
    year_ago: int | None = None


def zone(score: float) -> str:
    return next((name for edge, name in ZONES if score < edge), "Extreme greed")


def rank(s: pd.Series, invert: bool = False) -> pd.Series:
    """Percentile of each day's value within its trailing WINDOW, as 0-100."""
    r = s.dropna().rolling(WINDOW, min_periods=MIN_OBS).rank(pct=True) * 100
    return 100 - r if invert else r


def _closes(symbols: list[str]) -> pd.DataFrame:
    import yfinance as yf

    df = yf.download(symbols, period="3y", interval="1d", auto_adjust=True, progress=False)
    close = df["Close"]
    close.index = pd.to_datetime(close.index).tz_localize(None)
    return close


def _fred(series_id: str) -> pd.Series:
    from castelino.forecast.regime import _fetch_fred_series

    return _fetch_fred_series(series_id)


def compute(
    stocks: list[str],
    fetch_closes: Callable[[list[str]], pd.DataFrame] = _closes,
    fetch_fred: Callable[[str], pd.Series] = _fred,
) -> FearGreed:
    close = fetch_closes(list(INDEX) + stocks)
    spx, vix, ief = (close[s].dropna() for s in INDEX)
    hy = fetch_fred("BAMLH0A0HYM2").reindex(spx.index, method="ffill")

    # rows with no stock prices (index-only days) and the odd gap must not blank 200 days of averages
    px = close[[s for s in stocks if s in close.columns]].dropna(how="all")
    sma200 = px.rolling(200, min_periods=150).mean()
    # ponytail: today's top-10s, so the past is survivor-biased (yesterday's losers aren't in it)
    breadth = (px > sma200).where(px.notna() & sma200.notna()).mean(axis=1)

    momentum = spx / spx.rolling(125).mean() - 1
    vol = vix / vix.rolling(50).mean() - 1
    haven = spx.pct_change(20) - ief.reindex(spx.index).pct_change(20)

    signals = {
        "momentum": ("Market momentum", rank(momentum)),
        "breadth": ("Stock breadth", rank(breadth)),
        "volatility": ("Volatility", rank(vol, invert=True)),
        "junk": ("Junk bond demand", rank(hy, invert=True)),
        "haven": ("Safe-haven demand", rank(haven)),
    }
    scores = pd.DataFrame({k: s for k, (_, s) in signals.items()}).reindex(spx.index)
    index = scores.mean(axis=1, skipna=False).dropna()  # a day counts only with all 5 signals
    if index.empty:
        raise RuntimeError("fear & greed: not enough history to rank the signals")
    today = index.index[-1]

    def at(days: int) -> int | None:
        past = index[index.index <= today - pd.Timedelta(days=days)]
        return round(past.iloc[-1]) if len(past) else None

    def signal_at(k: str, when: pd.Timestamp | None) -> int | None:
        past = scores[k].loc[:when].dropna() if when is not None else ()
        return round(past.iloc[-1]) if len(past) else None

    before = index.index[-2] if len(index) > 1 else None
    week = today - pd.Timedelta(days=7)

    hy_now, hy_month = hy.loc[today], hy[hy.index <= today - pd.Timedelta(days=30)].iloc[-1]
    m, b, h = momentum.loc[today], breadth.loc[today], haven.loc[today]
    raw = {
        "momentum": f"S&P 500 {abs(m):.1%} {'above' if m >= 0 else 'below'} its 125-day average",
        "breadth": f"{b:.0%} of our {px.shape[1]} stocks above their 200-day average",
        "volatility": f"VIX {vix.loc[today]:.1f} vs its 50-day average {vix.rolling(50).mean().loc[today]:.1f}",
        "junk": f"High-yield spread {hy_now:.2f}%, {(hy_now - hy_month) * 100:+.0f} bp in a month",
        "haven": f"Stocks {'beat' if h >= 0 else 'trail'} Treasuries by {abs(h) * 100:.1f} pts over 20 days",
    }
    score = round(index.iloc[-1])
    return FearGreed(
        score=score,
        zone=zone(score),
        as_of=today.date(),
        components=[
            FGComponent(
                key=k,
                name=name,
                score=round(scores.loc[today, k]),
                raw=raw[k],
                previous=signal_at(k, before),
                week_ago=signal_at(k, week),
            )
            for k, (name, _) in signals.items()
        ],
        previous=round(index.iloc[-2]) if len(index) > 1 else None,
        week_ago=at(7),
        month_ago=at(30),
        year_ago=at(365),
    )


def sector_score(divergence: float, euphoric: float = 0.3, fearful: float = -0.3) -> int:
    """A sector's divergence on the same 0-100 scale: the euphoric/fearful lines land on 75/25."""
    edge = euphoric if divergence >= 0 else -fearful
    return max(0, min(100, round(50 + 25 * divergence / edge)))
