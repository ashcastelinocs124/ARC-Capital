from castelino.triggers.speech.queue import speech_trigger_queue
from castelino.memory.schemas import TriggerRecord, TriggerSource


def test_queue_offer_and_drain_round_trip():
    speech_trigger_queue.clear()
    speech_trigger_queue.offer(TriggerRecord(
        source=TriggerSource.SPEECH_DEVIATION,
        headline="x", significance=0.8,
        asset_classes_affected=[], one_sentence_reason="x",
    ))
    drained = speech_trigger_queue.drain()
    assert len(drained) == 1
    assert speech_trigger_queue.drain() == []


def test_tick_fires_pipeline_when_speech_trigger_present(monkeypatch):
    from castelino.triggers import runner as r
    from castelino.triggers.speech.queue import speech_trigger_queue

    fired = []
    monkeypatch.setattr(r, "fire_pipeline", lambda trg, **kw: fired.append(trg) or {})
    monkeypatch.setattr(r, "fetch_recent", lambda **kw: [])
    monkeypatch.setattr(r.calmod, "events_due", lambda: [])
    monkeypatch.setattr(r, "_check_regime_shift", lambda s: None)
    monkeypatch.setattr(r, "_check_conviction", lambda lf: (None, []))
    monkeypatch.setattr(r, "_trigger_cron_fallback", lambda lf: None)
    # Best-effort: some helpers may not exist; only patch those that do.

    speech_trigger_queue.clear()
    speech_trigger_queue.offer(TriggerRecord(
        source=TriggerSource.SPEECH_DEVIATION,
        headline="Powell hawkish shift", significance=0.85,
        asset_classes_affected=[], one_sentence_reason="x",
    ))
    out = r.tick()
    assert out == "speech"
    assert fired and fired[0].source.value == "speech_deviation"
