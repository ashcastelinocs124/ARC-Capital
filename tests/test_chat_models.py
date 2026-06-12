from castelino.agents.chat.models import AssistantTurn, CommandName


def test_assistant_turn_plain_reply_has_no_action():
    t = AssistantTurn(reply="hello")
    assert t.reply == "hello"
    assert t.command is None
    assert t.args is None


def test_assistant_turn_carries_command_and_args():
    t = AssistantTurn(reply="doing it", command=CommandName.run, args={"headline": "CPI hot"})
    assert t.command is CommandName.run
    assert t.args["headline"] == "CPI hot"


def test_command_name_is_closed_set():
    assert CommandName.none.value == "none"
    assert "status" in {c.value for c in CommandName}


def test_market_overview_exists():
    assert CommandName.market_overview.value == "market_overview"