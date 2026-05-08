import asyncio
from datetime import datetime, UTC
from castelino.triggers.speech.stt import FakeSTTProvider, TranscriptEvent


def test_fake_stt_yields_canned_sequence():
    canned = [
        TranscriptEvent(text="Hello.", timestamp=datetime.now(UTC), is_final=True),
        TranscriptEvent(text="Further firming.", timestamp=datetime.now(UTC), is_final=True),
    ]
    provider = FakeSTTProvider(canned=canned)

    async def collect():
        out = []
        async for ev in provider.stream(audio_url="fake://"):
            out.append(ev)
        return out

    out = asyncio.run(collect())
    assert len(out) == 2
    assert out[1].text == "Further firming."
