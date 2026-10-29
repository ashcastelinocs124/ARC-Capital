"""Builds data/dashboards/ai_capex.json, the AI Demand & Capex dashboard's one file.

Each lane runs on its own: a failed lane keeps the previous file's value and logs a gap (URL query
strings stripped: a FRED error carries its API key). If every lane fails the run raises and the old file
stays. Paid reads (the release and cited readers) run only when a company files something new, plus a
weekly pass from each Sunday for neocloud delays and private power; everything else is free."""

from __future__ import annotations

import csv
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from castelino.dashboards.ai_capex import adoption, census, cited, gpu, market, releases, xbrl
from castelino.dashboards.ai_capex.companies import COMPANIES, DASHBOARD_TICKERS, PRIVATE

log = logging.getLogger(__name__)
NY = ZoneInfo("America/New_York")
QS = re.compile(r"\?\S*")

CLOUD = {  # ticker -> (cloud name, revenue KPI, growth KPI)
    "MSFT": ("Azure", None, "Azure and other cloud services revenue growth %"),
    "GOOGL": ("Google Cloud", "Google Cloud revenue", "Google Cloud revenue growth %"),
    "AMZN": ("AWS", "AWS segment net sales", "AWS net sales growth %"),
    "ORCL": ("Oracle Cloud Infrastructure", None, "cloud infrastructure revenue growth %"),
}
BACKLOG = {  # ticker -> (label, release KPI; None = from a cited search)
    "MSFT": ("Commercial RPO", "commercial remaining performance obligation"),
    "GOOGL": ("Google Cloud backlog", None),
    "AMZN": ("AWS backlog", None),
    "ORCL": ("Total RPO", "remaining performance obligations"),
    "CRWV": ("Revenue backlog", "revenue backlog"),
    # not IREN: its release's "contracted AI cloud revenue" is an annual run rate, not backlog, so
    # its backlog is the filings' remaining performance obligations
}
POWER = {  # ticker -> (online KPI, contracted KPI)
    "CRWV": ("active power", "contracted power"),
    "NBIS": ("active power", "contracted power"),
    "IREN": ("operating AI cloud capacity", "secured power"),
}


def _root() -> Path:
    from castelino.config import get_settings

    return get_settings().root


def out_path() -> Path:
    return _root() / "data" / "dashboards" / "ai_capex.json"


def cache_dir() -> Path:
    return _root() / "data" / "dashboards" / "ai_capex"


def _edgar():
    from castelino.adoption.sources.edgar import EdgarClient
    from castelino.config import get_settings

    return EdgarClient(get_settings().adoption.sec_user_agent)


def _store():
    from castelino.adoption.store import AdoptionStore

    return AdoptionStore()


def _names() -> dict[str, str]:
    p = _root() / "data" / "adoption" / "universe.csv"
    if not p.exists():
        return {}
    with p.open() as f:
        return {r["ticker"]: r.get("name") or r["ticker"] for r in csv.DictReader(f)}


def _httpx_get(*a, **k):
    import httpx

    return httpx.get(*a, **k)


@dataclass
class Deps:
    """Everything the run reaches out to, so tests can swap in fakes."""

    edgar: Any = None
    search: Callable | None = None  # cited web search (system, user) -> (text, cites)
    release_reader: type = releases.KpiReader
    cited_reader: type = cited.CitedReader
    fetch_fred: Callable = market.spend.default_fred
    ramp_rows: Callable = market.sources.ramp_rows
    get_text: Callable = market.spend.get_text
    census_get: Callable = _httpx_get
    adoption_store: Any = None
    names: dict | None = None
    extra: dict = field(default_factory=dict)


# ── small helpers ────────────────────────────────────────────────────────────


def _bn(v: float | None, unit: str) -> float | None:
    if v is None:
        return None
    return {"billions": v, "millions": v / 1000}.get(unit)


def _gw(v: float | None, unit: str) -> float | None:
    if v is None:
        return None
    return {"gigawatts": v, "megawatts": v / 1000}.get(unit)


