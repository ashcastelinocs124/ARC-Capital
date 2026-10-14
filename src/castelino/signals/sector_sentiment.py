"""Sector Sentiment Indicator — technicals vs fundamentals divergence.

Per GICS sector: take the top-10 stocks by market cap, score each stock's
technicals (momentum) and fundamentals (quality) as cross-sectional z-scores
over the whole ~110-stock universe, and read sentiment as
``divergence = tech_score - fund_score``:

  strongly positive -> price running ahead of fundamentals ("euphoric")
  strongly negative -> strong fundamentals nobody is buying ("fearful")

Design doc: docs/superpowers/specs/2026-08-29-sector-sentiment-design.md
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from castelino.config import get_settings

log = logging.getLogger(__name__)

# GICS display name -> (SPDR ETF, yfinance sector key).
# Data source is yfinance (free, unofficial Yahoo API) — prices batch in one
# download; fundamentals come from per-ticker statements/info.
SECTOR_ETFS: dict[str, tuple[str, str]] = {
    "Technology": ("XLK", "technology"),
    "Health Care": ("XLV", "healthcare"),
    "Financials": ("XLF", "financial-services"),
    "Cons. Discretionary": ("XLY", "consumer-cyclical"),
    "Cons. Staples": ("XLP", "consumer-defensive"),
    "Energy": ("XLE", "energy"),
    "Industrials": ("XLI", "industrials"),
    "Materials": ("XLB", "basic-materials"),
    "Utilities": ("XLU", "utilities"),
    "Real Estate": ("XLRE", "real-estate"),
    "Comm. Services": ("XLC", "communication-services"),
}

# Extra rows that are not GICS sectors: name -> (ETF, the GICS sector they sit inside, yfinance
# industry keys). Their stocks also count in that sector, so NVDA is in Technology and here.
OVERLAYS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "Semiconductors": (
        "SMH",
        "Technology",
        ("semiconductors", "semiconductor-equipment-materials"),
    ),
}

_TECH_METRICS = ("rsi14", "macd_hist", "vs_sma50", "vs_sma200", "ret_3m")
# pe_rel inverted (cheap = good) before scoring; see score_stocks.
_TRAILING_METRICS = ("rev_yoy", "earnings_growth", "pe_rel_inv")
# Forward metrics carry FORWARD_WEIGHT of the fundamental score: markets price expected earnings,
# and estimate revisions are what moves stocks. Trailing (last fiscal year) carries the rest.
_FORWARD_METRICS = ("fwd_pe_rel_inv", "eps_rev_90d")
FORWARD_WEIGHT = 2 / 3


class StockRow(BaseModel):
    symbol: str
    name: str
    sector: str
    market_cap: float
    # technical raw metrics (None = unavailable)
    rsi14: float | None
    macd_hist: float | None
    vs_sma50: float | None
    vs_sma200: float | None
    ret_3m: float | None
    # fundamental raw metrics
    rev_yoy: float | None
    earnings_growth: float | None
    pe_rel: float | None  # P/E relative to sector median (1.0 = at median)
    fwd_pe_rel: float | None = None  # forward P/E relative to the row's median forward P/E
    eps_rev_90d: float | None = None  # next-year EPS estimate now / 90 days ago - 1
    # computed
    tech_score: float | None = None
    fund_score: float | None = None
    divergence: float | None = None
    fundamentals_missing: bool = False


class StockContribution(BaseModel):
    """One constituent's share of the cap-weighted sector divergence."""

    symbol: str
    divergence: float
    contribution: float  # cap_share * divergence; sums to SectorScore.divergence


class SectorExplanation(BaseModel):
    """Is a sector's divergence one stock's story or the whole sector's?

    verdict + stats are deterministic (explain_concentration); `prose` is
    filled later by the sector explainer agent and may stay None.
    """

    verdict: str  # "stock_specific" | "sector_wide" | "mixed"
    n_agree: int  # constituents sharing the sector's sign
    n_total: int
    top_symbol: str
    top_share: float  # |top contribution| / |sector divergence|
    equal_weight_divergence: float
    contributions: list[StockContribution]  # sorted by |contribution| desc
    drivers: list[str]  # top-3 symbols by |contribution|
    prose: str | None = None
    generated_at: datetime | None = None


