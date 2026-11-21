"""Macro agent: code gathers FRED / BLS / Yahoo facts, gpt-6-luna picks the findings."""

from __future__ import annotations

import logging
from datetime import date, timedelta

from castelino.agents.base import StructuredAgent
from castelino.agents.update import bls
from castelino.agents.update.collector import (
    PLAIN_NAMES,
    asset_groups,
    collect,
    default_fetch_monthly,
)
from castelino.agents.update.facts import PICKER_RULES, drafts_prompt, to_findings
from castelino.agents.update.models import (
    AgentOutput,
    Fact,
    FindingDrafts,
    MarketSnapshot,
    Point,
    SeriesRef,
)
from castelino.config import get_settings
from castelino.data.instruments import PriceSource

log = logging.getLogger(__name__)

SYSTEM = f"""You are the macro analyst on ARC Research's morning desk.
You get today's US economic releases (FRED, BLS), Treasury yields and moves in equities, sectors,
commodities, credit and FX, each as a numbered fact. Find what changed and why it matters.
{PICKER_RULES}"""


def release_facts(snap: MarketSnapshot, keep: set[str] | None = None) -> list[Fact]:
    out: list[Fact] = []
    for r in snap.releases:
        if keep is not None and r.series not in keep:
            continue
        prior = f", prior {r.prior:.2f}% ({r.prior_period})" if r.prior is not None else ""
        change = f", change {r.change:+.2f}pp" if r.change is not None else ""
        series = None
        if r.prior is not None:
            series = SeriesRef(
                kind="release",
                provider="fred",
                id=r.series,
                label=r.name,
                points=[
                    Point(label=f"{r.prior_period} data", value=r.prior),
                    Point(label=f"{r.latest_period} data", value=r.latest),
                ],
            )
        out.append(
            Fact(
                id=f"M{len(out) + 1}",
                text=f"{r.name}: {r.latest:.2f}% ({r.latest_period}){prior}{change}",
                numbers=[x for x in (r.latest, r.prior, r.change) if x is not None],
                provenance="data",
                series=series,
                source_title=f"FRED {r.series}",
                source_url=f"https://fred.stlouisfed.org/series/{r.series}",
            )
        )
    return out


def market_facts(snap: MarketSnapshot, start: int) -> list[Fact]:
    insts = {i.instrument_id: i for group in asset_groups().values() for i in group}
    out: list[Fact] = []
    for cls, rows in snap.asset_returns.items():
        for iid, w in rows.items():
            inst = insts.get(iid)
            if inst is None:
                continue
            fred = inst.source == PriceSource.FRED
            unit = "bp" if fred else "%"
            parts = [f"{k} {v:+.2f}{unit}" for k, v in w.items() if v is not None]
            if not parts:
                continue
            name = PLAIN_NAMES.get(iid, iid)
            out.append(
                Fact(
                    id=f"M{start + len(out)}",
                    text=f"{name} ({cls}): " + ", ".join(parts),
                    numbers=[v for v in w.values() if v is not None],
                    provenance="data",
                    series=SeriesRef(
                        kind="daily",
                        provider="fred" if fred else "yahoo",
                        id=inst.symbol,
                        label=name,
                    ),
                    # chart footers print this, so a fund's ticker stays out of it too
                    source_title="Yahoo Finance"
                    if iid in PLAIN_NAMES
                    else f"{'FRED' if fred else 'Yahoo Finance'} {inst.symbol}",
                    source_url=(
                        f"https://fred.stlouisfed.org/series/{inst.symbol}"
                        if fred
                        else f"https://finance.yahoo.com/quote/{inst.symbol}"
                    ),
                )
            )
    return out


def claims_fact(fetch=default_fetch_monthly) -> Fact | None:
    s = fetch("ICSA").dropna()  # weekly series; the FRED fetch works for any id
    if len(s) < 2:
        return None
    latest, prior = float(s.iloc[-1]), float(s.iloc[-2])
    return Fact(
        id="M_ICSA",
        text=f"Initial jobless claims, week ending {s.index[-1]:%b %d}: {latest:,.0f} "
        f"(prior {prior:,.0f}, change {latest - prior:+,.0f})",
        numbers=[latest, prior, latest - prior],
        provenance="data",
        series=SeriesRef(kind="daily", provider="fred", id="ICSA", label="Initial jobless claims"),
        source_title="FRED ICSA",
        source_url="https://fred.stlouisfed.org/series/ICSA",
    )


