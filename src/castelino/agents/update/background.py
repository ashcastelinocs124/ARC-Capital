"""Background facts (code, no LLM): the history behind the stocks, data and stories in the findings.

Runs after the analysts and before the Editor (daily run and admin rebuild). For each subject it
finds in the findings it adds one fact and links it to those findings, so the guard checks every
historical figure the Editor writes like any other figure:

- stock history (Yahoo): last close, 1 week / 1 month / 3 months / year to date %, 52-week high
  and low, % below the high. Companies are found as "Name (TICKER)" in the text, by name from the
  S&P 500 + AI-names universe, or as a Yahoo series a finding already cites.
- data history (FRED): a release's last 12 readings with its streak and "highest/lowest since",
  or a daily series' 1 month and 3 month change, up days and "highest/lowest since".
- what ARC said before: up to 2 earlier Morning Notes (last 30 days) that covered the subject.

Fact ids start "bg-" and are rebuilt from scratch on every call, so a rebuild doesn't stack them.
A failed fetch skips that subject and comes back as a data gap; it never fails the note.
"""

from __future__ import annotations

import csv
import json
import logging
import re
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from castelino.agents.update.charts import is_rate
from castelino.agents.update.guard import _FIG
from castelino.agents.update.models import Fact, Finding, Point, SeriesRef

log = logging.getLogger(__name__)

MAX_STOCKS, MAX_SERIES, NOTE_DAYS, NOTES_PER_SUBJECT, READINGS = 10, 6, 30, 2, 12
SITE = "https://arcresearch.markets"
# ponytail: acronyms that look like "(TICKER)" in news text; extend when one slips through.
NOT_TICKERS = {
    "AI", "API", "ADP", "BLS", "BOJ", "CEO", "CFO", "CPI", "CPU", "ECB", "EPS", "ETF", "EU", "FED",
    "FOMC", "GDP", "GPU", "HBM", "IMF", "IPO", "ISM", "LLM", "OPEC", "PCE", "PMI", "PPI", "SEC",
    "UK", "US", "USA", "YTD", "YOY", "MOM", "NYSE",
}  # fmt: skip
# How the news usually names a company when its legal name doesn't appear.
# ponytail: hand-kept; add a name when a story about a listed company gets no price history.
ALIASES = {
    "Meta": ("META", "Meta Platforms"), "Google": ("GOOGL", "Alphabet"),
    "Alphabet": ("GOOGL", "Alphabet"), "Amazon": ("AMZN", "Amazon"), "Nvidia": ("NVDA", "Nvidia"),
    "Goldman": ("GS", "Goldman Sachs"), "Citi": ("C", "Citigroup"), "Citigroup": ("C", "Citigroup"),
    "Wells Fargo": ("WFC", "Wells Fargo"), "Morgan Stanley": ("MS", "Morgan Stanley"),
    "TSMC": ("TSM", "TSMC"), "Samsung": ("005930.KS", "Samsung Electronics"),
    "SoftBank": ("9984.T", "SoftBank Group"), "AMD": ("AMD", "AMD"), "Tesla": ("TSLA", "Tesla"),
    "Broadcom": ("AVGO", "Broadcom"), "Micron": ("MU", "Micron Technology"),
    "CoreWeave": ("CRWV", "CoreWeave"), "Palantir": ("PLTR", "Palantir"),
}  # fmt: skip
_SUFFIX = re.compile(
    r",?\s+(Inc\.?|Incorporated|Corporation|Corp\.?|Company|Co\.?|& Co\.?|Holdings?|Group|plc|"
    r"PLC|Ltd\.?|Limited|N\.V\.|S\.A\.|SE|AG|Class [A-C]|\(The\))$"
)
_NAMED_TICKER = re.compile(
    r"([A-Z][\w&.'’-]*(?:\s+[A-Z][\w&.'’-]*){0,3})\s+\((?:(?:NYSE|Nasdaq|NASDAQ)[:\s]+)?"
    r"([A-Z]{1,5}(?:\.[A-Z]{1,2})?)\)"
)


# ── fetchers (replaced in tests) ───────────────────────────────────────────