class SectorScore(BaseModel):
    sector: str
    etf: str
    divergence: float
    tech_score: float
    fund_score: float
    label: str  # "euphoric" | "fair" | "fearful"
    explanation: SectorExplanation | None = None
    # equal-weight (simple) means across constituents, next to the
    # cap-weighted numbers above
    avg_divergence: float | None = None
    avg_tech: float | None = None
    avg_fund: float | None = None
    zscore: float | None = None
    delta_since_prev: float | None = None
    part_of: str | None = None  # overlays only: the GICS sector whose stocks this row shares


class SectorSentimentSnapshot(BaseModel):
    as_of: datetime
    sectors: list[SectorScore]
    stocks: list[StockRow]
    narrative: str | None = None
    narrative_generated_at: datetime | None = None


def cross_sectional_score(values: dict[str, float | None]) -> dict[str, float]:
    """Z-score the non-None values across the universe, clip to +-3, /3 -> -1..+1."""
    present = {k: float(v) for k, v in values.items() if v is not None}
    if not present:
        return {}
    n = len(present)
    mean = sum(present.values()) / n
    var = sum((v - mean) ** 2 for v in present.values()) / n
    std = var**0.5
    if std == 0:
        return {k: 0.0 for k in present}
    return {k: max(-3.0, min(3.0, (v - mean) / std)) / 3.0 for k, v in present.items()}


def score_stocks(rows: list[StockRow]) -> list[StockRow]:
    """Fill tech_score/fund_score/divergence on each row, cross-sectionally.

    fund_score = FORWARD_WEIGHT x mean(forward metrics) + the rest x mean(trailing metrics).
    A metric missing on a stock just drops out of its side's average, and a side with no metrics
    leaves the other to count alone; a stock with NO fundamental metrics gets
    fundamentals_missing=True and no fund/divergence (never zero-filled).
    """

    # ponytail: equal weights within each side, tune when history justifies
    # Keyed per row, not per symbol: a stock in a sector and an overlay has a different pe_rel in
    # each. ponytail: it then counts twice in the z-score stats (6 of ~120 rows); dedupe if that grows.
    def key(r: StockRow) -> str:
        return f"{r.sector}|{r.symbol}"

    metric_values: dict[str, dict[str, float | None]] = {}
    for m in _TECH_METRICS:
        metric_values[m] = {key(r): getattr(r, m) for r in rows}
    metric_values["rev_yoy"] = {key(r): r.rev_yoy for r in rows}
    metric_values["earnings_growth"] = {key(r): r.earnings_growth for r in rows}
    for m in ("pe_rel", "fwd_pe_rel"):  # inverted: cheaper scores higher
        metric_values[f"{m}_inv"] = {
            key(r): (-getattr(r, m) if getattr(r, m) is not None else None) for r in rows
        }
    metric_values["eps_rev_90d"] = {key(r): r.eps_rev_90d for r in rows}

    scored = {m: cross_sectional_score(vals) for m, vals in metric_values.items()}

    def _avg(k: str, metrics: tuple[str, ...]) -> float | None:
        vals = [scored[m][k] for m in metrics if k in scored[m]]
        return sum(vals) / len(vals) if vals else None

    out: list[StockRow] = []
    for r in rows:
        tech = _avg(key(r), _TECH_METRICS)
        trailing, forward = _avg(key(r), _TRAILING_METRICS), _avg(key(r), _FORWARD_METRICS)
        if trailing is not None and forward is not None:
            fund = FORWARD_WEIGHT * forward + (1 - FORWARD_WEIGHT) * trailing
        else:
            fund = forward if forward is not None else trailing
        update: dict = {"tech_score": tech, "fund_score": fund}
        if fund is None:
            update["fundamentals_missing"] = True
        if tech is not None and fund is not None:
            update["divergence"] = tech - fund
        out.append(r.model_copy(update=update))
    return out


