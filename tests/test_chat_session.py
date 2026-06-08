from castelino.agents.base import FakeLLMClient
from castelino.agents.chat.models import AssistantTurn, CommandName
from castelino.agents.chat.session import ChatSession


def test_session_handles_plain_conversation():
    fake = FakeLLMClient()
    fake.register("AssistantTurn", lambda s, u: AssistantTurn(reply="Hello there!"))
    session = ChatSession(client=fake)
    result = session.handle_turn("Hi")
    assert result.reply == "Hello there!"
    assert result.command is None
    assert not result.executed


def test_session_requires_confirmation_for_mutating_commands():
    fake = FakeLLMClient()
    fake.register(
        "AssistantTurn",
        lambda s, u: AssistantTurn(
            reply="Ready to reset",
            command=CommandName.reset,
            args={},
        )
    )
    confirm_calls = []
    session = ChatSession(
        client=fake,
        confirm=lambda p: confirm_calls.append(p) or False
    )
    result = session.handle_turn("reset everything")
    assert result.command == CommandName.reset
    assert not result.executed
    assert len(confirm_calls) == 1
    assert "ckm reset" in confirm_calls[0]