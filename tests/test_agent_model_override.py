from pydantic import BaseModel

from castelino.agents import base


class Out(BaseModel):
    x: int


class _Probe(base.StructuredAgent[Out]):
    name = "probe"
    output_schema = Out
    tier = "fast"
    model = "gpt-6-sol"

    def system_prompt(self) -> str:
        return "s"

    def user_prompt(self, **ctx) -> str:
        return "u"


def test_model_attribute_overrides_tier(monkeypatch):
    fake = base.FakeLLMClient()
    fake.register("Out", lambda s, u: Out(x=1))
    monkeypatch.setattr(base, "_LIVE_CLIENT_SINGLETON", fake)
    _Probe()()
    assert fake.call_log[-1][1] == "gpt-6-sol"


def test_no_model_attribute_uses_tier(monkeypatch):
    fake = base.FakeLLMClient()
    fake.register("Out", lambda s, u: Out(x=1))
    monkeypatch.setattr(base, "_LIVE_CLIENT_SINGLETON", fake)
    p = _Probe()
    p.model = None
    p()
    assert fake.call_log[-1][1] == base._resolve_model_id(base.get_settings(), "fast")
