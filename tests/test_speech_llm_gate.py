"""Tests for Stage B LLM confirmation classifier."""
from __future__ import annotations

from castelino.agents.base import FakeLLMClient
from castelino.triggers.speech.llm_gate import (
    SpeechShiftClassification,
    classify_speech_shift,
)
from castelino.triggers.speech.models import BaselineVector


BL = BaselineVector(
    hawkish_dovish_mean=-0.15,
    hawkish_dovish_std=0.20,
    key_phrase_frequencies={},
    hedging_density=0.18,
)


def _canned_handler(canned: SpeechShiftClassification):
    def _h(system: str, user: str) -> SpeechShiftClassification:
        return canned
    return _h


def test_classify_speech_shift_returns_structured_output():
    canned = SpeechShiftClassification(
        is_shift=True,
        direction="hawkish",
        magnitude=0.7,
        decisive_phrase="Further policy firming may be warranted.",
        rationale="Out-of-character for Powell's recent baseline.",
    )
    fake = FakeLLMClient()
    fake.register("SpeechShiftClassification", _canned_handler(canned))

    result = classify_speech_shift(
        client=fake,
        full_name="Jerome H. Powell",
        baseline=BL,
        rolling_window_text="Further firming may be warranted...",
    )
    assert result.is_shift is True
    assert result.direction == "hawkish"
    assert 0.0 <= result.magnitude <= 1.0
    assert result.decisive_phrase
    assert result.rationale


def test_classify_speech_shift_passes_baseline_into_prompt():
    canned = SpeechShiftClassification(
        is_shift=False,
        direction="neutral",
        magnitude=0.0,
        decisive_phrase="",
        rationale="Consistent with baseline.",
    )
    fake = FakeLLMClient()
    fake.register("SpeechShiftClassification", _canned_handler(canned))

    classify_speech_shift(
        client=fake,
        full_name="Jerome H. Powell",
        baseline=BL,
        rolling_window_text="The economy remains in a good place.",
    )

    assert len(fake.call_log) == 1
    schema_name, _model, _system, user = fake.call_log[0]
    assert schema_name == "SpeechShiftClassification"
    assert "Jerome H. Powell" in user
    # baseline mean -0.15 should appear, formatted with sign
    assert "-0.15" in user
    assert "0.20" in user
    assert "The economy remains in a good place." in user
