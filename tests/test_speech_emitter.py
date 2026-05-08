from datetime import datetime, UTC

from castelino.agents.base import FakeLLMClient
from castelino.triggers.speech.emitter import SpeechTriggerEmitter
from castelino.triggers.speech.llm_gate import SpeechShiftClassification
from castelino.triggers.speech.models import BaselineVector, SpeechSegment


BL = BaselineVector(
    hawkish_dovish_mean=-0.15, hawkish_dovish_std=0.20,
    key_phrase_frequencies={}, hedging_density=0.18,
)

CANNED_SHIFT = SpeechShiftClassification(
    is_shift=True, direction="hawkish", magnitude=0.7,
    decisive_phrase="Further policy firming may be warranted.", rationale="ok",
)
CANNED_NO_SHIFT = SpeechShiftClassification(
    is_shift=False, direction="neutral", magnitude=0.0,
    decisive_phrase="", rationale="baseline",
)


def _seg(text: str, event_id: str = "fomc-2026-04") -> SpeechSegment:
    return SpeechSegment(
        speaker_id="powell", text=text, timestamp=datetime.now(UTC),
        event_id=event_id,
    )


def _fake_with(canned: SpeechShiftClassification) -> FakeLLMClient:
    fake = FakeLLMClient()
    fake.register("SpeechShiftClassification", lambda system, user: canned)
    return fake


def test_emitter_below_threshold_no_llm_no_trigger():
    fake = _fake_with(CANNED_NO_SHIFT)
    em = SpeechTriggerEmitter(
        speaker_id="powell", full_name="J.P.", baseline=BL,
        threshold_sigma=1.5, llm_client=fake,
    )
    for txt in ["Today the Committee met.", "Hello, everyone."]:
        em.ingest(_seg(txt))
    assert em.triggers == []
    assert fake.stats.n_calls == 0


def test_emitter_above_threshold_with_confirmation_emits_trigger():
    fake = _fake_with(CANNED_SHIFT)
    em = SpeechTriggerEmitter(
        speaker_id="powell", full_name="Jerome H. Powell", baseline=BL,
        threshold_sigma=1.5, llm_client=fake,
    )
    for txt in [
        "Further firming may be warranted.",
        "Inflation persistent and elevated.",
        "We will act decisively.",
        "Persistent inflation requires policy firming.",
        "Remain restrictive.",
    ]:
        em.ingest(_seg(txt))
    assert len(em.triggers) == 1
    trg = em.triggers[0]
    assert trg.source.value == "speech_deviation"


def test_emitter_cooldown_caps_at_one_trigger_per_event():
    fake = _fake_with(CANNED_SHIFT)
    em = SpeechTriggerEmitter(
        speaker_id="powell", full_name="J.P.", baseline=BL,
        threshold_sigma=1.5, llm_client=fake,
    )
    for txt in ["Further firming may be warranted."] * 20:
        em.ingest(_seg(txt))
    assert len(em.triggers) == 1