def explain_concentration(
    members: list[StockRow], *, top_share: float = 0.5, min_agree: int = 7
) -> SectorExplanation:
    """Deterministic verdict on whether a sector's divergence is concentrated.

    stock_specific: the largest contributor supplies >= `top_share` of the
                    sector value (a single mega-cap is the reading).
    sector_wide:    >= `min_agree` constituents share the sector's sign and
                    no single contributor dominates.
    mixed:          everything else.
    """
    total_cap = sum(m.market_cap for m in members)
    contribs = sorted(
        (
            StockContribution(
                symbol=m.symbol,
                divergence=m.divergence or 0.0,
                contribution=(m.divergence or 0.0) * m.market_cap / total_cap,
            )
            for m in members
        ),
        key=lambda c: -abs(c.contribution),
    )
    sector_div = sum(c.contribution for c in contribs)
    sign = 1 if sector_div >= 0 else -1
    n_agree = sum(1 for c in contribs if c.divergence * sign > 0)
    top = contribs[0]
    share = abs(top.contribution) / abs(sector_div) if sector_div else 1.0
    if share >= top_share:
        verdict = "stock_specific"
    elif n_agree >= min_agree:
        verdict = "sector_wide"
    else:
        verdict = "mixed"
    return SectorExplanation(
        verdict=verdict,
        n_agree=n_agree,
        n_total=len(contribs),
        top_symbol=top.symbol,
        top_share=share,
        equal_weight_divergence=sum(c.divergence for c in contribs) / len(contribs),
        contributions=contribs,
        drivers=[c.symbol for c in contribs[:3]],
    )


def aggregate_sectors(
    rows: list[StockRow],
    *,
    euphoric: float = 0.3,
    fearful: float = -0.3,
    top_share: float = 0.5,
    min_agree: int = 7,
) -> list[SectorScore]:
    """Cap-weighted mean of constituent scores per sector; skipped stocks
    (no divergence) drop out and the weights renormalize."""
    by_sector: dict[str, list[StockRow]] = {}
    for r in rows:
        if r.divergence is None:
            continue
        by_sector.setdefault(r.sector, []).append(r)

    scores: list[SectorScore] = []
    for sector, members in by_sector.items():
        total_cap = sum(m.market_cap for m in members)
        if total_cap <= 0:
            continue

        def _wavg(attr: str, members=members, total_cap=total_cap) -> float:
            return sum(getattr(m, attr) * m.market_cap for m in members) / total_cap

        div = _wavg("divergence")
        label = "euphoric" if div >= euphoric else "fearful" if div <= fearful else "fair"
        etf = (SECTOR_ETFS.get(sector) or OVERLAYS.get(sector) or ("?",))[0]
        scores.append(
            SectorScore(
                sector=sector,
                etf=etf,
                part_of=OVERLAYS[sector][1] if sector in OVERLAYS else None,
                divergence=div,
                tech_score=_wavg("tech_score"),
                fund_score=_wavg("fund_score"),
                label=label,
                explanation=explain_concentration(
                    members, top_share=top_share, min_agree=min_agree
                ),
                # ponytail: avg_* are now cap-weighted and mirror the headline
                # fields; kept so the snapshot/API shape stays stable.
                avg_divergence=div,
                avg_tech=_wavg("tech_score"),
                avg_fund=_wavg("fund_score"),
            )
        )
    scores.sort(key=lambda s: s.divergence, reverse=True)
    return scores


def _store_path() -> Path:
    return get_settings().resolved_paths.data / "sector_sentiment.json"


def _universe_path() -> Path:
    return get_settings().resolved_paths.data / "sector_universe.json"


# ── universe ───────────────────────────────────────────────────────────────


def _yf_top_companies(sector_key: str, limit: int) -> list[dict]:
    """Top companies for a yfinance sector key: [{symbol, name}]. Ordered by
    Yahoo's market weight (≈ market cap); cap itself is fetched later."""
    import yfinance as yf

    df = yf.Sector(sector_key).top_companies
    if df is None or df.empty:
        return []
    out = []
    for symbol, row in df.head(limit).iterrows():
        out.append({"symbol": str(symbol), "name": str(row.get("name", symbol))})
    return out


