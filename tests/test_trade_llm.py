import pytest
from pydantic import BaseModel

from castelino.agents.trade import llm
from tests.trade_fakes import FakeClient, parsed, said


class Out(BaseModel):
    x: int


@pytest.fixture
def fake(monkeypatch):
    c = FakeClient()
    monkeypatch.setattr(llm, "_client", lambda model: c)
    return c


def test_openai_call_is_priced_from_tokens(fake):
    fake.script = [parsed(Out(x=1), tin=1_000_000, tout=100_000)]
    m = llm.Meter()
    assert llm.structured("a", "gpt-6-sol", [{"role": "user", "content": "q"}], Out, m).x == 1
    assert m.total == pytest.approx(2.0 + 1.0)  # $2/M in, $10/M out
    assert "extra_body" not in fake.calls[0][1]


def test_openrouter_call_sends_provider_rules_and_uses_reported_cost(fake, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    fake.script = [parsed(Out(x=2), cost=0.0123)]
    m = llm.Meter()
    llm.structured("a", "deepseek/deepseek-v4-pro", [], Out, m, fallback="gpt-6-sol")
    body = fake.calls[0][1]["extra_body"]
    assert body["provider"] == {
        "data_collection": "deny",
        "require_parameters": True,
        "sort": "price",
    }
    assert body["usage"] == {"include": True}
    assert m.total == pytest.approx(0.0123)


def test_missing_openrouter_key_routes_to_fallback(fake, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    fake.script = [parsed(Out(x=3))]
    m = llm.Meter()
    llm.structured("trade_bull", "deepseek/deepseek-v4-pro", [], Out, m, fallback="gpt-6-sol")
    assert fake.calls[0][1]["model"] == "gpt-6-sol"
    assert m.fallbacks == [
        "trade_bull: deepseek/deepseek-v4-pro → gpt-6-sol (no OPENROUTER_API_KEY)"
    ]


def test_openrouter_failure_retries_once_then_falls_back(fake, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    fake.script = [RuntimeError("502"), RuntimeError("502"), parsed(Out(x=4))]
    m = llm.Meter()
    out = llm.structured("a", "deepseek/deepseek-v4-pro", [], Out, m, fallback="gpt-6-sol")
    assert out.x == 4
    assert [c[1]["model"] for c in fake.calls] == ["deepseek/deepseek-v4-pro"] * 2 + ["gpt-6-sol"]
    assert m.fallbacks and "502" in m.fallbacks[0]


def test_chat_passes_tools_and_returns_the_message(fake):
    fake.script = [said("hi")]
    msg = llm.chat(
        "a", "gpt-6-luna", [], llm.Meter(), tools=[{"type": "function"}], tool_choice="auto"
    )
    assert msg.content == "hi" and fake.calls[0][1]["tools"] == [{"type": "function"}]


def test_all_attempts_failing_raises_the_last_error(fake):
    fake.script = [RuntimeError("boom")]
    with pytest.raises(RuntimeError, match="boom"):
        llm.structured("a", "gpt-6-sol", [], Out, llm.Meter())
