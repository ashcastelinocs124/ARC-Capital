"""Topic consultants: one per typed topic (spec docs/superpowers/specs/2026-10-22-topic-consultants/).

A consultant keeps a daily file of cited facts and a two-part thesis — what is happening, then what could
happen — written as analysis, not data points. Every fact id is `{code}-{yyyymmdd}-{n}`, so the day a fact
was gathered is readable from its id and ids never clash with the Daily Update's own facts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from castelino.agents.update.models import Fact


class Company(BaseModel):
    name: str
    ticker: str


class Watchlist(BaseModel):
    companies: list[Company]
    series: list[str]  # "fred:ID" or "yahoo:TICKER"
    queries: list[str]


class Consultant(BaseModel):
    slug: str
    code: str  # "K1": prefixes every fact id
    topic: str
    watchlist: Watchlist
    status: Literal["building", "active", "paused", "failed"]
    created: str  # ISO date
    error: str | None = None


class Part(BaseModel):
    text: str
    fact_ids: list[str]


class ThesisDraft(BaseModel):  # LLM output (closed schema: no defaults)
    happening: Part
    lean: Part
    alternative: Part
    change_mind: Part
    reason: str


class Thesis(ThesisDraft):
    updated: str
    version: int


class HistoryLine(BaseModel):
    day: str
    kind: Literal["start", "daily", "weekly"]
    verdict: Literal["started", "updated", "held", "skipped", "week"]
    p_thesis: float | None = None
    p_memory: float | None = None
    reason: str = ""
    before: str | None = None
    after: str | None = None
    moved: list[str] = Field(default_factory=list)
    deleted: list[str] = Field(default_factory=list)


class Ask(BaseModel):
    at: str
    asker: str
    question: str
    fact_ids: list[str]


class DayLog(BaseModel):
    day: str
    cost_usd: float = 0.0
    built: bool = False
    reviewed: bool = False
    asks: list[Ask] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class NoteConsult(BaseModel):
    """What the Daily Update gets from the consultants for one day (saved per day, so a rebuild reuses it)."""

    watch_md: str = ""
    prompt_md: str = ""
    facts: list[Fact] = Field(default_factory=list)
    codes: dict[str, str] = Field(default_factory=dict)  # slug → code
    names: dict[str, str] = Field(default_factory=dict)  # slug → topic
