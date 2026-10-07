from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class Stage(StrEnum):
    IDLE = "idle"
    PLANNING = "planning"
    RESEARCHING = "researching"
    REVIEWING = "reviewing"
    WRITING = "writing"
    GUARDING = "guarding"
    CHARTING = "charting"
    DONE = "done"
    FAILED = "failed"


class Decision(StrEnum):
    PROMOTED = "promoted"
    KEPT = "kept"


class ModelGate(BaseModel):
    decision: Decision
    champion_brier: float | None = None
    challenger_brier: float | None = None
    reason: str = ""


class GateResult(BaseModel):
    growth: ModelGate
    inflation: ModelGate


class Release(BaseModel):
    series: str
    name: str
    latest: float
    prior: float | None = None
    change: float | None = None
    consensus: float | None = None  # not wired in v1
    surprise: float | None = None  # not wired in v1
    latest_period: str | None = None  # data month of `latest`, e.g. "Aug 2026"
    prior_period: str | None = None


class SectorTrend(BaseModel):
    sector: str
    r1w: float | None = None
    r1m: float | None = None
    r3m: float | None = None
    r6m: float | None = None
    r12m: float | None = None
    rel1m: float | None = None  # vs SPY, percentage points
    rel12m: float | None = None
    short_label: str = "n/a"
    long_label: str = "n/a"


class PredictionDelta(BaseModel):
    old: float | None = None
    new: float
    gate: str  # promoted | kept | unchanged


class MarketSnapshot(BaseModel):
    date: str
    releases: list[Release] = Field(default_factory=list)
    # asset class -> instrument id -> window ("1d"|"1w"|"1m") -> % (or bp for yields)
    asset_returns: dict[str, dict[str, dict[str, float | None]]] = Field(default_factory=dict)
    sectors: list[SectorTrend] = Field(default_factory=list)
    prediction: dict[str, PredictionDelta] = Field(default_factory=dict)
    data_gaps: list[str] = Field(default_factory=list)
    model_note: str | None = None


# ── LLM output (no dict fields: OpenAI structured output wants closed schemas) ──


class ThemeEdit(BaseModel):
    title: str
    text: str


class NewTheme(BaseModel):
    title: str
    text: str
    importance: int = Field(ge=1, le=5)


class SectorRead(BaseModel):
    sector: str
    text: str


class DailyUpdate(BaseModel):
    headline: str
    economy: str
    asset_classes: str
    predictions_changed: str
    themes_touched: list[ThemeEdit]
    new_themes: list[NewTheme]
    sector_reads: list[SectorRead]


class DailyRecord(BaseModel):
    date: str
    generated_at: str
    snapshot: MarketSnapshot
    update: DailyUpdate
    gate: GateResult | None = None


# ── v2: multi-agent Morning Note ──────────────────────────────────────────

AgentName = Literal["macro", "news", "alt"]


class Point(BaseModel):
    label: str
    value: float


class SeriesRef(BaseModel):
    kind: Literal[
        "daily", "release"
    ]  # daily → last 7 obs fetched; release → `points` (prev, latest)
    provider: Literal["fred", "yahoo", "polymarket", "bls"]
    id: str
    label: str
    points: list[Point] = Field(default_factory=list)


class Fact(BaseModel):
    """Something code knows: its text and every number in it come from data or a cited search line."""

    id: str
    text: str
    numbers: list[float]
    provenance: Literal["data", "reported"]
    series: SeriesRef | None = None
    source_title: str
    source_url: str


class FindingDraft(BaseModel):  # LLM output (closed schema: no defaults)
    claim: str
    figure: float | None
    unit: Literal["%", "bp", "pp", "level", ""]
    fact_ids: list[str]


class FindingDrafts(BaseModel):
    findings: list[FindingDraft]


class Finding(BaseModel):
    id: str
    agent: AgentName
    claim: str
    figure: float | None = None
    unit: str = ""
    provenance: Literal["data", "reported"]
    series: SeriesRef | None = None
    source_title: str
    source_url: str
    fact_ids: list[str]


class AgentOutput(BaseModel):
    facts: list[Fact]
    findings: list[Finding]
    snapshot: MarketSnapshot | None = None  # Macro only: feeds memory trend tables + releases


class Briefs(BaseModel):
    macro: str
    news: str
    alt: str


class FollowUp(BaseModel):
    agent: AgentName
    ask: str


class Review(BaseModel):
    done: bool
    followups: list[FollowUp]


class NoteItem(BaseModel):
    rank: int
    title: str
    body: str
    finding_ids: list[str]
    chart: str | None


class MorningNote(BaseModel):
    headline: str
    takeaways: list[str]
    items: list[NoteItem]
    themes_touched: list[ThemeEdit]
    new_themes: list[NewTheme]


class Exhibit(BaseModel):
    n: int
    finding_id: str
    title: str
    subtitle: str
    file: str


class DailyRecordV2(BaseModel):
    version: Literal[2] = 2
    date: str
    generated_at: str
    findings: list[Finding]
    note: MorningNote
    exhibits: list[Exhibit]
    releases: list[Release]  # kept so /macro's Economic releases card still has data
    rounds: int
    data_gaps: list[str]