def _yf_top_industries(industry_keys: tuple[str, ...], limit: int) -> list[dict]:
    """Top companies across several yfinance industries: [{symbol, name, market_cap}]. Yahoo's
    market weight is a share of its own industry, so the merged list is ranked by market cap."""
    import yfinance as yf

    names: dict[str, str] = {}
    for key in industry_keys:
        df = yf.Industry(key).top_companies
        if df is not None:
            for symbol, row in df.head(limit).iterrows():
                names[str(symbol)] = str(row.get("name", symbol))
    caps: dict[str, float] = {}
    for symbol in names:
        try:
            caps[symbol] = float(yf.Ticker(symbol).fast_info["market_cap"] or 0.0)
        except Exception:  # noqa: BLE001 — an unknown cap ranks last rather than failing the row
            caps[symbol] = 0.0
    top = sorted(caps, key=caps.__getitem__, reverse=True)[:limit]
    return [{"symbol": s, "name": names[s], "market_cap": caps[s]} for s in top]


def get_universe(force: bool = False) -> dict[str, list[dict]]:
    """Sector (and overlay) -> top-N stocks: [{symbol, name}]. Screened via yfinance
    rankings; cached on disk for cfg.sector_sentiment.universe_cache_hours."""
    cfg = get_settings().sector_sentiment
    path = _universe_path()
    fetchers = {
        s: (lambda k=k: _yf_top_companies(k, cfg.top_n_per_sector))
        for s, (_e, k) in SECTOR_ETFS.items()
    }
    fetchers |= {
        s: (lambda k=k: _yf_top_industries(k, cfg.top_n_per_sector))
        for s, (_e, _p, k) in OVERLAYS.items()
    }
    if not force and path.exists():
        raw = json.loads(path.read_text())
        fetched = datetime.fromisoformat(raw["fetched_at"])
        age_h = (datetime.now(UTC) - fetched).total_seconds() / 3600
        # a group missing from the cache (new, or failed last time) refetches the lot
        if age_h < cfg.universe_cache_hours and set(fetchers) <= set(raw["universe"]):
            return raw["universe"]

    universe: dict[str, list[dict]] = {}
    for sector, fetch in fetchers.items():
        try:
            results = fetch()
        except Exception:
            log.warning("sector sentiment: sector ranking failed for %s", sector)
            continue
        if not results:
            log.warning("sector sentiment: empty sector ranking for %s", sector)
            continue
        universe[sector] = results
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"fetched_at": datetime.now(UTC).isoformat(), "universe": universe}))
    return universe


# ── snapshot store ─────────────────────────────────────────────────────────


def load_snapshot() -> SectorSentimentSnapshot | None:
    path = _store_path()
    if not path.exists():
        return None
    raw = json.loads(path.read_text())
    if not raw.get("latest"):
        return None
    try:
        return SectorSentimentSnapshot.model_validate(raw["latest"])
    except Exception:
        # schema drift (old field names) — treat as no snapshot; the daily
        # history list in the file survives the next save either way
        log.warning("sector sentiment: stored snapshot has stale schema; ignoring")
        return None


def save_snapshot(snap: SectorSentimentSnapshot) -> None:
    """Persist latest + append (date, sector, divergence) history, at most
    one row per sector per calendar day (same-day saves overwrite)."""
    path = _store_path()
    raw = {"latest": None, "history": []}
    if path.exists():
        raw = json.loads(path.read_text())
    day = snap.as_of.date().isoformat()
    history = [h for h in raw.get("history", []) if h["date"] != day]
    history.extend(
        {"date": day, "sector": s.sector, "divergence": s.divergence} for s in snap.sectors
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"latest": json.loads(snap.model_dump_json()), "history": history}))


def history_zscore(sector: str, value: float, history: list[dict], min_obs: int) -> float | None:
    """Z of today's divergence vs this sector's own daily history."""
    obs = [h["divergence"] for h in history if h["sector"] == sector]
    if len(obs) < min_obs:
        return None
    n = len(obs)
    mean = sum(obs) / n
    std = (sum((v - mean) ** 2 for v in obs) / n) ** 0.5
    if std == 0:
        return None
    return (value - mean) / std


# ── collection + refresh ───────────────────────────────────────────────────


