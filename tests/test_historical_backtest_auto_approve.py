"""Phase-3 tests: auto-approval policy + queue hook + model override."""
from __future__ import annotations

import pytest

from castelino.backtest import BACKTEST_AS_OF_ENV
from castelino.backtest import auto_approve as aa
from castelino.orchestrator.approval import (
    ApprovalItem, ApprovalQueue, ApprovalStatus, GateType,
)


# ─────────────── pure policy tests (no env / no queue) ───────────────────


@pytest.mark.parametrize("conviction,expected_status", [
    ("high", ApprovalStatus.APPROVED),
    ("medium", ApprovalStatus.APPROVED),
    ("low", ApprovalStatus.REJECTED),
    ("", ApprovalStatus.REJECTED),
])
def test_post_hypothesis_policy(conviction, expected_status):
    item = ApprovalItem(
        entry_id="H-1", gate=GateType.POST_HYPOTHESIS,
        payload={"conviction": conviction},
    )
    aa.apply_policy(item)
    assert item.status == expected_status
    assert item.resolved_at is not None
    if expected_status == ApprovalStatus.REJECTED:
        assert item.rejection_reason is not None


@pytest.mark.parametrize("payload,expected_status", [
    ({"decision": "proceed", "size_multiplier": 1.0, "dissent": "low"},
     ApprovalStatus.APPROVED),
    ({"decision": "modify", "size_multiplier": 0.7, "dissent": "low"},
     ApprovalStatus.APPROVED),
    ({"decision": "modify", "size_multiplier": 0.3, "dissent": "low"},
     ApprovalStatus.REJECTED),
    ({"decision": "reject", "size_multiplier": 1.0, "dissent": "low"},
     ApprovalStatus.REJECTED),
    ({"decision": "proceed", "size_multiplier": 1.0, "dissent": "high"},
     ApprovalStatus.REJECTED),
    # Edge: "high" anywhere in the dissent string still rejects (the
    # production payload sometimes uses "high (bear made strong case)")
    ({"decision": "proceed", "size_multiplier": 1.0, "dissent": "high (bear)"},
     ApprovalStatus.REJECTED),
])
def test_post_debate_policy(payload, expected_status):
    item = ApprovalItem(entry_id="V-1", gate=GateType.POST_DEBATE, payload=payload)
    aa.apply_policy(item)
    assert item.status == expected_status


def test_apply_policy_idempotent_on_resolved_items():
    item = ApprovalItem(
        entry_id="H-2", gate=GateType.POST_HYPOTHESIS,
        payload={"conviction": "high"}, status=ApprovalStatus.REJECTED,
    )
    item.rejection_reason = "human override"
    aa.apply_policy(item)
    # Should NOT flip a manually-rejected item
    assert item.status == ApprovalStatus.REJECTED
    assert item.rejection_reason == "human override"


# ─────────────── queue integration: env var triggers auto-approve ────────


@pytest.fixture
def queue_in_tmp(monkeypatch, tmp_path):
    return ApprovalQueue(state_dir=tmp_path)


def test_queue_submit_no_env_stays_pending(queue_in_tmp, monkeypatch):
    monkeypatch.delenv(BACKTEST_AS_OF_ENV, raising=False)
    item = queue_in_tmp.submit(
        gate=GateType.POST_HYPOTHESIS,
        payload={"conviction": "high"},
        entry_id="H-live",
    )
    assert item.status == ApprovalStatus.PENDING


def test_queue_submit_with_env_resolves_immediately(queue_in_tmp, monkeypatch):
    monkeypatch.setenv(BACKTEST_AS_OF_ENV, "2024-03-15")
    approved = queue_in_tmp.submit(
        gate=GateType.POST_HYPOTHESIS,
        payload={"conviction": "high"},
        entry_id="H-bt-1",
    )
    rejected = queue_in_tmp.submit(
        gate=GateType.POST_HYPOTHESIS,
        payload={"conviction": "low"},
        entry_id="H-bt-2",
    )
    assert approved.status == ApprovalStatus.APPROVED
    assert rejected.status == ApprovalStatus.REJECTED


def test_queue_wait_for_resolution_returns_instantly_in_backtest(
    queue_in_tmp, monkeypatch,
):
    """`wait_for_resolution()` should not block — auto-approval runs at submit
    time so the item is already resolved."""
    monkeypatch.setenv(BACKTEST_AS_OF_ENV, "2024-03-15")
    item = queue_in_tmp.submit(
        gate=GateType.POST_DEBATE,
        payload={"decision": "proceed", "size_multiplier": 1.0, "dissent": "low"},
        entry_id="V-bt-1",
    )
    # Fast — would hang in live mode without a human resolver
    result = queue_in_tmp.wait_for_resolution(item.entry_id, poll_interval=0.01)
    assert result.status == ApprovalStatus.APPROVED


# ─────────────── model override at agents/base.py ────────────────────────


def test_resolve_model_id_live_mode(monkeypatch):
    from castelino.agents.base import _resolve_model_id
    from castelino.config import get_settings
    monkeypatch.delenv(BACKTEST_AS_OF_ENV, raising=False)
    cfg = get_settings()
    assert _resolve_model_id(cfg, "reasoning") == cfg.models.reasoning
    assert _resolve_model_id(cfg, "fast") == cfg.models.fast


def test_resolve_model_id_backtest_mode_overrides(monkeypatch):
    from castelino.agents.base import _resolve_model_id
    from castelino.config import get_settings
    monkeypatch.setenv(BACKTEST_AS_OF_ENV, "2024-03-15")
    cfg = get_settings()
    # reasoning → gpt-4o; fast + significance → gpt-4o-mini (matches live tier split)
    assert _resolve_model_id(cfg, "reasoning") == cfg.backtest.reasoning_model
    assert _resolve_model_id(cfg, "significance") == cfg.backtest.fast_model
    assert _resolve_model_id(cfg, "fast") == cfg.backtest.fast_model
