from castelino.agents.base import FakeLLMClient
from castelino.agents.chat.models import AssistantTurn, Action, CommandName
from castelino.agents.chat.router import build_system_prompt, route


def test_system_prompt_contains_all_commands():
    prompt = build_system_prompt()
    assert "status" in prompt
    assert "CONFIRMED" in prompt  # Verify mutating commands are marked


def test_route_returns_structured_output():
    fake = FakeLLMClient()
    fake.register(
        "AssistantTurn",
        lambda s, u: AssistantTurn(
            reply="Here's your status report",
            action=Action(command=CommandName.status)
        )
    )
    
    turn = route(
        client=fake,
        model="test",
        transcript=[("user", "show status")]
    )
    
    assert turn.reply == "Here's your status report"
    assert turn.action.command == CommandName.status