def _kpi(rel: dict | None, name: str | None) -> dict | None:
    return (rel or {}).get("kpis", {}).get(name) if name else None


def _rel_label(filed: str) -> str:
    """A release's quarter: results come out 3-8 weeks after the quarter ends (Nvidia ~4, Nebius ~6),
    so 70 days before the filing lands inside the quarter reported."""
    d = date.fromisoformat(filed) - timedelta(days=70)
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


_SPREAD = re.compile(r"spread|margin", re.I)  # a SOFR spread is not a rate: 0.44% would read as one


_YEAR = re.compile(r"FY\s?'?(\d{2,4})\b|\b(20\d\d)\b", re.I)


def _fresh(items: list[dict], since: str, days: int = 100) -> list[dict]:
    """Cited items dated within `days` before `since` (a quarter end) or later. A cited line can be
    years old under "latest" (Google Cloud's June 2025 backlog came back in Oct 2026); its own date,
    which the search must give, is the only check. An undated line is dropped."""
    cut = (date.fromisoformat(since[:10]) - timedelta(days=days)).isoformat()[:7]
    return [i for i in items if (i.get("date") or "")[:7] >= cut and i.get("date")]


def _quoted(line: str) -> str | None:
    """The company's own words in a cited line: the search model's prose around them never reaches
    the page (no model-written text on the dashboard)."""
    m = re.search(r"[“\"]([^”\"]{12,240})[”\"]", line)
    return m.group(1).strip() if m else None


def _in_year(label: str, fy: int, fy_end: int) -> bool:
    """Does quarter `label` ("2026Q3") fall in fiscal year `fy` ending in month `fy_end`?"""
    y, mid = int(label[:4]), (int(label[5]) - 1) * 3 + 2  # the quarter's middle month
    return (y == fy - 1 and mid > fy_end) or (y == fy and mid <= fy_end) if fy_end < 12 else y == fy


def _guidance(
    items: list[dict], quarters: list[dict], year: int | None = None, fy_end: int = 12
) -> dict | None:
    """The newest full-year guidance. Guidance for a year that has ended is dropped, and so is
    guidance that would leave the rest of its year at under half the latest quarter's pace: a search's
    old line under a new date (Alphabet's 2025 "$91-93bn" came back as 2026's after $80.6bn was spent
    in the first half; Oracle's "$35bn for fiscal 2027" after $28.5bn in its first quarter).
    Conservative: the filings' capex excludes finance leases, which some guidance includes."""
    guides = sorted(
        (i for i in items if "guidance" in i["label"].lower()), key=lambda i: i["date"] or ""
    )
    if not guides:
        return None
    guide = guides[-1]  # the newest line, whatever order the reader returned
    actual = next((i for i in items if i["label"].lower() == "actual"), None)
    low, high = (
        _bn(guide["value"], guide["unit"]),
        _bn(guide["value_high"] or guide["value"], guide["unit"]),
    )
    fiscal = bool(re.search(r"fiscal|\bFY", guide["period"], re.I)) and fy_end < 12
    if m := _YEAR.search(guide["period"]):
        fy = int(m.group(1) or m.group(2))
        fy = fy + 2000 if fy < 100 else fy
        end, today = (fy_end if fiscal else 12), date.today()
        ended = (fy, end) < (today.year, today.month) if fiscal else fy < (year or today.year)
        if ended:
            return None  # that year is over: not guidance any more
        done = [q for q in quarters if q["capex"] is not None and _in_year(q["q"], fy, end)]
        if high is not None and done:
            floor = sum(q["capex"] for q in done) + (4 - len(done)) * done[-1]["capex"] * 0.5
            if high < floor:
                return None
    return {
        "low": low,
        "high": high,
        "label": guide["period"],
        "actual": _bn(actual["value"], actual["unit"]) if actual else None,
        "actual_label": actual["period"] if actual else None,
        "line": guide["source"]["line"] if guide["value"] is None else None,
        "source": _src(guide),
    }  # fmt: skip


