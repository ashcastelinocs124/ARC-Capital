"""End-to-end replay: feed a recorded transcript through the speech emitter
and assert it emits exactly one trigger on the dovish→hawkish pivot."""
from datetime import datetime, UTC
from pathlib import Path

from castelino.agents.base import FakeLLMClient
from castelino.triggers.speech.emitter import SpeechTriggerEmitter
from castelino.triggers.speech.llm_gate import SpeechShiftClassification
from castelino.triggers.speech.models import (
    BaselineVector,
    SpeechSegment,
)
from castelino.triggers.speech.scorer import split_sentences


def test_replay_dovish_to_hawkish_pivot_emits_one_trigger():
    text = Path("tests/fixtures/fed/powell_replay_transcript.txt").read_text()
    sentences = split_sentences(text)
    assert len(sentences) > 30, "fixture too thin"

    baseline = BaselineVector(
        hawkish_dovish_mean=-0.15,
        hawkish_dovish_std=0.20,
        key_phrase_frequencies={},
        hedging_density=0.18,
    )
    fake = FakeLLMClient()
    fake.register(
        "SpeechShiftClassification",
        lambda system, user: SpeechShiftClassification(
            is_shift=True,
            direction="hawkish",
            magnitude=0.7,
            decisive_phrase="Further firming may be warranted.",
            rationale="ok",
        ),
    )
    em = SpeechTriggerEmitter(
        speaker_id="powell",
        full_name="Jerome H. Powell",
        baseline=baseline,
        threshold_sigma=1.5,
        llm_client=fake,
    )
    for s in sentences:
        em.ingest(
            SpeechSegment(
                speaker_id="powell",
                text=s,
                timestamp=datetime.now(UTC),
                event_id="fomc-2026-04",
            )
        )
    assert len(em.triggers) == 1, (
        f"expected exactly 1 trigger on dovish→hawkish pivot, "
        f"got {len(em.triggers)}"
    )
    assert em.triggers[0].source.value == "speech_deviation"
    assert "hawkish" in em.triggers[0].headline.lower()
