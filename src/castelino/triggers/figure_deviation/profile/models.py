"""FigureProfile data models.

Mirrors the shape of `agents/personas/models.py::PersonaCard` but for
tracked-figure profiles. The `RetrievedChunk` carries source provenance so
the audit trail can reconstruct exactly what context Stage B / the
Hypothesis Agent saw at decision time.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class FigureCard(BaseModel):
    """Auto-generated header summarising a figure's profile.

    Included verbatim in every Stage B / Hypothesis prompt so the LLM has
    the figure's belief summary, decision framework, signature phrases,
    and rhetorical-tell catalogue without having to retrieve them.
    """

    figure_id: str
    version: int = Field(ge=1)
    belief_summary: str
    decision_framework: str
    signature_phrases: list[str] = Field(default_factory=list)
    rhetorical_tells: dict[str, list[str]] = Field(
        default_factory=dict,
        description=(
            "Mapping {category: [phrases]} — e.g. 'committed': ['starting "
            "Monday', 'by next week'], 'exploratory': ['looking at']."
        ),
    )


class FigureProfileMeta(BaseModel):
    """Per-figure version + source manifest persisted at version.json."""

    figure_id: str
    version: int = Field(ge=1)
    source_manifest: list[str] = Field(default_factory=list)
    last_built: datetime


class RetrievedChunk(BaseModel):
    """A chunk surfaced by a profile query. Provenance fields support the
    audit trail that the post-hypothesis HITL gate displays to the
    reviewer."""

    chunk_id: str
    text: str
    section: str            # e.g. "tweet_outcome_examples", "behavioural_patterns"
    similarity: float = Field(ge=0.0, le=1.0)
    source_doc: str         # filename in sources/ that contributed this chunk


class Chunk(BaseModel):
    """An ingestion-time chunk being upserted into the store. Carries the
    pre-embedding metadata; the store handles embedding + persistence."""

    id: str
    text: str
    section: str
    source_doc: str