def _borrowing(items: list[dict]) -> list[dict]:
    return [
        {"label": i["label"], "rate_pct": i["value"], "date": i["date"], "source": _src(i)}
        for i in items
        if i["unit"] == "percent" and i["value"] is not None and not _SPREAD.search(i["label"])
    ][:3]


def _off_balance(items: list[dict]) -> list[dict]:
    """One tile per kind (its newest figure), $1bn or more, at most two per company."""
    newest: dict[str, dict] = {}
    for i in sorted(items, key=lambda i: i.get("date") or ""):
        v = _bn(i["value"], i["unit"]) if i["value"] is not None else None
        if v is not None and v >= 1:
            newest[i["label"].lower()] = {"label": i["label"], "value": v, "source": _src(i)}
    return sorted(newest.values(), key=lambda o: -o["value"])[:2]


def _year_before(label: str) -> str:
    return f"{int(label[:4]) - 1}{label[4:]}"


def _src(item: dict) -> dict:
    return {"title": item["source"]["title"], "url": item["source"]["url"]}


def _usd(v: float) -> str:
    if v >= 1000:
        return f"${v / 1000:.2f}tn"
    return f"${v:.1f}bn" if v < 10 else f"${v:.0f}bn"


def _qname(label: str) -> str:
    return f"Q{label[5]} {label[:4]}"


def _week_key(today: date) -> str:
    """The ISO week of the latest Sunday: a new key (so new searches) only from each Sunday."""
    sunday = today - timedelta(days=(today.weekday() + 1) % 7)
    y, w, _ = sunday.isocalendar()
    return f"{y}-W{w:02d}"


# ── one company ──────────────────────────────────────────────────────────────


def _company(co, d: Deps, edgar, cache: Path, week: str, year: int) -> dict:
    t = co.ticker
    rels = edgar.earnings_releases(t, 5)
    filing = edgar.latest_filing(t) if co.xbrl else None
    key = "_".join(a for a in (getattr(filing, "accession", None), rels[0].accession if rels else None) if a) or "none"  # fmt: skip

    def read(r):
        return releases.read_release(t, r, edgar, cache, reader=d.release_reader)

    wanted = t in releases.WANTED  # Meta: no cloud, nothing a release adds
    now = read(rels[0]) if rels and wanted else None
    ago = read(rels[4]) if len(rels) >= 5 and wanted else None

    def topic(name: str, k: str = key) -> list[dict]:
        return cited.cited_items(co.name, t, name, k, cache, search=d.search, reader=d.cited_reader, year=year)  # fmt: skip

    if co.xbrl:
        f = xbrl.fundamentals(edgar.company_facts(t) or {})
    else:
        f = _from_releases([read(r) for r in rels])
    out: dict = {
        "ticker": t,
        "name": co.name,
        "kind": co.kind,
        "quarters": f.quarters,
        "ttm": f.ttm,
        "mix": f.mix,
        "cents_per_dollar": f.cents_per_dollar,
        "cents_year_ago": f.cents_year_ago,
        "ocf_share": f.ocf_share,
        "avg_rate": f.avg_rate,
        "yoy_pct": f.yoy_pct,
        "as_of": f.as_of,
        "cloud": None,
        "backlog": None,
        "power": None,
        "sources": {
            "xbrl": {"title": "SEC filings", "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={t}&type=10-Q"},
            "release": {"title": f"{co.name} earnings release", "url": rels[0].url} if rels else None,
        },
    }  # fmt: skip
    if t in CLOUD:
        name, rev, growth = CLOUD[t]
        g, r = _kpi(now, growth), _kpi(now, rev)
        out["cloud"] = {
            "name": name,
            "growth_pct": g["value"] if g else None,
            "revenue": _bn(r["value"], r["unit"]) if r else None,
        }
    # a cited line is kept only if dated near the company's latest quarter (see _fresh)
    as_of = f.as_of or date.today().isoformat()
    year_ago = date.today() - timedelta(days=365)
    label, kname = BACKLOG.get(t, ("Remaining performance obligations", ""))
    val = val0 = None
    if kname:
        k, k0 = _kpi(now, kname), _kpi(ago, kname)
        val = _bn(k["value"], k["unit"]) if k else None
        val0 = _bn(k0["value"], k0["unit"]) if k0 else None
    elif kname is None:
        items = topic("backlog")
        # the current figure must be recent; the year-ago one is old by definition
        cur = next((i for i in _fresh(items, as_of) if i["label"] == "backlog"), None)
        old = next((i for i in items if "year ago" in i["label"]), None)
        val = _bn(cur["value"], cur["unit"]) if cur else None
        val0 = _bn(old["value"], old["unit"]) if old and cur else None
    if val is None and f.rpo is not None:  # the filings' own figure, dated by the filing
        label, val, val0 = "Remaining performance obligations", f.rpo, None
    out["backlog"] = {"label": label, "value": val, "year_ago": val0} if val is not None else None
    if co.kind == "neocloud":
        on, con = POWER.get(t, (None, None))
        a, c = _kpi(now, on), _kpi(now, con)
        power = {
            "online_gw": _gw(a["value"], a["unit"]) if a else None,
            "contracted_gw": _gw(c["value"], c["unit"]) if c else None,
        }
        if power["online_gw"] is None or power["contracted_gw"] is None:
            power = _power(_fresh(topic("power", week), as_of)) or power
        out["power"] = power
        out["events"] = [
            {"date": i["date"], "text": _quoted(i["source"]["line"]), "source": _src(i)}
            for i in _fresh(topic("delays", week), year_ago.isoformat(), days=0)
        ][:3]
    out["guidance"] = _guidance(
        _fresh(topic("guidance"), year_ago.isoformat(), days=0), f.quarters, year, co.fy_end
    )
    out["borrowing"] = _borrowing(
        [i for i in topic("borrowing") if (i.get("date") or "").startswith(str(year))]
    )
    out["off_balance"] = _off_balance(_fresh(topic("off_balance"), as_of))
    return out


