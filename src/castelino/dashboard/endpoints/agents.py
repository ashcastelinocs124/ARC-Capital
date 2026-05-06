from __future__ import annotations

from fastapi import APIRouter

from castelino.memory import io as memio
from castelino.memory.schemas import GuardDecision, Verdict

router = APIRouter()


@router.get("/verdicts")
def verdicts():
    entries = memio.read_short_term()
    vs = sorted(
        [e for e in entries if isinstance(e, Verdict)],
        key=lambda x: x.timestamp, reverse=True,
    )[:20]
    return [
        {"timestamp": v.timestamp.strftime("%Y-%m-%d %H:%M"), "decision": v.decision,
         "size_multiplier": round(v.size_multiplier, 2), "decisive_factor": v.decisive_factor}
        for v in vs
    ]


@router.get("/guard_decisions")
def guard_decisions():
    entries = memio.read_short_term()
    gs = sorted(
        [e for e in entries if isinstance(e, GuardDecision)],
        key=lambda x: x.timestamp, reverse=True,
    )[:20]
    return [
        {"timestamp": g.timestamp.strftime("%Y-%m-%d %H:%M"), "decision": g.decision,
         "triggered_rules": len(g.triggered_rules), "rationale": g.rationale[:150]}
        for g in gs
    ]
