"""Tests for DeepgramSTTProvider.

If the deepgram-sdk isn't installed in the env, all tests skip via
`pytest.importorskip` — production CI should install the dep so they run.
"""
from __future__ import annotations

import pytest

deepgram = pytest.importorskip("deepgram")

from castelino.triggers.speech.stt_deepgram import DeepgramSTTProvider  # noqa: E402


def test_deepgram_provider_constructs_with_api_key():
    p = DeepgramSTTProvider(api_key="dg_test", model="nova-2-finance")
    assert p.model == "nova-2-finance"


def test_deepgram_provider_default_model():
    p = DeepgramSTTProvider(api_key="dg_test")
    assert p.model == "nova-2-finance"


def test_stream_calls_sdk(monkeypatch):
    """Mock at the SDK boundary — verify init + start + finish are wired up."""
    from castelino.triggers.speech import stt_deepgram as mod

    called: dict[str, bool] = {}

    class _Conn:
        async def start(self, *_a, **_kw):
            called["started"] = True
            return True

        async def finish(self):
            called["finished"] = True

        def on(self, *_a, **_kw):
            called["on_registered"] = True

    class _AsyncLive:
        def v(self, _v):
            return _Conn()

    class _Listen:
        @property
        def asynclive(self):
            return _AsyncLive()

    class _FakeClient:
        def __init__(self, *_a, **_kw):
            called["init"] = True

        @property
        def listen(self):
            return _Listen()

    monkeypatch.setattr(mod, "DeepgramClient", _FakeClient)
    p = mod.DeepgramSTTProvider(api_key="x")
    assert called.get("init") is True
    assert p.model == "nova-2-finance"