_ONLINE = re.compile(r"online|active|operat|energi[sz]ed|\blive\b|in service", re.I)
_CONTRACTED = re.compile(r"contract|secured|signed|committed", re.I)


def _power(items: list[dict]) -> dict | None:
    con = next((i for i in items if _CONTRACTED.search(i["label"])), None)
    on = next((i for i in items if _ONLINE.search(i["label"]) and i is not con), None)
    if not (on and con):
        return None
    return {
        "online_gw": _gw(on["value"], on["unit"]),
        "contracted_gw": _gw(con["value"], con["unit"]),
    }


def _from_releases(rels: list[dict]) -> xbrl.Fundamentals:
    """Nebius files no quarterly XBRL: its quarters from its 6-K releases, newest first in `rels`."""
    qs = []
    for r in reversed(rels):
        cap, rev, ocf = (_kpi(r, n) for n in ("capital expenditures", "revenue", "net cash from operating activities"))  # fmt: skip
        qs.append(
            {
                "q": _rel_label(r["filed"]),
                "end": None,
                "capex": abs(_bn(cap["value"], cap["unit"])) if cap and _bn(cap["value"], cap["unit"]) is not None else None,
                "revenue": _bn(rev["value"], rev["unit"]) if rev else None,
                "ocf": _bn(ocf["value"], ocf["unit"]) if ocf else None,
                "_r": r,
            }
        )  # fmt: skip
    if not qs:
        return xbrl.Fundamentals()
    last, last4 = qs[-1], qs[-4:]
    year_ago = qs[-5] if len(qs) >= 5 else None

    def cents(q):
        return round(q["capex"] / q["revenue"] * 100) if q and q["capex"] and q["revenue"] else None

    def sum4(k):
        vals = [q[k] for q in last4]
        return sum(vals) if len(vals) == 4 and None not in vals else None

    def kpi_sum(name):
        vals = [_kpi(q["_r"], name) for q in last4]
        return sum(_bn(v["value"], v["unit"]) or 0 for v in vals if v)

    capex, ocf = sum4("capex"), sum4("ocf")
    mix = None
    if capex is not None and ocf is not None:
        parts = {
            "own_cash": max(0.0, ocf),
            "debt": max(
                0.0, kpi_sum("proceeds from borrowings") - kpi_sum("repayments of borrowings")
            ),
            "convertible": max(0.0, kpi_sum("proceeds from convertible notes")),
            "shares": max(0.0, kpi_sum("proceeds from issuance of shares")),
            "cash_on_hand": 0.0,
        }
        mix = xbrl._largest_remainder(parts)
    for q in qs:
        q.pop("_r")
    return xbrl.Fundamentals(
        quarters=[{k: (round(v, 2) if isinstance(v, float) else v) for k, v in q.items()} for q in qs],
        ttm={"capex": capex, "ocf": ocf, "revenue": sum4("revenue")},
        mix=mix,
        cents_per_dollar=cents(last),
        cents_year_ago=cents(year_ago),
        ocf_share=round(capex / ocf * 100) if capex is not None and ocf and ocf > 0 else None,
        yoy_pct=round((last["capex"] / year_ago["capex"] - 1) * 100) if year_ago and year_ago["capex"] and last["capex"] else None,
        as_of=rels[0]["filed"] if rels else None,
    )  # fmt: skip


