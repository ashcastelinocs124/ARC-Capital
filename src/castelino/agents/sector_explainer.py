"""Sector Sentiment explainers — OpenAI prose around numbers Python already computed.

Two StructuredAgents, run once per daily refresh (1 narrative + 11 sector calls):
  - SectorNarrativeAgent: 3-5 sentence read of the whole snapshot.
  - SectorProseAgent: 2-3 sentences per sector explaining its concentration
    verdict (stock_specific / sector_wide / mixed), which code has decided.

Failure-tolerant by contract: any LLM error leaves that text None and the
snapshot ships with just the numbers. Ported from arc-dashboard's Claude
explainer onto this repo's OpenAI client.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from pydantic import BaseModel

from castelino.agents.base import StructuredAgent
from castelino.signals.sector_sentiment import SectorScore, SectorSentimentSnapshot, StockRow

log = logging.getLogger(__name__)

_DEFINITION = """\
divergence = technical score - fundamental score, each -1..+1; positive =
price running ahead of fundamentals ("euphoric" at >= +0.30), negative =
strong fundamentals nobody is buying ("fearful" at <= -0.30)."""

NARRATIVE_SYSTEM = f"""\
You are the analyst voice of ARC Research's Sector Sentiment tool.

You are given today's sector divergence table ({_DEFINITION}), each sector's
concentration verdict, the change since the previous snapshot, and notable
stocks.

Write a 3-5 sentence read for a portfolio manager:
- Lead with the most interesting thing in today's data (biggest level,
  biggest change since the last snapshot, or a concentration story).
- Cite concrete numbers from the provided data ONLY. Never invent data.
- Note when a reading is one stock's story rather than the whole sector's.
- NO trade recommendations, no position advice. Describe; humans decide.
Set `biggest_move` to a short "<sector> <+/-value>" for the largest change
since the previous snapshot (or the largest level if there is no change data).
"""

SECTOR_SYSTEM = f"""\
You are the analyst voice of ARC Research's Sector Sentiment tool, explaining
ONE sector's divergence reading ({_DEFINITION})

Python has already decided the VERDICT on whether the reading is one stock's
story (stock_specific), the whole sector's (sector_wide), or mixed. The verdict
is final — explain it, do not re-judge it.

Write 2-3 sentences for a portfolio manager:
- Name the stocks that drive the reading and what they have in common
  (sub-industry, shared setup) when the data shows it.
- Cite concrete numbers from the supplied data ONLY. Never invent data.
- Note when the equal-weight average disagrees with the cap-weighted reading
  (the breadth story).
