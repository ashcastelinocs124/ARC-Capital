"""Tests for the market_overview chat command handler."""
from castelino.agents.chat.models import CommandName
from castelino.agents.chat.registry import REGISTRY, _market_overview, _MARKET_OVERVIEW_QUERY
from castelino.agents.chat.repl import _is_market_shortcut
from castelino.agents.research.deep.sonar_client import FakeSonarClient, SonarResult


def test_market_overview_in_registry():
    assert CommandName.market_overview in REGISTRY
    spec = REGISTRY[CommandName.market_overview]
    assert spec.mutating is False
    assert spec.required_args == []
    assert "cross-asset" in spec.help.lower()


def test_market_overview_query_is_fixed():
    q = _MARKET_OVERVIEW_QUERY.lower()
    assert "equities" in q
    assert "rates" in q
    assert "commodities" in q
    assert "crypto" in q
    assert "credit" in q
    assert "fx" in q
    assert "spx" in q
    assert "wti" in q
    assert "btcusd" in q
    assert "dxy" in q


def test_handler_returns_sonar_content(monkeypatch):
    fake = FakeSonarClient()
    fake.register("market snapshot", SonarResult(
        content="- Equities: flat",
        sources=[],
    ))
    monkeypatch.setattr("castelino.agents.chat.registry.PerplexitySonarClient",
                        lambda: fake)

    result = _market_overview({})
    assert "Equities" in result


def test_handler_returns_failure_on_empty_sonar(monkeypatch):
    fake = FakeSonarClient()
    monkeypatch.setattr("castelino.agents.chat.registry.PerplexitySonarClient",
                        lambda: fake)

    result = _market_overview({})
    assert "couldn't get current market coverage" in result.lower()


def test_shortcut_matches_plain_market_query():
    assert _is_market_shortcut("how is the market")
    assert _is_market_shortcut("how's the market today?")
    assert _is_market_shortcut("give me a market update please")
    assert _is_market_shortcut("broad market snapshot")


def test_shortcut_skips_when_persona_mentioned():
    assert not _is_market_shortcut("Dalio, how is the market?")
    assert not _is_market_shortcut("hey dalio how is the market today")
    assert not _is_market_shortcut("krugman what's the market overview?")
    assert not _is_market_shortcut("what does druckenmiller think about markets")
    assert not _is_market_shortcut("summers, how are markets looking?")


def test_shortcut_skips_when_no_market_phrase():
    assert not _is_market_shortcut("hello")
    assert not _is_market_shortcut("dalio what do you think?")
