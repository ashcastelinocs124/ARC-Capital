"""Human-in-the-loop approval queue. Persists to JSON on disk."""
from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from castelino.config import get_settings

log = logging.getLogger(__name__)


class GateType(str, Enum):
    POST_HYPOTHESIS = "post_hypothesis"
    POST_DEBATE = "post_debate"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalItem(BaseModel):
    entry_id: str
    gate: GateType
    status: ApprovalStatus = ApprovalStatus.PENDING
    payload: dict = Field(default_factory=dict)
    submitted_at: str = ""
    resolved_at: str | None = None
    rejection_reason: str | None = None
    notes: str = ""  # human reasoning for approve/reject decision

    model_config = {"use_enum_values": True}


class ApprovalQueue:
    """Disk-backed approval queue."""

    def __init__(self, state_dir: Path | None = None):
        if state_dir is None:
            cfg = get_settings()
            state_dir = cfg.resolved_paths.data
        self._path = state_dir / "approval_queue.json"
        self._items: dict[str, ApprovalItem] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            raw = json.loads(self._path.read_text())
            for entry_id, data in raw.items():
                self._items[entry_id] = ApprovalItem.model_validate(data)

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {k: v.model_dump() for k, v in self._items.items()}
        self._path.write_text(json.dumps(payload, indent=2, default=str))

    def submit(self, *, gate: GateType, payload: dict, entry_id: str) -> ApprovalItem:
        item = ApprovalItem(
            entry_id=entry_id,
            gate=gate,
            payload=payload,
            submitted_at=datetime.now(UTC).isoformat(),
        )
        self._items[entry_id] = item
        self._save()
        log.info("Approval gate %s: item %s pending", gate.value, entry_id)
        return item

    def pending(self) -> list[ApprovalItem]:
        return [i for i in self._items.values() if i.status == ApprovalStatus.PENDING]

    def get(self, entry_id: str) -> ApprovalItem:
        if entry_id not in self._items:
            raise KeyError(f"No approval item with id {entry_id}")
        return self._items[entry_id]

    def approve(self, entry_id: str, notes: str = "") -> ApprovalItem:
        item = self.get(entry_id)
        item.status = ApprovalStatus.APPROVED
        item.resolved_at = datetime.now(UTC).isoformat()
        item.notes = notes
        self._save()
        log.info("Approved: %s%s", entry_id, f" — {notes}" if notes else "")
        return item

    def reject(self, entry_id: str, reason: str = "", notes: str = "") -> ApprovalItem:
        item = self.get(entry_id)
        item.status = ApprovalStatus.REJECTED
        item.rejection_reason = reason
        item.notes = notes or reason
        item.resolved_at = datetime.now(UTC).isoformat()
        self._save()
        log.info("Rejected: %s — %s", entry_id, reason)
        return item

    def edit(self, entry_id: str, updated_payload: dict) -> ApprovalItem:
        item = self.get(entry_id)
        item.payload = updated_payload
        item.status = ApprovalStatus.APPROVED
        item.resolved_at = datetime.now(UTC).isoformat()
        self._save()
        log.info("Edited + approved: %s", entry_id)
        return item

    def wait_for_resolution(self, entry_id: str, poll_interval: float = 2.0) -> ApprovalItem:
        """Block until the item is approved or rejected."""
        while True:
            self._load()
            item = self.get(entry_id)
            if item.status != ApprovalStatus.PENDING:
                return item
            time.sleep(poll_interval)

    def history(self, limit: int = 50) -> list[ApprovalItem]:
        resolved = [i for i in self._items.values() if i.status != ApprovalStatus.PENDING]
        return sorted(resolved, key=lambda x: x.resolved_at or "", reverse=True)[:limit]