def compute_rsi(closes: list[float], period: int = 14) -> float | None:
    """Wilder's RSI over the last value of *closes*. None if not enough data."""
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for prev, cur in zip(closes[:-1], closes[1:], strict=False):
        change = cur - prev
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for g, loss in zip(gains[period:], losses[period:], strict=True):
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def _ema(values: list[float], period: int) -> list[float]:
    k = 2.0 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def compute_macd_hist(closes: list[float]) -> float | None:
    """Latest MACD histogram (12/26 EMA minus its 9-EMA signal)."""
    if len(closes) < 35:
        return None
    macd_line = [f - s for f, s in zip(_ema(closes, 12), _ema(closes, 26), strict=True)]
    signal = _ema(macd_line, 9)
    return macd_line[-1] - signal[-1]


def _yf_closes(symbols: list[str]) -> dict[str, list[float]]:
    """Daily closes per symbol via ONE batched yfinance download (~1y)."""
    import yfinance as yf

    df = yf.download(symbols, period="1y", interval="1d", auto_adjust=True, progress=False)
    closes: dict[str, list[float]] = {}
    if df is None or df.empty:
        return closes
    close = df["Close"] if "Close" in df.columns.get_level_values(0) else df
    for sym in symbols:
        try:
            series = close[sym].dropna() if hasattr(close, "columns") else close.dropna()
            closes[sym] = [float(v) for v in series.tolist()]
        except Exception:
            continue
    return closes


def _yf_fundamentals(symbol: str) -> dict:
    """rev_yoy, earnings_growth, pe, fwd_pe, eps_rev_90d, market_cap from Yahoo — None on any gap."""
    import yfinance as yf

    out = {
        "rev_yoy": None,
        "earnings_growth": None,
        "pe": None,
        "fwd_pe": None,
        "eps_rev_90d": None,
        "market_cap": None,
    }
    try:
        t = yf.Ticker(symbol)
        inc = t.income_stmt
        if inc is not None and not inc.empty and inc.shape[1] >= 2:

            def _row(name: str) -> tuple[float, float] | None:
                if name not in inc.index:
                    return None
                vals = inc.loc[name].dropna()
                if len(vals) < 2 or not float(vals.iloc[1]):
                    return None
                return float(vals.iloc[0]), float(vals.iloc[1])

            rev = _row("Total Revenue")
            if rev:
                out["rev_yoy"] = rev[0] / rev[1] - 1.0
            ni = _row("Net Income")
            if ni and ni[1] > 0:
                out["earnings_growth"] = ni[0] / ni[1] - 1.0
        info = t.info or {}
        if info.get("trailingPE") is not None:
            out["pe"] = float(info["trailingPE"])
        if info.get("marketCap") is not None:
            out["market_cap"] = float(info["marketCap"])
        if info.get("forwardPE") is not None:
            out["fwd_pe"] = float(info["forwardPE"])
        trend = t.eps_trend  # analysts' EPS estimates: now and 7/30/60/90 days ago
        if trend is not None and "+1y" in trend.index:
            now, ago = float(trend.loc["+1y", "current"]), float(trend.loc["+1y", "90daysAgo"])
            if (
                now > 0 and ago > 0
            ):  # Yahoo sends 0 for a missing estimate (SK hynix); NaN fails too
                out["eps_rev_90d"] = now / ago - 1.0
    except Exception:
        log.debug("fundamentals: yfinance failed for %s", symbol)
    return out


def _technicals_from_closes(closes: list[float]) -> dict:
    """rsi14, macd_hist, vs_sma50, vs_sma200, ret_3m from a close series."""
    out = {"rsi14": None, "macd_hist": None, "vs_sma50": None, "vs_sma200": None, "ret_3m": None}
    if not closes:
        return out
    px = closes[-1]
    out["rsi14"] = compute_rsi(closes)
    out["macd_hist"] = compute_macd_hist(closes)
    if len(closes) >= 50:
        s50 = sum(closes[-50:]) / 50
        if s50:
            out["vs_sma50"] = px / s50 - 1.0
    if len(closes) >= 200:
        s200 = sum(closes[-200:]) / 200
        if s200:
            out["vs_sma200"] = px / s200 - 1.0
    if len(closes) > 63 and closes[-64]:
        out["ret_3m"] = px / closes[-64] - 1.0
    return out


