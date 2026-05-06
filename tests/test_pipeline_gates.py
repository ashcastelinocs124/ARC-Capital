"""Tests for HITL approval gates in the pipeline."""
import threading
import time

import pytest

from castelino.orchestrator.approval import ApprovalQueue, ApprovalStatus, GateType


def test_hypothesis_gate_stalls_then_approves(tmp_path):
    queue = ApprovalQueue(state_dir=tmp_path)
    queue.submit(gate=GateType.POST_HYPOTHESIS, payload={"thesis": "test"}, entry_id="H-test")

    def approve_later():
        time.sleep(0.3)
        queue.approve("H-test")

    t = threading.Thread(target=approve_later)
    t.start()
    result = queue.wait_for_resolution("H-test", poll_interval=0.1)
    t.join()
    assert result.status == ApprovalStatus.APPROVED


def test_debate_gate_rejection(tmp_path):
    queue = ApprovalQueue(state_dir=tmp_path)
    queue.submit(gate=GateType.POST_DEBATE, payload={"decision": "proceed"}, entry_id="V-test")
    queue.reject("V-test", reason="too risky")
    item = queue.get("V-test")
    assert item.status == ApprovalStatus.REJECTED
    assert item.rejection_reason == "too risky"


def test_queue_persists_to_disk(tmp_path):
    """Verify the queue state survives re-instantiation."""
    q1 = ApprovalQueue(state_dir=tmp_path)
    q1.submit(gate=GateType.POST_HYPOTHESIS, payload={"x": 1}, entry_id="H-persist")

    # Fresh instance should load persisted state
    q2 = ApprovalQueue(state_dir=tmp_path)
    item = q2.get("H-persist")
    assert item.status == ApprovalStatus.PENDING
    assert item.payload == {"x": 1}


def test_approve_updates_resolved_at(tmp_path):
    queue = ApprovalQueue(state_dir=tmp_path)
    queue.submit(gate=GateType.POST_DEBATE, payload={}, entry_id="V-ts")
    queue.approve("V-ts")
    item = queue.get("V-ts")
    assert item.resolved_at is not None
    assert item.status == ApprovalStatus.APPROVED
