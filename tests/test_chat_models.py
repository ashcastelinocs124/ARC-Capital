from castelino.agents.chat.models import AssistantTurn, Action, CommandName


def test_assistant_turn_plain_reply_has_no_action():
    t = AssistantTurn(reply="hello")
    assert t.reply == "hello"
    assert t.action is None


def test_action_carries_command_and_args():
    a = Action(command=CommandName.run, args={"headline": "CPI hot"})
    assert a.command is CommandName.run
    assert a.args["headline"] == "CPI hot"


def test_command_name_is_closed_set():
    # 'none' is the explicit "just talk / no action" member
    assert CommandName.none.value == "none"
    assert "status" in {c.value for c in CommandName}