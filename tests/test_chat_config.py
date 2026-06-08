from castelino.agents.chat.models import CommandName
from castelino.config import get_settings
from pydantic import BaseModel


def test_chat_config_defaults():
    cfg = get_settings()
    assert cfg.chat.max_context_turns == 12