def collect_rows(universe: dict[str, list[dict]]) -> list[StockRow]:
    """Fetch raw metrics for every stock in the universe. pe_rel (fwd_pe_rel) is the
    stock's trailing (forward) P/E divided by its row's median."""
    # a stock in a sector and an overlay is fetched once
    all_symbols = list(dict.fromkeys(m["symbol"] for members in universe.values() for m in members))
    funds: dict[str, dict] = {}
    try:
        closes_by_symbol = _yf_closes(all_symbols)
    except Exception:
        log.exception("technicals: batched price download failed")
        closes_by_symbol = {}

    rows: list[StockRow] = []
    pe_by_sector: dict[tuple[str, str], list[tuple[int, float]]] = {}
    for sector, members in universe.items():
        for m in members:
            tech = _technicals_from_closes(closes_by_symbol.get(m["symbol"], []))
            if m["symbol"] not in funds:
                funds[m["symbol"]] = _yf_fundamentals(m["symbol"])
            fund = funds[m["symbol"]]
            rows.append(
                StockRow(
                    symbol=m["symbol"],
                    name=m["name"],
                    sector=sector,
                    market_cap=fund["market_cap"] or float(m.get("market_cap") or 0.0),
                    pe_rel=None,
                    rev_yoy=fund["rev_yoy"],
                    earnings_growth=fund["earnings_growth"],
                    eps_rev_90d=fund["eps_rev_90d"],
                    **tech,
                )
            )
            for field in ("pe", "fwd_pe"):
                if fund[field] is not None and fund[field] > 0:
                    pe_by_sector.setdefault((sector, field), []).append(
                        (len(rows) - 1, fund[field])
                    )
    # pe_rel / fwd_pe_rel: stock P/E / its row's median P/E
    for (_sector, field), pairs in pe_by_sector.items():
        pes = sorted(p for _, p in pairs)
        median = pes[len(pes) // 2]
        if median > 0:
            for idx, pe in pairs:
                rows[idx] = rows[idx].model_copy(update={f"{field}_rel": pe / median})
    return rows


def refresh(force: bool = False) -> SectorSentimentSnapshot:
    """Universe -> collect -> score -> aggregate -> narrate -> persist.

    A full refresh is ~110 yfinance lookups, so unless *force*
    is set it no-ops (returns the stored snapshot) when the stored one is
    younger than cfg.refresh_interval_hours.
    """
    cfg = get_settings().sector_sentiment
    prev = load_snapshot()
    if not force and prev is not None:
        age_h = (datetime.now(UTC) - prev.as_of).total_seconds() / 3600
        if age_h < cfg.refresh_interval_hours:
            return prev

    universe = get_universe()
    rows = score_stocks(collect_rows(universe))
    sectors = aggregate_sectors(
        rows,
        euphoric=cfg.euphoric_threshold,
        fearful=cfg.fearful_threshold,
        top_share=cfg.stock_specific_top_share,
        min_agree=cfg.sector_wide_min_agree,
    )
    # Yahoo throttling can drop fundamentals for some stocks; keep the previous snapshot then
    missing = sorted(set(universe) - {s.sector for s in sectors})
    if missing:
        raise RuntimeError(f"no fundamentals from Yahoo for {', '.join(missing)}; kept previous")

    # z vs own history + delta vs previous snapshot
    raw_history: list[dict] = []
    if _store_path().exists():
        raw_history = json.loads(_store_path().read_text()).get("history", [])
    prev_by_sector = {s.sector: s.divergence for s in prev.sectors} if prev else {}
    for i, s in enumerate(sectors):
        update: dict = {
            "zscore": history_zscore(
                s.sector, s.divergence, raw_history, cfg.min_history_for_zscore
            )
        }
        if s.sector in prev_by_sector:
            update["delta_since_prev"] = s.divergence - prev_by_sector[s.sector]
        sectors[i] = s.model_copy(update=update)

    snap = SectorSentimentSnapshot(as_of=datetime.now(UTC), sectors=sectors, stocks=rows)
    # Narrative is written by the Claude explainer in scripts/refresh_snapshot.py,
    # after the history backfill (it needs trends + events as context).
    save_snapshot(snap)
    log.info("sector sentiment refreshed: %d sectors, %d stocks", len(sectors), len(rows))
    return snap
