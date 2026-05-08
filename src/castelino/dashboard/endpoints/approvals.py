"""Approval workflow endpoints — read-only views + write actions for HITL."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from castelino.orchestrator.approval import ApprovalQueue

router = APIRouter()


class ApprovalAction(BaseModel):
    notes: str = ""
    reason: str = ""  # only used for reject


# ───────────────────── read-only ─────────────────────────────────────────


@router.get("/approval_metrics")
def approval_metrics():
    q = ApprovalQueue()
    pending = q.pending()
    return [
        {"label": "Pending", "value": str(len(pending)), "subvalue": "awaiting decision"},
    ]


@router.get("/approval_queue")
def approval_queue():
    q = ApprovalQueue()
    return [
        {
            "entry_id": item.entry_id,
            "gate": item.gate,
            "submitted_at": item.submitted_at,
            "summary": _payload_summary(item.gate, item.payload),
        }
        for item in q.pending()
    ]


@router.get("/approval_queue_full")
def approval_queue_full():
    """Full detail per pending item — what the dashboard needs to render the decision."""
    q = ApprovalQueue()
    return [
        {
            "entry_id": item.entry_id,
            "gate": item.gate,
            "submitted_at": item.submitted_at,
            "payload": item.payload,
        }
        for item in q.pending()
    ]


@router.get("/approval_detail/{entry_id}")
def approval_detail(entry_id: str):
    q = ApprovalQueue()
    try:
        item = q.get(entry_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {
        "entry_id": item.entry_id,
        "gate": item.gate,
        "status": item.status,
        "submitted_at": item.submitted_at,
        "resolved_at": item.resolved_at,
        "payload": item.payload,
        "notes": item.notes,
        "rejection_reason": item.rejection_reason,
    }


@router.get("/approval_history")
def approval_history():
    q = ApprovalQueue()
    return [
        {
            "entry_id": item.entry_id,
            "gate": item.gate,
            "status": item.status,
            "resolved_at": item.resolved_at or "",
            "notes": item.notes or "",
            "rejection_reason": item.rejection_reason or "",
        }
        for item in q.history()
    ]


# ───────────────────── write actions ─────────────────────────────────────


@router.post("/approvals/{entry_id}/approve")
def approve(entry_id: str, action: ApprovalAction):
    q = ApprovalQueue()
    try:
        item = q.approve(entry_id, notes=action.notes)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {
        "entry_id": item.entry_id,
        "status": item.status,
        "notes": item.notes,
        "resolved_at": item.resolved_at,
    }


@router.post("/approvals/{entry_id}/reject")
def reject(entry_id: str, action: ApprovalAction):
    q = ApprovalQueue()
    try:
        item = q.reject(entry_id, reason=action.reason or action.notes, notes=action.notes)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {
        "entry_id": item.entry_id,
        "status": item.status,
        "notes": item.notes,
        "rejection_reason": item.rejection_reason,
        "resolved_at": item.resolved_at,
    }


# ───────────────────── helpers ───────────────────────────────────────────


def _payload_summary(gate: str, payload: dict) -> str:
    """One-line human-readable summary of an approval payload."""
    if gate == "post_hypothesis":
        thesis = payload.get("thesis", "")
        regime = payload.get("regime", "")
        conv = payload.get("conviction", "")
        return f"[{regime}/{conv}] {thesis}"[:240]
    if gate == "post_debate":
        instr = payload.get("instrument", "")
        direction = payload.get("direction", "")
        decision = payload.get("decision", "")
        factor = payload.get("decisive_factor", "")
        return f"{direction.upper()} {instr} — {decision} ({factor})"[:240]
    return str(payload)[:200]


# ───────────────────── HTML form (for OpenBB html widget) ────────────────


@router.get("/approval_form", response_class=HTMLResponse)
def approval_form() -> str:
    """Render an HTML form that approves/rejects pending items via fetch()."""
    q = ApprovalQueue()
    pending = q.pending()

    if not pending:
        return _wrap_html(
            '<div class="empty">No pending approvals 🎉</div>'
        )

    cards: list[str] = []
    for item in pending:
        summary = _payload_summary(item.gate, item.payload)
        payload_html = _format_payload_block(item.gate, item.payload)
        cards.append(f'''
<div class="card" data-entry="{item.entry_id}">
  <div class="card-header">
    <span class="badge">{item.gate}</span>
    <span class="entry-id">{item.entry_id}</span>
    <span class="ts">{item.submitted_at[:19]}</span>
  </div>
  <div class="summary">{_html_escape(summary)}</div>
  <div class="payload">{payload_html}</div>
  <textarea
    id="notes-{item.entry_id}"
    placeholder="Reasoning notes (required for reject)..."
    rows="2"
  ></textarea>
  <div class="actions">
    <button class="approve" onclick="decide('{item.entry_id}', 'approve')">✅ Approve</button>
    <button class="reject" onclick="decide('{item.entry_id}', 'reject')">❌ Reject</button>
  </div>
  <div class="result" id="result-{item.entry_id}"></div>
</div>
''')

    body = "\n".join(cards)
    return _wrap_html(body)


def _format_payload_block(gate: str, payload: dict) -> str:
    """Render the payload dict as a readable HTML block."""
    if gate == "post_hypothesis":
        kc = payload.get("kill_criteria", [])
        kc_html = "<ul>" + "".join(f"<li>{_html_escape(str(c))}</li>" for c in kc) + "</ul>" if kc else ""
        return (
            f'<div class="kv"><b>Thesis:</b> {_html_escape(payload.get("thesis", ""))}</div>'
            f'<div class="kv"><b>Regime:</b> {payload.get("regime", "")} '
            f'· <b>Conviction:</b> {payload.get("conviction", "")} '
            f'· <b>Horizon:</b> {payload.get("horizon_days", "")}d</div>'
            f'<div class="kv"><b>Kill criteria:</b>{kc_html}</div>'
        )
    if gate == "post_debate":
        return (
            f'<div class="kv"><b>{payload.get("direction", "").upper()} {payload.get("instrument", "")}</b> · '
            f'<b>Decision:</b> {payload.get("decision", "")} · '
            f'<b>Size mult:</b> {payload.get("size_multiplier", "")}</div>'
            f'<div class="kv"><b>Decisive factor:</b> {_html_escape(payload.get("decisive_factor", ""))}</div>'
            f'<div class="kv"><b>Dissent:</b> {_html_escape(payload.get("dissent", "") or "—")}</div>'
        )
    return f'<pre>{_html_escape(str(payload))}</pre>'


def _html_escape(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _wrap_html(body: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif;
          background: #0e1117; color: #c9d1d9; margin: 0; padding: 16px; }}
  .empty {{ text-align: center; padding: 40px; color: #8b949e; font-size: 16px; }}
  .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px;
          padding: 14px; margin-bottom: 12px; }}
  .card-header {{ display: flex; gap: 12px; align-items: center; margin-bottom: 8px;
                 font-size: 11px; color: #8b949e; }}
  .badge {{ background: #1f6feb; color: white; padding: 2px 8px; border-radius: 12px;
           font-size: 11px; text-transform: uppercase; }}
  .entry-id {{ font-family: monospace; }}
  .ts {{ margin-left: auto; }}
  .summary {{ font-size: 14px; font-weight: 600; margin-bottom: 8px; color: #f0f6fc; }}
  .payload {{ background: #0d1117; padding: 10px; border-radius: 6px; margin-bottom: 10px;
             font-size: 13px; line-height: 1.5; }}
  .kv {{ margin-bottom: 6px; }}
  .kv b {{ color: #58a6ff; }}
  ul {{ margin: 4px 0; padding-left: 20px; }}
  textarea {{ width: 100%; background: #0d1117; color: #c9d1d9; border: 1px solid #30363d;
             border-radius: 6px; padding: 8px; font-family: inherit; font-size: 13px;
             box-sizing: border-box; resize: vertical; }}
  .actions {{ display: flex; gap: 8px; margin-top: 8px; }}
  button {{ padding: 8px 16px; border: 0; border-radius: 6px; font-weight: 600;
           cursor: pointer; font-size: 13px; }}
  button.approve {{ background: #238636; color: white; }}
  button.approve:hover {{ background: #2ea043; }}
  button.reject {{ background: #da3633; color: white; }}
  button.reject:hover {{ background: #f85149; }}
  button:disabled {{ opacity: 0.5; cursor: not-allowed; }}
  .result {{ margin-top: 8px; font-size: 12px; padding: 6px 10px; border-radius: 6px;
            display: none; }}
  .result.success {{ background: #0d4429; color: #56d364; display: block; }}
  .result.error {{ background: #4a1a1a; color: #f85149; display: block; }}
</style></head><body>
{body}
<script>
async function decide(entryId, action) {{
  const notesEl = document.getElementById('notes-' + entryId);
  const notes = notesEl.value.trim();
  const resultEl = document.getElementById('result-' + entryId);
  if (action === 'reject' && !notes) {{
    resultEl.className = 'result error';
    resultEl.textContent = 'Rejection requires a reason in the notes field.';
    return;
  }}
  const card = document.querySelector('.card[data-entry="' + entryId + '"]');
  card.querySelectorAll('button').forEach(b => b.disabled = true);
  try {{
    const resp = await fetch('/approvals/' + entryId + '/' + action, {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ notes: notes, reason: notes }}),
    }});
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();
    resultEl.className = 'result success';
    resultEl.textContent = (action === 'approve' ? '✅ Approved' : '❌ Rejected') +
                           ' at ' + data.resolved_at;
    setTimeout(() => location.reload(), 1500);
  }} catch (e) {{
    resultEl.className = 'result error';
    resultEl.textContent = 'Error: ' + e.message;
    card.querySelectorAll('button').forEach(b => b.disabled = false);
  }}
}}
</script></body></html>"""
