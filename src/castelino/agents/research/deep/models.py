from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ResearchStatus(StrEnum):
    CREATED = "created"
    AWAITING_ANSWERS = "awaiting_answers"
    RESEARCHING = "researching"
    SYNTHESIZING = "synthesizing"
    COMPLETE = "complete"
    FAILED = "failed"


class SourceRef(BaseModel):
    """A web source backing a finding. Web-oriented (vs persona Citation)."""
    title: str = ""
    url: str = ""
    snippet: str = ""


class ClarificationQuestion(BaseModel):
    question: str
    why: str = ""


class ClarifierResult(BaseModel):
    """Output of the Clarifier agent."""
    reworded_query: str
    clarifying_questions: list[ClarificationQuestion] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)  # used in --no-clarify mode


class SubQuestion(BaseModel):
    id: str
    text: str
    rationale: str = ""
    round: int = 1


class DecompositionResult(BaseModel):
    """Output of the Lead/decomposer agent."""
    sub_questions: list[SubQuestion] = Field(default_factory=list)


class SubFinding(BaseModel):
    sub_question_id: str
    summary: str = ""
    key_points: list[str] = Field(default_factory=list)
    citations: list[SourceRef] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    error: str | None = None


class ReflectionResult(BaseModel):
    is_sufficient: bool
    gaps: list[str] = Field(default_factory=list)
    new_sub_questions: list[SubQuestion] = Field(default_factory=list)


class DeepResearchReport(BaseModel):
    exec_summary: str
    findings: list[SubFinding] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    caveats: list[str] = Field(default_factory=list)
    gaps_remaining: list[str] = Field(default_factory=list)


class ResearchRound(BaseModel):
    round: int
    sub_questions: list[SubQuestion] = Field(default_factory=list)
    findings: list[SubFinding] = Field(default_factory=list)
    reflection: ReflectionResult | None = None


class ResearchSession(BaseModel):
    id: str
    original_query: str
    reworded_query: str = ""
    status: ResearchStatus = ResearchStatus.CREATED
    clarifying_questions: list[ClarificationQuestion] = Field(default_factory=list)
    answers: dict[str, str] = Field(default_factory=dict)
    rounds: list[ResearchRound] = Field(default_factory=list)
    report: DeepResearchReport | None = None
    sonar_calls_used: int = 0
    error: str | None = None
    created_at: datetime
    updated_at: datetime
