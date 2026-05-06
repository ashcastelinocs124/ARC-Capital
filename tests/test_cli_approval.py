"""Tests for approval CLI commands."""
import pytest
from typer.testing import CliRunner

from castelino.orchestrator.approval import ApprovalQueue, GateType
from castelino.orchestrator.cli import app

runner = CliRunner()


def test_queue_shows_pending(tmp_path):
    q = ApprovalQueue(state_dir=tmp_path)
    q.submit(gate=GateType.POST_HYPOTHESIS, payload={"thesis": "rates up"}, entry_id="H-001")

    result = runner.invoke(app, ["queue", "--state-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "H-001" in result.output
    assert "rates up" in result.output


def test_queue_empty(tmp_path):
    result = runner.invoke(app, ["queue", "--state-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "No pending" in result.output


def test_approve_command(tmp_path):
    q = ApprovalQueue(state_dir=tmp_path)
    q.submit(gate=GateType.POST_HYPOTHESIS, payload={"thesis": "test"}, entry_id="H-001")

    result = runner.invoke(app, ["approve", "H-001", "--state-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "Approved" in result.output


def test_reject_command(tmp_path):
    q = ApprovalQueue(state_dir=tmp_path)
    q.submit(gate=GateType.POST_DEBATE, payload={}, entry_id="V-001")

    result = runner.invoke(app, ["reject", "V-001", "--reason", "too risky", "--state-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "Rejected" in result.output
    assert "too risky" in result.output


def test_edit_command(tmp_path):
    q = ApprovalQueue(state_dir=tmp_path)
    q.submit(gate=GateType.POST_HYPOTHESIS, payload={"thesis": "original"}, entry_id="H-001")

    result = runner.invoke(app, ["edit", "H-001", "--thesis", "revised thesis", "--state-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "Edited" in result.output
    assert "revised thesis" in result.output


def test_approve_nonexistent(tmp_path):
    result = runner.invoke(app, ["approve", "NOPE", "--state-dir", str(tmp_path)])
    assert result.exit_code == 1
    assert "Not found" in result.output
