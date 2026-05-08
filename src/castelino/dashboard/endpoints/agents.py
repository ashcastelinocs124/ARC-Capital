"""Agent activity endpoints — one per agent in the pipeline.

Each endpoint reads the short-term journal, filters by entry type, and
returns the most recent N records as flat dicts the dashboard can render.
"""
from __future__ import annotations

from fastapi import APIRouter

from castelino.memory import io as memio
from castelino.memory.schemas import (
    BearCase,
    BullCase,
    GuardDecision,
    Hypothesis,
    LongTermLesson,
    PrincipleWarning,
    ResearchBundle,
    TradeExpression,
    TriggerRecord,
    Verdict,
    WorldStateBrief,
)

router = APIRouter()

LIMIT = 20


def _ts(s):
    """Stringify a timestamp."""
    return s.strftime("%Y-%m-%d %H:%M") if s else "—"


# ── Trigger / Current Event / Hypothesis ──────────────────────────────


@router.get("/agent_triggers")
def agent_triggers():
    entries = memio.read_short_term()
    items = sorted(
        [e for e in entries if isinstance(e, TriggerRecord)],
        key=lambda x: x.timestamp,
        reverse=True,
    )[:LIMIT]
    return [
        {
            "timestamp": _ts(t.timestamp),
            "source": t.source.value if hasattr(t.source, "value") else str(t.source),
            "headline": t.headline,
            "significance": round(t.significance, 2),
            "asset_classes": ", ".join(t.asset_classes_affected) or "—",
            "reason": t.one_sentence_reason,
        }
        for t in items
    ]


@router.get("/agent_world_state")
def agent_world_state():
    entries = memio.read_short_term()
    items = sorted(
        [e for e in entries if isinstance(e, WorldStateBrief)],
        key=lambda x: x.timestamp,
        reverse=True,
    )[:LIMIT]
    return [
        {
            "timestamp": _ts(w.timestamp),
            "summary": w.summary,
            "headline_count": len(w.headlines),
            "indicator_reads": len(getattr(w, "leading_indicator_reads", []) or []),
            "surprises": len(w.surprises),
        }
        for w in items
    ]


@router.get("/agent_hypotheses")
def agent_hypotheses():
    entries = memio.read_short_term()
    items = sorted(
        [e for e in entries if isinstance(e, Hypothesis)],
        key=lambda x: x.timestamp,
        reverse=True,
    )[:LIMIT]
    return [
        {
            "timestamp": _ts(h.timestamp),
            "thesis": h.thesis,
            "regime": h.regime.value if hasattr(h.regime, "value") else str(h.regime),
            "conviction": h.conviction.value if hasattr(h.conviction, "value") else str(h.conviction),
            "horizon_days": h.horizon_days,
            "kill_criteria_count": len(h.kill_criteria),
            "rationale": h.rationale,
        }
        for h in items
    ]


@router.get("/agent_expressions")
def agent_expressions():
    entries = memio.read_short_term()
    items = sorted(
        [e for e in entries if isinstance(e, TradeExpression)],
        key=lambda x: x.timestamp,
        reverse=True,
    )[:LIMIT]
    return [
        {
            "timestamp": _ts(x.timestamp),
            "instrument": x.instrument_id,
            "direction": x.direction.value if hasattr(x.direction, "value") else str(x.direction),
            "target_pct_nav": round(x.target_size_pct_nav, 4),
            "stop_pct": round(x.initial_stop_pct, 3),
            "rationale": x.rationale,
        }
        for x in items
    ]


# ── Research desk ──────────────────────────────────────────────────────


@router.get("/agent_research")
def agent_research():
    entries = memio.read_short_term()
    bundles = sorted(
        [e for e in entries if isinstance(e, ResearchBundle)],
        key=lambda x: x.timestamp,
        reverse=True,
    )[:LIMIT]
    return [
        {
            "timestamp": _ts(b.timestamp),
            "instrument": b.web.instrument_id,
            "sentiment": b.web.sentiment,
            "trend": b.technical.trend,
            "rsi_14": round(b.technical.rsi_14, 1),
            "hit_rate": round(b.backtest.hit_rate, 2),
            "samples": b.backtest.similar_setups_found,
            "vol_60d": round(b.risk.realized_vol_60d, 3),
            "summary": b.web.summary[:140],
        }
        for b in bundles
    ]


# ── Bull / Bear / Debate ────────────────────────────────────────────────


