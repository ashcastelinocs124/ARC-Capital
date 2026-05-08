from castelino.config import get_settings


def test_personas_config_has_defaults():
    s = get_settings()
    assert s.personas.enabled is True
    assert s.personas.chat_model == "gpt-4o-mini"
    assert s.personas.synthesis_model == "gpt-4o"
    assert s.personas.embedding_model == "text-embedding-3-small"
    assert s.personas.retrieval_top_k == 6
    assert s.personas.chunk_max_tokens == 400
    assert "druckenmiller" in s.personas.active_roster
    assert "tudor_jones" in s.personas.active_roster


def test_personas_roster_macro_only():
    """Roster is macro investors + economists. Buffett (value) excluded."""
    s = get_settings()
    expected = {"krugman", "el_erian", "summers",
                "druckenmiller", "dalio", "tudor_jones"}
    assert expected.issubset(set(s.personas.active_roster))
    assert "buffett" not in s.personas.active_roster
