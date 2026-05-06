"""Tests for the HITL approval queue."""
import json
import threading
import time
from pathlib import Path

import pytest

from castelino.orchestrator.approval import (
    ApprovalItem,
    ApprovalQueue,
    ApprovalStatus,
    GateType,
)


@pytest.fixture
def queue(tmp_path):
    return ApprovalQueue(state_dir=tmp_path)


def test_submit_creates_pending_item(queue):
    item = queue.submit(
        gate=GateType.POST_HYPOTHESIS,
        payload={"thesis": "Rates will rise", "regime": "tightening"},
        entry_id="H-abc123",
    )
    assert item.status == ApprovalStatus.PENDING
    assert item.gate == GateType.POST_HYPOTHESIS
    assert item.entry_id == "H-abc123"


def test_persists_to_disk(queue, tmp_path):
    queue.submit(gate=GateType.POST_HYPOTHESIS, payload={"thesis": "test"}, entry_id="H-001")
    queue2 = ApprovalQueue(state_dir=tmp_path)
    pending = queue2.pending()
    assert len(pending) == 1
    assert pending[0].entry_id == "H-001"


def test_approve(queue):
    queue.submit(gate=GateType.POST_DEBATE, payload={}, entry_id="V-001")
    item = queue.approve("V-001")
    assert item.status == ApprovalStatus.APPROVED
    assert item.resolved_at is not None


def test_reject(queue):
    queue.submit(gate=GateType.POST_DEBATE, payload={}, entry_id="V-001")
    item = queue.reject("V-001", reason="too risky")
    assert item.status == ApprovalStatus.REJECTED
    assert item.rejection_reason == "too risky"


def test_edit_updates_payload_and_approves(queue):
    queue.submit(gate=GateType.POST_HYPOTHESIS, payload={"thesis": "original"}, entry_id="H-001")
    item = queue.edit("H-001", updated_payload={"thesis": "revised"})
    assert item.status == ApprovalStatus.APPROVED
    assert item.payload["thesis"] == "revised"


def test_approve_nonexistent_raises(queue):
    with pytest.raises(KeyError):
        queue.approve("NOPE")


def test_wait_for_resolution_returns_on_approve(queue):
    queue.submit(gate=GateType.POST_HYPOTHESIS, payload={}, entry_id="H-001")

    def approve_later():
        time.sleep(0.3)
        queue.approve("H-001")

    t = threading.Thread(target=approve_later)
    t.start()
    result = queue.wait_for_resolution("H-001", poll_interval=0.1)
    t.join()
    assert result.status == ApprovalStatus.APPROVED


def test_history_returns_resolved_items(queue):
    queue.submit(gate=GateType.POST_HYPOTHESIS, payload={}, entry_id="H-001")
    queue.submit(gate=GateType.POST_DEBATE, payload={}, entry_id="V-001")
    queue.approve("H-001")
    queue.reject("V-001", reason="nope")
    hist = queue.history()
    assert len(hist) == 2
    assert all(h.status != ApprovalStatus.PENDING for h in hist)


def test_pending_excludes_resolved(queue):
    queue.submit(gate=GateType.POST_HYPOTHESIS, payload={}, entry_id="H-001")
    queue.submit(gate=GateType.POST_DEBATE, payload={}, entry_id="V-001")
    queue.approve("H-001")
    pending = queue.pending()
    assert len(pending) == 1
    assert pending[0].entry_id == "V-001"
