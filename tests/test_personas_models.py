from datetime import datetime, UTC
from castelino.agents.personas.models import (
    Citation, PersonaMessage, PersonaConversation,
    PanelResponse, Disagreement, PanelSynthesis, PanelDiscussion,
    FamousCall, PersonaCard,
)

def test_citation_roundtrips():
    c = Citation(source="buffett_2008.pdf#p4", snippet="hold forever", score=0.83)
    assert Citation.model_validate_json(c.model_dump_json()) == c

def test_persona_message_with_citations():
    m = PersonaMessage(
        role="assistant", text="Hold quality.",
        timestamp=datetime.now(UTC),
        citations=[Citation(source="x", snippet="y", score=0.9)],
    )
    assert m.role == "assistant"
    assert len(m.citations) == 1

def test_panel_synthesis_schema():
    s = PanelSynthesis(
        consensus=["direction is right"],
        disagreements=[Disagreement(axis="sizing",
                                    positions={"a": "1/3", "b": "2/3"})],
        strongest_objection="Krugman: supply shocks are transitory",
        recommended_modifications=["halve initial size"],
    )
    assert s.disagreements[0].positions["a"] == "1/3"

def test_persona_card_round_trip():
    card = PersonaCard(
        persona_id="buffett", full_name="Warren Buffett",
        role="Value investor", tenure="1965-present",
        belief_summary="hold quality companies forever",
        decision_framework=["margin of safety", "circle of competence"],
        signature_phrases=["intrinsic value"],
        famous_calls=[FamousCall(date="2008", description="GS preferred")],
        voice_notes="folksy, anecdotal",
    )
    assert PersonaCard.model_validate_json(card.model_dump_json()) == card
