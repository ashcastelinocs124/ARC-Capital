from castelino.agents.chat.models import CommandName
from castelino.agents.chat.registry import REGISTRY
from castelino.execution.portfolio import Portfolio


def test_status_callable_returns_nav_summary(tmp_path, monkeypatch):
    # status reads Portfolio.load(); a fresh book reports its NAV string
    out = REGISTRY[CommandName.status].run({})
    assert "NAV" in out


def test_queue_callable_returns_string():
    out = REGISTRY[CommandName.queue].run({})
    assert isinstance(out, str)  # "No pending approvals." on a clean queue