@router.get("/agent_bull")
def agent_bull():
    entries = memio.read_short_term()
    items = sorted(
        [e for e in entries if isinstance(e, BullCase)],
        key=lambda x: x.timestamp,
        reverse=True,
    )[:LIMIT]
    return [
        {
            "timestamp": _ts(b.timestamp),
            "confidence": b.confidence.value if hasattr(b.confidence, "value") else str(b.confidence),
            "argument_count": len(b.arguments),
            "strongest": b.strongest_argument,
        }
        for b in items
    ]


@router.get("/agent_bear")
def agent_bear():
    entries = memio.read_short_term()
    items = sorted(
        [e for e in entries if isinstance(e, BearCase)],
        key=lambda x: x.timestamp,
        reverse=True,
    )[:LIMIT]
    return [
        {
            "timestamp": _ts(b.timestamp),
            "confidence": b.confidence.value if hasattr(b.confidence, "value") else str(b.confidence),
            "argument_count": len(b.arguments),
            "strongest": b.strongest_argument,
        }
        for b in items
    ]


@router.get("/agent_verdicts")
def agent_verdicts():
    entries = memio.read_short_term()
    items = sorted(
        [e for e in entries if isinstance(e, Verdict)],
        key=lambda x: x.timestamp,
        reverse=True,
    )[:LIMIT]
    return [
        {
            "timestamp": _ts(v.timestamp),
            "decision": v.decision,
            "size_multiplier": round(v.size_multiplier, 2),
            "decisive_factor": v.decisive_factor,
            "dissent": v.dissent or "—",
        }
        for v in items
    ]


# ── Guard / Warnings ────────────────────────────────────────────────────


@router.get("/agent_guard")
def agent_guard():
    entries = memio.read_short_term()
    items = sorted(
        [e for e in entries if isinstance(e, GuardDecision)],
        key=lambda x: x.timestamp,
        reverse=True,
    )[:LIMIT]
    return [
        {
            "timestamp": _ts(g.timestamp),
            "decision": g.decision,
            "triggered_rules": ", ".join(g.triggered_rules) if g.triggered_rules else "—",
            "amended_size": round(g.amended_size_multiplier, 2),
            "rationale": g.rationale[:200],
        }
        for g in items
    ]


@router.get("/agent_warnings")
def agent_warnings():
    entries = memio.read_short_term()
    items = sorted(
        [e for e in entries if isinstance(e, PrincipleWarning)],
        key=lambda x: x.timestamp,
        reverse=True,
    )[:LIMIT]
    return [
        {
            "timestamp": _ts(w.timestamp),
            "rule_id": w.rule_id,
            "severity": w.severity,
            "description": w.description,
        }
        for w in items
    ]


# ── Curator ─────────────────────────────────────────────────────────────


@router.get("/agent_curator")
def agent_curator():
    """Long-term lessons distilled by the weekly Curator pass."""
    lessons = memio.read_long_term()
    items = sorted(lessons, key=lambda x: x.timestamp, reverse=True)[:LIMIT]
    return [
        {
            "timestamp": _ts(l.timestamp),
            "category": l.category,
            "title": l.title,
            "body": l.body[:200],
            "statistical_backing": l.statistical_backing or "—",
        }
        for l in items
    ]


# ── Pipeline summary ────────────────────────────────────────────────────


@router.get("/agent_summary")
def agent_summary():
    """Counts per agent — used by the dashboard to render activity tiles."""
    entries = memio.read_short_term()
    return [
        {"agent": "Trigger", "count": sum(1 for e in entries if isinstance(e, TriggerRecord))},
        {"agent": "Current Event", "count": sum(1 for e in entries if isinstance(e, WorldStateBrief))},
        {"agent": "Hypothesis", "count": sum(1 for e in entries if isinstance(e, Hypothesis))},
        {"agent": "Asset Selection", "count": sum(1 for e in entries if isinstance(e, TradeExpression))},
        {"agent": "Research Desk", "count": sum(1 for e in entries if isinstance(e, ResearchBundle))},
        {"agent": "Bull", "count": sum(1 for e in entries if isinstance(e, BullCase))},
        {"agent": "Bear", "count": sum(1 for e in entries if isinstance(e, BearCase))},
        {"agent": "Debate", "count": sum(1 for e in entries if isinstance(e, Verdict))},
        {"agent": "Guard", "count": sum(1 for e in entries if isinstance(e, GuardDecision))},
        {"agent": "Curator", "count": len(memio.read_long_term())},
    ]


# Legacy aliases (preserve OpenBB Workspace widget compat)
@router.get("/verdicts")
def verdicts():
    return agent_verdicts()


@router.get("/guard_decisions")
def guard_decisions():
    return agent_guard()