def default_close(symbol: str) -> pd.Series:
    from castelino.forecast import regime

    return regime._fetch_yf_close(symbol)


def default_fred(series_id: str) -> pd.Series:
    from castelino.forecast import regime

    return regime._fetch_fred_series(series_id)


def load_universe(path: Path | None = None) -> list[tuple[str, str]]:
    if path is None:
        from castelino.config import get_settings

        path = get_settings().root / "data" / "week_ahead" / "universe.csv"
    try:
        with open(path, newline="") as fh:
            return [(r["ticker"], r["name"]) for r in csv.DictReader(fh)]
    except OSError:
        return []


# ── finding subjects ───────────────────────────────────────────────────────


def _name_variants(universe: list[tuple[str, str]]) -> dict[str, tuple[str, str]]:
    """Text to look for → (ticker, display name): the full name, the name without its suffix,
    its first word only when that word is a coined brand no other company shares ("JPMorgan",
    not "Boston" or "Williams", which also name people and places), and ALIASES."""
    out: dict[str, tuple[str, str]] = {}
    firsts: dict[str, list[tuple[str, str]]] = {}
    for ticker, name in universe:
        short = name
        while (s := _SUFFIX.sub("", short).strip()) != short:
            short = s
        for v in (name, short):
            if len(v) >= 3:
                out[v] = (ticker, short)
        firsts.setdefault(short.split()[0], []).append((ticker, short))
    for word, hits in firsts.items():
        coined = re.search(r"[a-z][A-Z]|^[A-Z]{2,}[a-z]", word) is not None  # PayPal, JPMorgan
        if len(hits) == 1 and coined and word not in out:
            out[word] = hits[0]
    return out | ALIASES


def _mentions(text: str, needle: str) -> bool:
    # all-caps names (NVIDIA) also match their usual spelling (Nvidia)
    flags = re.I if needle.isupper() and len(needle) >= 4 else 0
    return re.search(rf"(?<![\w-]){re.escape(needle)}(?![\w-])", text, flags) is not None


def stock_subjects(
    findings: list[Finding], facts: list[Fact], universe: list[tuple[str, str]]
) -> dict[str, tuple[str, list[str]]]:
    """ticker → (name, finding ids), in finding order: named tickers and universe companies in
    news/AI/alt findings first, then Yahoo series the findings cite (ETFs, indexes)."""
    by = {f.id: f for f in facts}
    names = _name_variants(universe)
    found: dict[str, tuple[str, list[str]]] = {}

    def add(ticker: str, name: str, fid: str) -> None:
        _, fids = found.setdefault(ticker, (name, []))
        if fid not in fids:
            fids.append(fid)

    ordered = sorted(findings, key=lambda f: f.agent == "macro")  # company stories lead
    texts = {
        f.id: " ".join([f.claim, *(by[i].text for i in f.fact_ids if i in by)]) for f in ordered
    }
    for f in ordered:  # "Name (TICKER)" is the surest sign, so those come first
        for m in _NAMED_TICKER.finditer(texts[f.id]):
            if m.group(2) not in NOT_TICKERS:
                add(m.group(2), m.group(1).strip(), f.id)
    for f in ordered:
        for needle, (ticker, name) in names.items():
            if _mentions(texts[f.id], needle):
                add(ticker, name, f.id)
    for f in ordered:
        refs = [f.series, *(by[i].series for i in f.fact_ids if i in by)]
        for ref in refs:
            if ref is not None and ref.provider == "yahoo" and ref.kind == "daily":
                add(ref.id, ref.label or ref.id, f.id)
    return found


def series_subjects(
    findings: list[Finding], facts: list[Fact]
) -> dict[str, tuple[SeriesRef, list[str]]]:
    """FRED series id → (the ref a finding cites, finding ids). Releases and daily series."""
    by = {f.id: f for f in facts}
    found: dict[str, tuple[SeriesRef, list[str]]] = {}
    for f in findings:
        for ref in [f.series, *(by[i].series for i in f.fact_ids if i in by)]:
            if ref is None or ref.provider != "fred":
                continue
            key = f"{ref.id}|{ref.label}" if ref.kind == "release" else ref.id  # CPI y/y vs m/m
            _, fids = found.setdefault(key, (ref, []))
            if f.id not in fids:
                fids.append(f.id)
    return found