def released_today(series_id: str, day: date) -> bool:
    """True if FRED published a new period of `series_id` on `day` (its vintage gained one)."""
    from castelino.agents.update import asof

    before = asof.fred_vintage(series_id, day - timedelta(days=1)).index[-1]
    return asof.fred_vintage(series_id, day).index[-1] != before


def _bls_parent(sid: str) -> str:  # BLS components come out with the FRED headline release
    return "PAYEMS" if sid.startswith("CES") else "CPIAUCSL"


def _asof_fetchers(day: date):
    """FRED as published on `day` (vintage), prices cut off at `day`; for rebuilt past notes."""
    from castelino.agents.update import asof
    from castelino.agents.update.collector import default_fetch_close

    def monthly(sid: str):
        return asof.fred_vintage(sid, day)

    def close(inst):
        return asof.truncate(default_fetch_close(inst), day)

    def upto(sid: str) -> str | None:  # BLS: stop at the month FRED's vintage of CPI / payrolls had
        return monthly(_bls_parent(sid)).index[-1].strftime("%Y-%m")

    return monthly, close, upto


def gather_facts(
    *,
    collect_fn=collect,
    bls_fn=bls.bls_facts,
    claims_fn=claims_fact,
    released_fn=released_today,
    today: str,
    day: date | None = None,
) -> tuple[list[Fact], MarketSnapshot]:
    """Market moves every day; a release only on the day FRED published it, so the note covers
    that day's data rather than restating last month's CPI or payrolls."""
    if day is None:
        snap = collect_fn(today=today, prediction={}, model_note=None)
    else:
        monthly, close, upto = _asof_fetchers(day)
        snap = collect_fn(
            today=today, prediction={}, model_note=None, fetch_close=close, fetch_monthly=monthly
        )
        if bls_fn is bls.bls_facts:
            bls_fn = lambda: bls.bls_facts(upto=upto)  # noqa: E731
        if claims_fn is claims_fact:
            claims_fn = lambda: claims_fact(fetch=monthly)  # noqa: E731
    fresh: set[str] = set()
    for sid in sorted({r.series for r in snap.releases} | {"CPIAUCSL", "PAYEMS", "ICSA"}):
        try:
            if released_fn(sid, day or date.today()):
                fresh.add(sid)
        except Exception as exc:  # noqa: BLE001 — can't tell (e.g. no FRED_API_KEY): keep it
            fresh.add(sid)
            gap = f"release date unknown ({str(exc)[:80]})"
            if gap not in snap.data_gaps:
                snap.data_gaps.append(gap)
    facts = release_facts(snap, keep=fresh)
    facts += market_facts(snap, start=len(facts) + 1)
    for label, fn in (("BLS", bls_fn), ("ICSA", claims_fn)):
        try:
            got = fn()
        except Exception as exc:  # noqa: BLE001 — one source must not sink the agent
            log.warning("macro %s failed: %s", label, exc)
            snap.data_gaps.append(f"{label} ({str(exc)[:80]})")
            continue
        if isinstance(got, list):
            facts += [f for f in got if _bls_parent(f.series.id) in fresh]
        elif got is not None and "ICSA" in fresh:
            facts.append(got)
    return facts, snap


class MacroAgent(StructuredAgent[FindingDrafts]):
    name = "macro_agent"
    output_schema = FindingDrafts
    tier = "fast"

    def __init__(self) -> None:
        cfg = get_settings().update_agent
        self.model = cfg.agent_model
        self.max_output_tokens = cfg.max_output_tokens  # luna reasons first

    def system_prompt(self) -> str:
        return SYSTEM

    def user_prompt(
        self, *, facts: list[Fact], brief: str, ask: str | None = None, cap: int = 6
    ) -> str:
        return drafts_prompt(facts, brief, ask, cap)


def run(brief: str, ask: str | None = None, *, day: date | None = None) -> AgentOutput:
    # ponytail: a follow-up re-fetches all macro data (~30 s); cache per day if that starts to hurt
    cap = get_settings().update_agent.max_findings_per_agent
    facts, snap = gather_facts(today=(day or date.today()).isoformat(), day=day)
    drafts = MacroAgent()(facts=facts, brief=brief, ask=ask, cap=cap)
    findings = to_findings(drafts, facts, "macro", cap)
    return AgentOutput(facts=facts, findings=findings, snapshot=snap)
