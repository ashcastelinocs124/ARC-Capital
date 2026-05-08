from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Citation(BaseModel):
    source: str
    snippet: str
    score: float = Field(ge=0.0, le=1.0)


class PersonaMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str
    timestamp: datetime
    citations: list[Citation] = Field(default_factory=list)


class PersonaConversation(BaseModel):
    entry_id: str
    persona_id: str
    started_at: datetime
    messages: list[PersonaMessage] = Field(default_factory=list)


class PanelResponse(BaseModel):
    persona_id: str
    text: str
    citations: list[Citation] = Field(default_factory=list)


class Disagreement(BaseModel):
    axis: str
    positions: dict[str, str]


class PanelSynthesis(BaseModel):
    consensus: list[str] = Field(default_factory=list)
    disagreements: list[Disagreement] = Field(default_factory=list)
    strongest_objection: str = ""
    recommended_modifications: list[str] = Field(default_factory=list)


class PanelDiscussion(BaseModel):
    entry_id: str
    question: str
    responses: list[PanelResponse]
    synthesis: PanelSynthesis
    created_at: datetime


class FamousCall(BaseModel):
    date: str
    description: str


class PersonaCard(BaseModel):
    persona_id: str
    full_name: str
    role: str
    tenure: str = ""
    belief_summary: str
    decision_framework: list[str] = Field(default_factory=list)
    signature_phrases: list[str] = Field(default_factory=list)
    famous_calls: list[FamousCall] = Field(default_factory=list)
    voice_notes: str = ""