# ── totals and sentences ─────────────────────────────────────────────────────


def totals(companies: list[dict]) -> dict:
    hyp = [c for c in companies if c["kind"] == "hyperscaler"]
    neo = [c for c in companies if c["kind"] == "neocloud"]
    by: dict[str, list[float]] = {}
    for c in hyp:
        for q in c["quarters"]:
            if q.get("capex") is not None:
                by.setdefault(q["q"], []).append(q["capex"])
    labels = sorted(by)[-10:]
    tq = [
        {"q": lab, "capex": round(sum(by[lab]), 1), "reported": len(by[lab]), "of": len(hyp)}
        for lab in labels
    ]
    full = {t["q"]: t["capex"] for t in tq if t["reported"] == t["of"]}
    out: dict = {"quarters": tq}
    if full:
        last = max(full)
        if (prev := _year_before(last)) in full:
            out["yoy_pct"] = round((full[last] / full[prev] - 1) * 100)
        last4 = sorted(full)[-4:]
        if len(last4) == 4:
            out["ttm_capex"] = round(sum(full[q] for q in last4), 1)
            before = [_year_before(q) for q in last4]
            if all(q in full for q in before):
                out["ttm_yoy_pct"] = round(
                    (out["ttm_capex"] / sum(full[q] for q in before) - 1) * 100
                )
    bl = [c["backlog"] for c in hyp if c.get("backlog")]
    if bl:
        out["backlog"] = round(sum(b["value"] for b in bl), 1)
        both = [b for b in bl if b.get("year_ago")]
        if both:
            out["backlog_growth_pct"] = round((sum(b["value"] for b in both) / sum(b["year_ago"] for b in both) - 1) * 100)  # fmt: skip
    nq = [
        c["quarters"][-1]["capex"]
        for c in neo
        if c["quarters"] and c["quarters"][-1].get("capex") is not None
    ]
    if nq:
        out["neocloud_capex_q"] = round(sum(nq), 1)
    return out