# ── facts ──────────────────────────────────────────────────────────────────


def _cut(s: pd.Series, day: date) -> pd.Series:
    s = s.dropna()
    return s[s.index < pd.Timestamp(day) + pd.Timedelta(days=1)]


def stock_fact(fid: str, ticker: str, name: str, s: pd.Series, day: date) -> Fact:
    s = _cut(s, day)
    if len(s) < 6:
        raise ValueError(f"only {len(s)} closes")
    last, end = float(s.iloc[-1]), s.index[-1]

    def chg(n: int) -> float | None:
        return round((last / float(s.iloc[-1 - n]) - 1) * 100, 2) if len(s) > n else None

    prior_year = s[s.index.year < end.year]
    ytd = round((last / float(prior_year.iloc[-1]) - 1) * 100, 2) if len(prior_year) else None
    year = s[s.index > end - pd.Timedelta(days=365)]
    hi, lo = round(float(year.max()), 2), round(float(year.min()), 2)
    below = round((1 - last / hi) * 100, 2)
    span = "since listing" if s.index[0] > end - pd.Timedelta(days=365) else "52-week"
    moves = [("1 week", chg(5)), ("1 month", chg(21)), ("3 months", chg(63)), ("year to date", ytd)]
    parts = [f"last close ${last:,.2f} ({end:%b %-d, %Y})"]
    parts += [f"{label} {v:+.2f}%" for label, v in moves if v is not None]
    parts.append(f"{span} high ${hi:,.2f}, low ${lo:,.2f}, {below:.2f}% below the high")
    return Fact(
        id=fid,
        text=f"Background, {name} ({ticker}) price history: " + "; ".join(parts),
        numbers=[round(last, 2), *(v for _, v in moves if v is not None), hi, lo, below],
        provenance="data",
        series=SeriesRef(kind="daily", provider="yahoo", id=ticker, label=name),
        source_title=f"Yahoo Finance {ticker}",
        source_url=f"https://finance.yahoo.com/quote/{ticker}",
    )


def _since(s: pd.Series, fmt: str, span: str) -> str:
    """'the highest since Jul 2026' / 'the lowest since …' for the last value of `s`."""
    last, prev = float(s.iloc[-1]), s.iloc[:-1]
    if prev.empty:
        return ""
    hi, lo = prev[prev > last], prev[prev < last]
    if hi.empty:
        return f"the highest {span}"
    if lo.empty:
        return f"the lowest {span}"
    if hi.index[-1] < lo.index[-1]:
        return f"the highest since {hi.index[-1]:{fmt}}"
    return f"the lowest since {lo.index[-1]:{fmt}}"


def _streak(vals: list[float]) -> tuple[int, str]:
    n, direction = 0, ""
    for a, b in zip(reversed(vals[:-1]), reversed(vals[1:]), strict=True):
        d = "rise" if b > a else "fall" if b < a else ""
        if not d or (direction and d != direction):
            break
        direction, n = d, n + 1
    return n, direction


def _transform(ref: SeriesRef) -> str:
    from castelino.agents.update.collector import RELEASES

    kinds = {name: kind for _, name, kind in RELEASES}
    if ref.label in kinds:
        return kinds[ref.label]
    return "yoy" if "y/y" in ref.label else "mom" if "m/m" in ref.label else "level"


