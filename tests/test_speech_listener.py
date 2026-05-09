import asyncio
from datetime import datetime, UTC
from castelino.triggers.figure_deviation.listener import listen
from castelino.triggers.figure_deviation.stt import FakeSTTProvider, TranscriptEvent


def test_listener_emits_per_sentence():
    canned = [
        TranscriptEvent(text="Today the Committee met.", timestamp=datetime.now(UTC), is_final=True),
        TranscriptEvent(text="Further firming may be", timestamp=datetime.now(UTC), is_final=False),
        TranscriptEvent(text="Further firming may be warranted.", timestamp=datetime.now(UTC), is_final=True),
    ]
    provider = FakeSTTProvider(canned=canned)

    async def go():
        out = []
        async for seg in listen(
            provider=provider, audio_url="fake://", speaker_id="powell",
            event_id="fomc-2026-04",
        ):
            out.append(seg)
        return out

    out = asyncio.run(go())
    assert len(out) >= 2
    # First final sentence must be Today's; second must contain "warranted"
    texts = [s.text for s in out]
    assert any("Today the Committee met" in t for t in texts)
    assert any("warranted" in t for t in texts)
    assert all(seg.event_id == "fomc-2026-04" for seg in out)
    assert all(seg.speaker_id == "powell" for seg in out)
