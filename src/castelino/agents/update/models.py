from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Stage(str, Enum):
    IDLE = "idle"
    CHECKING = "checking"
    REFITTING = "refitting"
    GATING = "gating"
    COLLECTING = "collecting"
    WRITING = "writing"
    GUARDING = "guarding"
    DONE = "done"
    FAILED = "failed"


class Decision(str, Enum):
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
    consensus: float | None = None   # not wired in v1
    surprise: float | None = None    # not wired in v1


class SectorTrend(BaseModel):
    sector: str
    r1w: float | None = None
    r1m: float | None = None
    r3m: float | None = None
    r6m: float | None = None
    r12m: float | None = None
    rel1m: float | None = None       # vs SPY, percentage points
    rel12m: float | None = None
    short_label: str = "n/a"
    long_label: str = "n/a"


class PredictionDelta(BaseModel):
    old: float | None = None
    new: float
    gate: str                         # promoted | kept | unchanged


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
