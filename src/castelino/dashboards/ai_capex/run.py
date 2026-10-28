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
    "IREN": ("Contracted AI cloud revenue", "contracted AI cloud revenue"),
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
    """A release's quarter: results come out within about six weeks of the quarter's end."""
    d = date.fromisoformat(filed) - timedelta(days=45)
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


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
    if t in BACKLOG:
        label, kname = BACKLOG[t]
        if kname:
            k, k0 = _kpi(now, kname), _kpi(ago, kname)
            val = _bn(k["value"], k["unit"]) if k else None
            val0 = _bn(k0["value"], k0["unit"]) if k0 else None
        else:
            items = topic("backlog")
            cur = next((i for i in items if i["label"] == "backlog"), None)
            old = next((i for i in items if "year ago" in i["label"]), None)
            val = _bn(cur["value"], cur["unit"]) if cur else None
            val0 = _bn(old["value"], old["unit"]) if old else None
        if val is None and f.rpo is not None:
            label, val = "Remaining performance obligations", f.rpo
        out["backlog"] = (
            {"label": label, "value": val, "year_ago": val0} if val is not None else None
        )
    if co.kind == "neocloud":
        on, con = POWER.get(t, (None, None))
        a, c = _kpi(now, on), _kpi(now, con)
        power = {
            "online_gw": _gw(a["value"], a["unit"]) if a else None,
            "contracted_gw": _gw(c["value"], c["unit"]) if c else None,
        }
        if power["online_gw"] is None or power["contracted_gw"] is None:
            power = _power(topic("power", week)) or power
        out["power"] = power
        out["events"] = [
            {"date": i["date"], "text": i["source"]["line"], "source": _src(i)}
            for i in topic("delays", week)
        ][:3]
    g = topic("guidance")
    guide = next((i for i in g if "guidance" in i["label"].lower()), None)
    actual = next((i for i in g if i["label"].lower() == "actual"), None)
    out["guidance"] = (
        {
            "low": _bn(guide["value"], guide["unit"]),
            "high": _bn(guide["value_high"] or guide["value"], guide["unit"]),
            "label": guide["period"],
            "actual": _bn(actual["value"], actual["unit"]) if actual else None,
            "actual_label": actual["period"] if actual else None,
            "line": guide["source"]["line"] if guide["value"] is None else None,
            "source": _src(guide),
        }
        if guide
        else None
    )
    out["borrowing"] = [
        {"label": i["label"], "rate_pct": i["value"], "date": i["date"], "source": _src(i)}
        for i in topic("borrowing")
        if i["unit"] == "percent" and i["value"] is not None
    ][:4]
    out["off_balance"] = [
        {"label": i["label"], "value": _bn(i["value"], i["unit"]), "source": _src(i)}
        for i in topic("off_balance")
        if i["value"] is not None and i["unit"] in ("billions", "millions")
    ][:3]
    return out


def _power(items: list[dict]) -> dict | None:
    on = next((i for i in items if "online" in i["label"]), None)
    con = next((i for i in items if "contracted" in i["label"]), None)
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
        latest = [c for c in hyp if c["quarters"] and c["quarters"][-1].get("capex") is not None]
        if latest:
            top = max(latest, key=lambda c: c["quarters"][-1]["capex"])
            fast = max(
                (c for c in hyp if c.get("yoy_pct") is not None),
                key=lambda c: c["yoy_pct"],
                default=None,
            )
            s += f" {top['name']} spends the most"
            s += (
                f"; {fast['name']}'s spending is growing fastest: up {fast['yoy_pct']}%."
                if fast and fast is not top
                else "."
            )
        if tot.get("neocloud_capex_q"):
            s += f" The three neoclouds add {_usd(tot['neocloud_capex_q'])} a quarter."
        out["spending"] = s
    mixed = [c for c in cos if c.get("mix")]
    if mixed:
        own = max(mixed, key=lambda c: c["mix"]["own_cash"])
        parts = [
            f"{own['name']} pays for {own['mix']['own_cash']}% of its capex from its own cash."
        ]
        ty = (doc.get("rates") or {}).get("treasury_10y", {}).get("value")
        for group in (hyp, neo):
            lend = [
                c for c in group if c.get("mix") and c["mix"]["debt"] + c["mix"]["convertible"] > 0
            ]
            if not lend:
                continue
            b = max(lend, key=lambda c: c["mix"]["debt"] + c["mix"]["convertible"])
            share = b["mix"]["debt"] + b["mix"]["convertible"]
            p = f"{b['name']} borrows **{share}%** of it"
            if b.get("borrowing"):
                r = b["borrowing"][0]["rate_pct"]
                p += f", and its newest borrowing pays **{r}%**"
                if ty is not None:
                    p += f", {round((r - ty) * 100)}bp over Treasuries"
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
        c["power"]
        for c in neo
        if c.get("power") and c["power"].get("online_gw") and c["power"].get("contracted_gw")
    ]
    if powered:
        on, con = sum(p["online_gw"] for p in powered), sum(p["contracted_gw"] for p in powered)
        s = f"The listed neoclouds have **{on:.1f} GW** running against **{con:.1f} GW** contracted, so {round(on / con * 100)}% is online."
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
            items = cited.cited_items(
                name, name, "power", week, cache, search=d.search, reader=d.cited_reader
            )
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
        "gpu": lane("gpu", lambda: gpu.lane(cache / "gpu_prices.jsonl", d.get_text, today), prev.get("gpu")),
        "adoption": lane(
            "adoption",
            lambda: adoption.talk_slice(d.adoption_store or _store(), DASHBOARD_TICKERS, d.names if d.names is not None else _names()),
            prev.get("adoption"),
        ),
    }  # fmt: skip
    if failed == lanes:
        raise RuntimeError("ai_capex: every lane failed; previous file kept")
    doc["totals"] = totals(companies)
    doc["sentences"] = sentences(doc)
    doc["gaps"] = gaps
    _write(out, doc)
    return f"{len(companies)} companies; {len(gaps)} gaps"