def release_fact(fid: str, ref: SeriesRef, raw: pd.Series, day: date) -> Fact:
    kind = _transform(ref)
    s = raw.dropna()
    s = (
        (s.pct_change(12) * 100)
        if kind == "yoy"
        else (s.pct_change(1) * 100)
        if kind == "mom"
        else s
    )
    s = _cut(s.dropna(), day)
    if ref.points:  # never show a reading newer than the one the note reports (rebuilds)
        latest = re.match(r"([A-Z][a-z]{2} \d{4})", ref.points[-1].label)
        if latest:
            s = s[s.index <= pd.Timestamp(pd.to_datetime(latest.group(1), format="%b %Y"))]
    s = s.round(2)
    if len(s) < 3:
        raise ValueError(f"only {len(s)} readings")
    last12 = s.tail(READINGS)
    vals = [float(v) for v in last12]
    n, direction = _streak(vals)
    streak = f"the {_ordinal(n)} straight {direction}" if n >= 2 else ""
    since = _since(s, "%b %Y", "on record")
    tail = ", ".join(x for x in (streak, since) if x)
    readings = ", ".join(f"{i:%b %Y} {v:.2f}%" for i, v in last12.items())
    return Fact(
        id=fid,
        text=f"Background, {ref.label} history (FRED {ref.id}), last {len(vals)} readings: "
        f"{readings}. The latest, {vals[-1]:.2f}%, is {tail or 'unchanged'}.",
        numbers=vals,
        provenance="data",
        series=SeriesRef(
            kind="release",
            provider="fred",
            id=ref.id,
            label=ref.label,
            points=[Point(label=f"{i:%b %y}", value=float(v)) for i, v in last12.items()],
        ),
        source_title=f"FRED {ref.id}",
        source_url=f"https://fred.stlouisfed.org/series/{ref.id}",
    )


def daily_fact(fid: str, ref: SeriesRef, raw: pd.Series, day: date) -> Fact:
    s = _cut(raw, day)
    if len(s) < 25:
        raise ValueError(f"only {len(s)} observations")
    last, end = float(s.iloc[-1]), s.index[-1]
    rate = is_rate(ref.id)
    unit = "bp" if rate else "%"

    def chg(n: int) -> float | None:
        if len(s) <= n:
            return None
        a = float(s.iloc[-1 - n])
        return round((last - a) * 100, 0) if rate else round((last / a - 1) * 100, 2)

    m1, m3 = chg(21), chg(63)
    ten = s.tail(11).diff().dropna()
    ups = int((ten > 0).sum())
    since = _since(s.tail(260), "%b %-d, %Y", "in a year")
    level = f"{last:.2f}%" if rate else f"{last:,.2f}"
    moves = [
        f"{lab} {v:+g}{unit}" for lab, v in (("1 month", m1), ("3 months", m3)) if v is not None
    ]
    return Fact(
        id=fid,
        text=f"Background, {ref.label or ref.id} history (FRED {ref.id}): {level} on {end:%b %-d}; "
        f"{', '.join(moves)}; up on {ups} of the last {len(ten)} days; {since}.",
        numbers=[round(last, 2), *(v for v in (m1, m3) if v is not None)],
        provenance="data",
        series=SeriesRef(kind="daily", provider="fred", id=ref.id, label=ref.label or ref.id),
        source_title=f"FRED {ref.id}",
        source_url=f"https://fred.stlouisfed.org/series/{ref.id}",
    )


def _ordinal(n: int) -> str:
    return {2: "2nd", 3: "3rd"}.get(n, f"{n}th")


def _first_sentence(body: str) -> str:
    text = body.replace("**", "").strip()
    m = re.match(r"(.+?[.!?])(\s|$)", text, re.S)
    return (m.group(1) if m else text)[:400]


