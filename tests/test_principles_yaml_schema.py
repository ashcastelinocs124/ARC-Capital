"""Smoke tests on `data/core_principles.md`.

We don't test rule semantics here (Guard tests do that); we test that the
constitution is present, has both rule sections, and that every hard rule has
a section heading the Guard can grep for.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PRINCIPLES = ROOT / "data" / "core_principles.md"


@pytest.fixture(scope="module")
def text() -> str:
    assert PRINCIPLES.exists(), "core_principles.md missing"
    return PRINCIPLES.read_text()


def test_has_hard_and_soft_sections(text):
    assert "## HARD RULES" in text
    assert "## SOFT RULES" in text


@pytest.mark.parametrize("rule_id", ["H1", "H2", "H3", "H4", "H5"])
def test_hard_rule_present(text, rule_id):
    assert f"### {rule_id}." in text, f"Hard rule {rule_id} missing"


@pytest.mark.parametrize("rule_id", ["S1", "S2", "S3", "S4", "S5"])
def test_soft_rule_present(text, rule_id):
    assert f"### {rule_id}." in text, f"Soft rule {rule_id} missing"


def test_concrete_thresholds_are_named(text):
    """The Guard greps these strings; if they get rephrased the Guard breaks."""
    for needle in ["5%", "40%", "10%", "$50M", "1% of 30-day ADV", "VIX > 40"]:
        assert needle in text, f"missing constitutional threshold: {needle}"
