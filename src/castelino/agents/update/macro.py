"""Macro agent: code gathers FRED / BLS / Yahoo facts, gpt-6-luna picks the findings."""

from __future__ import annotations

import logging
from datetime import date

from castelino.agents.base import StructuredAgent
from castelino.agents.update import bls
from castelino.agents.update.collector import asset_groups, collect, default_fetch_monthly
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


def release_facts(snap: MarketSnapshot) -> list[Fact]:
    out: list[Fact] = []
    for r in snap.releases:
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
            out.append(
                Fact(
                    id=f"M{start + len(out)}",
                    text=f"{iid} ({cls}): " + ", ".join(parts),
                    numbers=[v for v in w.values() if v is not None],
                    provenance="data",
                    series=SeriesRef(
                        kind="daily",
                        provider="fred" if fred else "yahoo",
                        id=inst.symbol,
                        label=iid,
                    ),
                    source_title=f"{'FRED' if fred else 'Yahoo Finance'} {inst.symbol}",
                    source_url=(
                        f"https://fred.stlouisfed.org/series/{inst.symbol}"
                        if fred
                        else f"https://finance.yahoo.com/quote/{inst.symbol}"
                    ),
                )
            )
    return out


def claims_fact() -> Fact | None:
    s = default_fetch_monthly("ICSA").dropna()  # weekly series; the FRED fetch works for any id
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


def gather_facts(
    *, collect_fn=collect, bls_fn=bls.bls_facts, claims_fn=claims_fact, today: str
) -> tuple[list[Fact], MarketSnapshot]:
    snap = collect_fn(today=today, prediction={}, model_note=None)
    facts = release_facts(snap)
    facts += market_facts(snap, start=len(facts) + 1)
    for label, fn in (("BLS", bls_fn), ("ICSA", claims_fn)):
        try:
            got = fn()
        except Exception as exc:  # noqa: BLE001 — one source must not sink the agent
            log.warning("macro %s failed: %s", label, exc)
            snap.data_gaps.append(f"{label} ({str(exc)[:80]})")
            continue
        if isinstance(got, list):
            facts += got
        elif got is not None:
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


def run(brief: str, ask: str | None = None) -> AgentOutput:
    # ponytail: a follow-up re-fetches all macro data (~30 s); cache per day if that starts to hurt
    cap = get_settings().update_agent.max_findings_per_agent
    facts, snap = gather_facts(today=date.today().isoformat())
    drafts = MacroAgent()(facts=facts, brief=brief, ask=ask, cap=cap)
    findings = to_findings(drafts, facts, "macro", cap)
    return AgentOutput(facts=facts, findings=findings, snapshot=snap)
