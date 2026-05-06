from __future__ import annotations

from fastapi import APIRouter

from castelino.orchestrator.approval import ApprovalQueue

router = APIRouter()


@router.get("/approval_metrics")
def approval_metrics():
    q = ApprovalQueue()
    pending = q.pending()
    return [{"label": "Pending", "value": str(len(pending)), "subvalue": "awaiting decision"}]


@router.get("/approval_queue")
def approval_queue():
    q = ApprovalQueue()
    return [
        {"entry_id": item.entry_id, "gate": item.gate, "submitted_at": item.submitted_at,
         "payload": str(item.payload)[:200]}
        for item in q.pending()
    ]


@router.get("/approval_history")
def approval_history():
    q = ApprovalQueue()
    return [
        {"entry_id": item.entry_id, "gate": item.gate, "status": item.status,
         "resolved_at": item.resolved_at or "", "reason": item.rejection_reason or ""}
        for item in q.history()
    ]