def note_facts(
    updates_dir: Path, day: date, subjects: dict[str, tuple[list[str], list[str]]], start: int
) -> tuple[list[Fact], dict[str, list[str]]]:
    """Earlier Morning Notes (newest first) whose items covered a subject. `subjects`: key →
    (texts to look for, series ids). Returns the facts and subject key → their fact ids."""
    facts: list[Fact] = []
    links: dict[str, list[str]] = {}  # subject key → note fact ids
    seen: dict[tuple[str, int], str] = {}
    for back in range(1, NOTE_DAYS + 1):
        d = day - timedelta(days=back)
        path = Path(updates_dir) / f"{d.isoformat()}.json"
        if not path.exists():
            continue
        try:
            rec = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if rec.get("version") != 2:
            continue
        rec_series = {f["id"]: (f.get("series") or {}).get("id") for f in rec.get("findings", [])}
        for it in rec.get("note", {}).get("items", []):
            text = f"{it.get('title', '')} {it.get('body', '')}"
            ids = {rec_series.get(fid) for fid in it.get("finding_ids", [])}
            for key, (needles, series_ids) in subjects.items():
                if len(links.get(key, [])) >= NOTES_PER_SUBJECT:
                    continue
                if not (any(_mentions(text, n) for n in needles) or ids & set(series_ids)):
                    continue
                slot = (d.isoformat(), it.get("rank", 0))
                if slot not in seen:
                    sentence = _first_sentence(it.get("body", ""))
                    fid = f"bg-n{start + len(facts)}"
                    seen[slot] = fid
                    facts.append(
                        Fact(
                            id=fid,
                            text=f"Background, ARC Morning Note {d:%b %-d, %Y}, item "
                            f'"{it.get("title", "")}": {sentence}',
                            numbers=[
                                float(m.group(1) + m.group(2)) for m in _FIG.finditer(sentence)
                            ],
                            provenance="reported",
                            source_title=f"ARC Morning Note {d:%b %-d}",
                            source_url=f"{SITE}/updates?date={d.isoformat()}",
                        )
                    )
                links.setdefault(key, []).append(seen[slot])
    return facts, links


# ── entry point ────────────────────────────────────────────────────────────


def enrich(
    findings: list[Finding],
    facts: list[Fact],
    day: str,
    updates_dir: Path,
    *,
    fetch_close: Callable[[str], pd.Series] = default_close,
    fetch_fred: Callable[[str], pd.Series] = default_fred,
    universe: list[tuple[str, str]] | None = None,
) -> tuple[list[Finding], list[Fact], list[str]]:
    """Findings with background fact ids linked, all facts, and data gaps."""
    d = date.fromisoformat(day)
    facts = [f for f in facts if not f.id.startswith("bg-")]
    findings = [
        f.model_copy(update={"fact_ids": [i for i in f.fact_ids if not i.startswith("bg-")]})
        for f in findings
    ]
    links: dict[str, list[str]] = {}  # finding id → background fact ids
    new: list[Fact] = []
    gaps: list[str] = []

    def link(fids: list[str], fact_id: str) -> None:
        for fid in fids:
            links.setdefault(fid, []).append(fact_id)

    stocks = stock_subjects(findings, facts, load_universe() if universe is None else universe)
    for ticker, (name, fids) in list(stocks.items())[:MAX_STOCKS]:
        try:
            fact = stock_fact(f"bg-s{len(new) + 1}", ticker, name, fetch_close(ticker), d)
        except Exception as exc:  # noqa: BLE001 — background is never load-bearing
            gaps.append(f"background: {ticker} price history unavailable ({exc})")
            continue
        new.append(fact)
        link(fids, fact.id)

    series = series_subjects(findings, facts)
    for _key, (ref, fids) in list(series.items())[:MAX_SERIES]:
        try:
            raw = fetch_fred(ref.id)
            fid = f"bg-d{len(new) + 1}"
            fact = (
                release_fact(fid, ref, raw, d)
                if ref.kind == "release"
                else daily_fact(fid, ref, raw, d)
            )
        except Exception as exc:  # noqa: BLE001
            gaps.append(f"background: {ref.id} history unavailable ({exc})")
            continue
        new.append(fact)
        link(fids, fact.id)

    subjects: dict[str, tuple[list[str], list[str]]] = {}
    owners: dict[str, list[str]] = {}
    for ticker, (name, fids) in list(stocks.items())[:MAX_STOCKS]:
        subjects[ticker] = ([n for n in (ticker, name) if len(n) >= 3], [ticker])
        owners[ticker] = fids
    for key, (ref, fids) in list(series.items())[:MAX_SERIES]:
        subjects[key] = ([ref.label] if ref.label else [], [ref.id])
        owners[key] = fids
    notes, note_links = note_facts(updates_dir, d, subjects, start=len(new) + 1)
    new += notes
    for key, ids in note_links.items():
        for fact_id in ids:
            link(owners[key], fact_id)

    findings = [
        f.model_copy(update={"fact_ids": f.fact_ids + list(dict.fromkeys(links.get(f.id, [])))})
        for f in findings
    ]
    return findings, facts + new, gaps