def sentences(doc: dict) -> dict[str, str]:
    """One or two plain sentences per section, from the numbers alone (no model)."""
    out: dict[str, str] = {}
    cos, tot = doc.get("companies") or [], doc.get("totals") or {}
    hyp = [c for c in cos if c["kind"] == "hyperscaler"]
    neo = [c for c in cos if c["kind"] == "neocloud"]
    full = [q for q in tot.get("quarters", []) if q["reported"] == q["of"]]
    if full and tot.get("yoy_pct") is not None:
        q = full[-1]
        s = f"The five spent **{_usd(q['capex'])}** in {_qname(q['q'])}, up {tot['yoy_pct']}% from a year ago"
        s += (
            f", and **{_usd(tot['ttm_capex'])}** over the last four quarters."
            if tot.get("ttm_capex")
            else "."
        )
        # every company compared in the quarter the sentence names, not each one's own newest
        at = {c["name"]: {x["q"]: x.get("capex") for x in c["quarters"]} for c in hyp}
        spend = {n: v[q["q"]] for n, v in at.items() if v.get(q["q"]) is not None}
        growth = {
            n: round((spend[n] / v[_year_before(q["q"])] - 1) * 100)
            for n, v in at.items()
            if n in spend and v.get(_year_before(q["q"]))
        }
        if spend:
            top = max(spend, key=spend.get)
            s += f" {top} spends the most"
            if growth and (fast := max(growth, key=growth.get)) != top:
                s += f"; {fast}'s spending is growing fastest: up {growth[fast]}%."
            elif growth:
                s += f" and is growing fastest: up {growth[top]}%."
            else:
                s += "."
        if tot.get("neocloud_capex_q"):
            s += f" The three neoclouds add {_usd(tot['neocloud_capex_q'])} a quarter."
        out["spending"] = s
    mixed = [c for c in cos if c.get("mix")]
    if mixed:
        # the mix is each source's share of all the cash coming in, not of capex: say so
        own = max(mixed, key=lambda c: c["mix"]["own_cash"])
        parts = [
            f"Over the last four quarters, {own['mix']['own_cash']}% of the cash coming into "
            f"{own['name']} came from its own business."
        ]
        for group in (hyp, neo):
            lend = [
                c for c in group if c.get("mix") and c["mix"]["debt"] + c["mix"]["convertible"] > 0
            ]
            if not lend:
                continue
            b = max(lend, key=lambda c: c["mix"]["debt"] + c["mix"]["convertible"])
            share = b["mix"]["debt"] + b["mix"]["convertible"]
            what = "New debt" if not b["mix"]["convertible"] else "New debt and convertible notes"
            p = f"{what} was **{share}%** of the cash coming into {b['name']} over the last four quarters"
            # bonds and loans only: a convertible's coupon is low because it can turn into shares
            rates = [
                d["rate_pct"]
                for d in b.get("borrowing") or []
                if "convertible" not in d["label"].lower()
            ]
            if rates:
                lo, hi = min(rates), max(rates)
                span = f"{lo:g}%" if lo == hi else f"{lo:g}–{hi:g}%"
                p += f"; its new bonds and loans this year pay **{span}**"
            parts.append(p + ".")
        out["funding"] = " ".join(parts)
    if tot.get("backlog"):
        s = f"Contracted backlog reached **{_usd(tot['backlog'])}**"
        s += (
            f", up {tot['backlog_growth_pct']}% from a year ago."
            if tot.get("backlog_growth_pct") is not None
            else "."
        )
        growth = [
            c["cloud"]["growth_pct"]
            for c in hyp
            if c.get("cloud") and c["cloud"].get("growth_pct") is not None
        ]
        if growth:
            s += f" Cloud revenue is growing {min(growth):g}–{max(growth):g}%."
        out["demand"] = s
    powered = [
        c
        for c in neo
        if c.get("power") and c["power"].get("online_gw") and c["power"].get("contracted_gw")
    ]
    if powered:
        on = sum(c["power"]["online_gw"] for c in powered)
        con = sum(c["power"]["contracted_gw"] for c in powered)
        names = [
            c["name"] for c in powered
        ]  # only those with figures: never "the neoclouds" for one
        who = (
            names[0] + " has"
            if len(names) == 1
            else ", ".join(names[:-1]) + f" and {names[-1]} have"
        )
        s = f"{who} **{on:.1f} GW** running against **{con:.1f} GW** contracted, so {round(on / con * 100)}% is online."
        yrs = [(c["backlog"]["value"] / c["ttm"]["revenue"], c["name"]) for c in neo
               if c.get("backlog") and (c.get("ttm") or {}).get("revenue")]  # fmt: skip
        if yrs:
            y, name = max(yrs)
            s += f" {name}'s backlog would take **{y:.1f} years** to deliver at today's revenue."
        out["compute"] = s
    return out


# ── the run ──────────────────────────────────────────────────────────────────