- NO trade recommendations, no position advice. Describe; humans decide.
"""


class SectorNarrative(BaseModel):
    narrative: str
    biggest_move: str


class SectorProse(BaseModel):
    explanation: str


def narrative_context(snap: SectorSentimentSnapshot, prev_narrative: str | None = None) -> str:
    lines = ["TODAY'S SECTOR TABLE (sorted most positive -> most negative):"]
    for s in snap.sectors:
        z = f" z={s.zscore:+.1f}" if s.zscore is not None else ""
        d = (
            f" change since prev {s.delta_since_prev:+.2f}"
            if s.delta_since_prev is not None
            else ""
        )
        lines.append(f"- {s.sector} ({s.etf}): divergence {s.divergence:+.2f} [{s.label}]{z}{d}")

    verdicts = [(s.sector, s.explanation) for s in snap.sectors if s.explanation]
    if verdicts:
        lines.append(
            "\nCONCENTRATION VERDICTS (stock_specific = one name is the whole reading; "
            "sector_wide = most constituents agree):"
        )
        for sector, e in verdicts:
            lines.append(
                f"- {sector}: {e.verdict} (top contributor {e.top_symbol} {e.top_share:.0%}, "
                f"{e.n_agree}/{e.n_total} share sign, equal-weight {e.equal_weight_divergence:+.2f})"
            )

    notable = [r for r in snap.stocks if r.divergence is not None and abs(r.divergence) >= 0.4]
    lines.append("\nNOTABLE STOCKS (|divergence| >= 0.4):")
    for r in sorted(notable, key=lambda r: -abs(r.divergence or 0))[:15]:
        lines.append(
            f"- {r.symbol} ({r.sector}): div {r.divergence:+.2f}, RSI {r.rsi14}, "
            f"vs SMA200 {r.vs_sma200}, rev YoY {r.rev_yoy}, P/E vs sector {r.pe_rel}"
        )

    if prev_narrative:
        lines.append(f"\nPREVIOUS NARRATIVE (for continuity):\n{prev_narrative}")
    return "\n".join(lines)


def sector_context(s: SectorScore, rows: list[StockRow]) -> str:
    e = s.explanation
    assert e is not None
    lines = [
        f"SECTOR: {s.sector} — cap-weighted divergence {s.divergence:+.2f} [{s.label}], "
        f"equal-weight {e.equal_weight_divergence:+.2f}",
        f"VERDICT (final, computed): {e.verdict}",
        f"- {e.n_agree}/{e.n_total} constituents share the sector's sign",
        f"- top contributor {e.top_symbol} supplies {e.top_share:.0%} of the reading",
        f"- drivers by |contribution|: {', '.join(e.drivers)}",
        "\nCONSTITUENTS (contribution = cap share x divergence; sums to the sector value):",
    ]
    by_symbol = {r.symbol: r for r in rows}
    for c in e.contributions:
        r = by_symbol.get(c.symbol)
        extra = ""
        if r is not None:
            extra = (
                f", {r.name}, RSI {r.rsi14 and round(r.rsi14)}, vs SMA200 {r.vs_sma200}, "
                f"rev YoY {r.rev_yoy}, P/E vs sector {r.pe_rel}"
            )
        lines.append(f"- {c.symbol}: div {c.divergence:+.2f}, contrib {c.contribution:+.3f}{extra}")
    return "\n".join(lines)


class SectorNarrativeAgent(StructuredAgent[SectorNarrative]):
    name = "sector_narrative"
    output_schema = SectorNarrative
    tier = "fast"

    def system_prompt(self) -> str:
        return NARRATIVE_SYSTEM

    def user_prompt(
        self, *, snap: SectorSentimentSnapshot, prev_narrative: str | None = None
    ) -> str:
        return narrative_context(snap, prev_narrative)


class SectorProseAgent(StructuredAgent[SectorProse]):
    name = "sector_prose"
    output_schema = SectorProse
    tier = "fast"

    def system_prompt(self) -> str:
        return SECTOR_SYSTEM

    def user_prompt(self, *, sector: SectorScore, rows: list[StockRow]) -> str:
        return sector_context(sector, rows)


def explain_snapshot(
    snap: SectorSentimentSnapshot, prev_narrative: str | None = None
) -> SectorSentimentSnapshot:
    """Fill snap.narrative and each sector's explanation.prose; a failed call leaves it None."""
    now = datetime.now(UTC)
    update: dict = {}
    try:
        out = SectorNarrativeAgent()(snap=snap, prev_narrative=prev_narrative)
        update = {"narrative": out.narrative, "narrative_generated_at": now}
    except Exception:
        log.exception("sector narrative failed; shipping without it")

    sectors = list(snap.sectors)
    for i, s in enumerate(sectors):
        if s.explanation is None:
            continue
        try:
            rows = [r for r in snap.stocks if r.sector == s.sector]
            prose = SectorProseAgent()(sector=s, rows=rows).explanation
        except Exception:
            log.exception("sector prose failed for %s", s.sector)
            continue
        sectors[i] = s.model_copy(
            update={
                "explanation": s.explanation.model_copy(
                    update={"prose": prose, "generated_at": now}
                )
            }
        )
    return snap.model_copy(update={**update, "sectors": sectors})
