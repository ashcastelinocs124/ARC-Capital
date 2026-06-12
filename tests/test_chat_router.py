from castelino.agents.base import FakeLLMClient
from castelino.agents.chat.models import AssistantTurn, CommandName
from castelino.agents.chat.router import build_system_prompt, route


def test_system_prompt_contains_all_commands():
    prompt = build_system_prompt()
    assert "status" in prompt
    assert "MUTATING" in prompt
    assert "market_overview" in prompt


def test_system_prompt_routing_guidance_present():
    prompt = build_system_prompt()
    assert "market_overview" in prompt
    assert "cross-asset" in prompt or "ROUTING RULES" in prompt


def test_system_prompt_distinguishes_market_from_forecast():
    prompt = build_system_prompt()
    assert "market_overview" in prompt
    assert "forecast_regime" in prompt
    assert "forecast_risk" in prompt


def test_route_returns_structured_output():
    fake = FakeLLMClient()
    fake.register(
        "AssistantTurn",
        lambda s, u: AssistantTurn(
            reply="Here's your status report",
            command=CommandName.status,
            args={},
        )
    )

    turn = route(
        client=fake,
        model="test",
        transcript=[("user", "show status")]
    )

    assert turn.reply == "Here's your status report"
    assert turn.command == CommandName.status


def test_system_prompt_mentions_persona_override():
    prompt = build_system_prompt()
    assert "PERSONA OVERRIDE" in prompt
    assert "Dalio" in prompt
    assert "Krugman" in prompt
    assert "ALWAYS beats" in prompt
    assert "market_overview" in prompt


def test_route_persona_query_dispatches_to_discuss():
    fake = FakeLLMClient()
    fake.register(
        "AssistantTurn",
        lambda s, u: AssistantTurn(
            reply="Let me ask Dalio about that.",
            command=CommandName.discuss,
            args={"query": "Dalio, how is the market?"},
        )
    )

    turn = route(
        client=fake,
        model="test",
        transcript=[("user", "Dalio, how is the market?")]
    )

    assert turn.reply == "Let me ask Dalio about that."
    assert turn.command == CommandName.discuss
    assert turn.args is not None
    assert "Dalio" in turn.args["query"]