def run(now: datetime | None = None, *, out: Path | None = None, deps: Deps | None = None) -> str:
    import json

    from castelino.week_ahead.run import _write

    now = now or datetime.now(UTC)
    out = out or out_path()
    cache = out.parent / "ai_capex"
    d = deps or Deps()
    edgar = d.edgar or _edgar()
    today = now.astimezone(NY).date()
    week = _week_key(today)
    prev = json.loads(out.read_text()) if out.exists() else {}
    prev_cos = {c["ticker"]: c for c in prev.get("companies") or []}
    gaps: list[dict] = []
    lanes = failed = 0

    def lane(name: str, fn, fallback):
        nonlocal lanes, failed
        lanes += 1
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 - one lane never blanks the page
            failed += 1
            msg = QS.sub("", str(e))[:200]
            log.warning("ai_capex %s failed: %s", name, msg)
            gaps.append({"lane": name, "error": msg})
            return fallback

    companies = [
        c
        for co in COMPANIES
        if (c := lane(f"company:{co.ticker}", lambda co=co: _company(co, d, edgar, cache, week, today.year), prev_cos.get(co.ticker)))
    ]  # fmt: skip

    def private():
        rows = []
        for name in PRIVATE:
            items = _fresh(
                cited.cited_items(name, name, "power", week, cache, search=d.search, reader=d.cited_reader),
                today.isoformat(),
                days=200,  # private companies report no quarters: six months or so
            )  # fmt: skip
            if p := _power(items):
                rows.append({"name": name, **p, "source": _src(items[0])})
        return rows

    def nvidia():
        rels = edgar.earnings_releases("NVDA", 9)
        read = [
            releases.read_release("NVDA", r, edgar, cache, reader=d.release_reader) for r in rels
        ]
        qs = [
            {"q": _rel_label(r["filed"]), "value": _bn(k["value"], k["unit"])}
            for r in reversed(read)
            if (k := _kpi(r, "Data Center revenue"))
        ]
        g = _kpi(read[0], "Data Center revenue growth %") if read else None
        src = {"title": "Nvidia earnings release", "url": read[0]["url"]} if read else None
        return {"quarters": qs, "growth_pct": g["value"] if g else None, "source": src}

    doc = {
        "generated_at": datetime.now(UTC).isoformat(),
        "as_of": today.isoformat(),
        "companies": companies,
        "private": lane("private", private, prev.get("private") or []),
        "nvidia": lane("nvidia", nvidia, prev.get("nvidia")),
        "rates": lane("rates", lambda: market.rates(d.fetch_fred), prev.get("rates")),
        "ramp": lane("ramp", lambda: market.ramp(d.ramp_rows), prev.get("ramp")),
        "openrouter": lane("openrouter", lambda: market.openrouter(d.get_text), prev.get("openrouter")),
        "census": lane("census", lambda: census.fetch(d.census_get), prev.get("census")),
        # no fallback: a failed read is "unavailable", never yesterday's prices under today's date
        "gpu": lane("gpu", lambda: gpu.lane(cache / "gpu_prices.jsonl", d.get_text, today), None),
        "adoption": lane(
            "adoption",
            # Nvidia too: it sells the chips (it has its own tile), so it isn't adoption beyond the buyers
            lambda: adoption.talk_slice(d.adoption_store or _store(), DASHBOARD_TICKERS | {"NVDA"}, d.names if d.names is not None else _names()),
            prev.get("adoption"),
        ),
    }  # fmt: skip
    if failed == lanes:
        raise RuntimeError("ai_capex: every lane failed; previous file kept")
    doc["totals"] = totals(companies)
    doc["sentences"] = sentences(doc)
    try:  # the link card; without it a shared link shows the plain page, never a failed run
        from castelino.dashboards.ai_capex import card

        card.draw(doc, cache / "card.png")
    except Exception as e:  # noqa: BLE001
        gaps.append({"lane": "card", "error": QS.sub("", str(e))[:200]})
    doc["gaps"] = gaps
    _write(out, doc)
    return f"{len(companies)} companies; {len(gaps)} gaps"
