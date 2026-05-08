"""Schemas for every entry that lands in the journals.

Every agent that produces structured output emits one of these. Every read
deserializes from these. The `entry_id` is canonical — used by the index file
to find offsets in the markdown journal.

A single `JournalEntry` discriminated union is the wire format.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _now() -> datetime:
    return datetime.now(UTC)


# ────────────────────────── enums shared across schemas ──────────────────────


class Conviction(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Direction(str, Enum):
    LONG = "long"
    SHORT = "short"


class Regime(str, Enum):
    RISK_ON = "risk_on"
    RISK_OFF = "risk_off"
    STAGFLATION = "stagflation"
    DISINFLATION = "disinflation"
    REFLATION = "reflation"
    UNCERTAIN = "uncertain"


class TriggerSource(str, Enum):
    CALENDAR = "calendar"
    NEWS = "news"
    CRON_FALLBACK = "cron_fallback"
    MANUAL = "manual"
    REGIME_SHIFT = "regime_shift"
    CONVICTION = "conviction"
    SPEECH_DEVIATION = "speech_deviation"


# ────────────────────────── trigger / world-state ────────────────────────────


class LeadingIndicatorRead(BaseModel):
    """Maps headline evidence to one catalog row from `data/macro_leading_indicators.yaml`."""

    indicator_key: str = Field(
        ...,
        description=(
            "Must match a `key` from the macro leading-indicator catalog "
            "(system prompt)."
        ),
    )
    read: str = Field(
        ...,
        max_length=500,
        description="What the cited headlines imply for this indicator; stay factual.",
    )
    supporting_headline: str = Field(
        ...,
        description=(
            "Verbatim copy of one headline from the user message (same spelling/punctuation)."
        ),
    )


class TriggerRecord(BaseModel):
    kind: Literal["TriggerRecord"] = "TriggerRecord"
    entry_id: str = Field(default_factory=lambda: _new_id("trg"))
    timestamp: datetime = Field(default_factory=_now)
    source: TriggerSource
    headline: str
    significance: float = Field(ge=0.0, le=1.0)
    asset_classes_affected: list[str] = Field(default_factory=list)
    raw_event_data: dict = Field(default_factory=dict)
    one_sentence_reason: str = ""

    @field_validator("significance")
    @classmethod
    def _round_sig(cls, v: float) -> float:
        return round(v, 3)


class WorldStateBrief(BaseModel):
    """The Current Event Agent's compressed view of 'what just changed'."""

    kind: Literal["WorldStateBrief"] = "WorldStateBrief"
    entry_id: str = Field(default_factory=lambda: _new_id("wsb"))
    timestamp: datetime = Field(default_factory=_now)
    parent_trigger_id: str
    headlines: list[str]
    source_summaries: list[str] = Field(default_factory=list)
    macro_signals: list[str] = Field(default_factory=list)
    surprises: list[str] = Field(default_factory=list)
    leading_indicator_reads: list[LeadingIndicatorRead] = Field(
        default_factory=list,
        max_length=12,
        description=(
            "Optional structured pass over the team's leading-indicator catalog; "
            "only include rows backed by supplied headlines."
        ),
    )
    summary: str


# ────────────────────────── hypothesis / expression ──────────────────────────


class KillCriterion(BaseModel):
    """A specific, falsifiable condition that — if met — kills the thesis."""

    description: str
    metric: str = ""  # e.g. "10y yield" or "DXY"
    threshold: float | None = None
    direction: Literal["above", "below"] | None = None


class Hypothesis(BaseModel):
    kind: Literal["Hypothesis"] = "Hypothesis"
    entry_id: str = Field(default_factory=lambda: _new_id("hyp"))
    timestamp: datetime = Field(default_factory=_now)
    parent_trigger_id: str
    parent_world_state_id: str
    thesis: str
    regime: Regime
    horizon_days: int = Field(ge=1, le=365)
    conviction: Conviction
    kill_criteria: list[KillCriterion] = Field(min_length=1)
    rationale: str
    contradicting_evidence: str = ""


class TradeExpression(BaseModel):
    kind: Literal["TradeExpression"] = "TradeExpression"
    entry_id: str = Field(default_factory=lambda: _new_id("exp"))
    timestamp: datetime = Field(default_factory=_now)
    parent_hypothesis_id: str
    instrument_id: str
    direction: Direction
    rationale: str
    expected_holding_days: int = Field(ge=1)
    target_size_pct_nav: float = Field(gt=0.0, le=0.05)
    initial_stop_pct: float = Field(gt=0.0, le=0.20)


# ────────────────────────── research bundle ──────────────────────────────────


class TAReport(BaseModel):
    kind: Literal["TAReport"] = "TAReport"
    instrument_id: str
    trend: Literal["uptrend", "downtrend", "range"]
    rsi_14: float
    sma_50: float
    sma_200: float
    realized_vol_30d: float
    key_support: float
    key_resistance: float
    interpretation: str


class WebResearch(BaseModel):
    kind: Literal["WebResearch"] = "WebResearch"
    instrument_id: str
    headlines: list[str] = Field(default_factory=list)
    sentiment: Literal["positive", "neutral", "negative"]
    catalysts: list[str] = Field(default_factory=list)
    summary: str


class BacktestReport(BaseModel):
    kind: Literal["BacktestReport"] = "BacktestReport"
    instrument_id: str
    similar_setups_found: int
    hit_rate: float
    avg_return_pct: float
    max_drawdown_pct: float
    sample_period_years: float
    interpretation: str


class RiskReport(BaseModel):
    kind: Literal["RiskReport"] = "RiskReport"
    instrument_id: str
    realized_vol_60d: float
    correlation_to_book: float
    marginal_var_pct_nav: float
    suggested_max_size_pct_nav: float = Field(gt=0.0, le=0.05)
    interpretation: str


class ResearchBundle(BaseModel):
    """Sealed snapshot of all research feeding Bull / Bear."""

    kind: Literal["ResearchBundle"] = "ResearchBundle"
    entry_id: str = Field(default_factory=lambda: _new_id("rsb"))
    timestamp: datetime = Field(default_factory=_now)
    parent_expression_id: str
    web: WebResearch
    technical: TAReport
    backtest: BacktestReport
    risk: RiskReport


# ────────────────────────── debate ───────────────────────────────────────────


class BullCase(BaseModel):
    kind: Literal["BullCase"] = "BullCase"
    entry_id: str = Field(default_factory=lambda: _new_id("bul"))
    timestamp: datetime = Field(default_factory=_now)
    parent_expression_id: str
    parent_research_bundle_id: str
    arguments: list[str] = Field(min_length=1)
    strongest_argument: str
    confidence: Conviction


class BearCase(BaseModel):
    kind: Literal["BearCase"] = "BearCase"
    entry_id: str = Field(default_factory=lambda: _new_id("ber"))
    timestamp: datetime = Field(default_factory=_now)
    parent_expression_id: str
    parent_research_bundle_id: str
    arguments: list[str] = Field(min_length=1)
    strongest_argument: str
    confidence: Conviction


class Verdict(BaseModel):
    kind: Literal["Verdict"] = "Verdict"
    entry_id: str = Field(default_factory=lambda: _new_id("vdc"))
    timestamp: datetime = Field(default_factory=_now)
    parent_expression_id: str
    parent_bull_id: str
    parent_bear_id: str
    decision: Literal["proceed", "reject", "modify"]
    decisive_factor: str
    dissent: str = ""
    size_multiplier: float = Field(default=1.0, ge=0.0, le=2.0)


# ────────────────────────── guard ────────────────────────────────────────────


class PrincipleWarning(BaseModel):
    kind: Literal["PrincipleWarning"] = "PrincipleWarning"
    entry_id: str = Field(default_factory=lambda: _new_id("pwn"))
    timestamp: datetime = Field(default_factory=_now)
    rule_id: str  # e.g. "S1", "H2"
    severity: Literal["soft", "hard"]
    description: str
    parent_expression_id: str | None = None


class GuardDecision(BaseModel):
    kind: Literal["GuardDecision"] = "GuardDecision"
    entry_id: str = Field(default_factory=lambda: _new_id("gdc"))
    timestamp: datetime = Field(default_factory=_now)
    parent_verdict_id: str
    decision: Literal["approved", "hard_veto", "soft_warning", "amended"]
    amended_size_multiplier: float = 1.0
    triggered_rules: list[str] = Field(default_factory=list)
    rationale: str
    warnings: list[PrincipleWarning] = Field(default_factory=list)


# ────────────────────────── trade events ─────────────────────────────────────


class TradeEvent(BaseModel):
    """A journal entry produced by an executed fill."""

    kind: Literal["TradeEvent"] = "TradeEvent"
    entry_id: str = Field(default_factory=lambda: _new_id("trd"))
    timestamp: datetime = Field(default_factory=_now)
    event_type: Literal["open", "close", "trim", "stop_loss"]
    instrument_id: str
    parent_hypothesis_id: str | None = None
    parent_expression_id: str | None = None
    quantity: float
    fill_price: float
    slippage_cost: float
    commission_cost: float
    realized_pnl: float = 0.0
    pre_trade_nav: float
    post_trade_nav: float
    notes: str = ""


# ────────────────────────── long-term lesson ─────────────────────────────────


class LongTermLesson(BaseModel):
    kind: Literal["LongTermLesson"] = "LongTermLesson"
    entry_id: str = Field(default_factory=lambda: _new_id("lt"))
    timestamp: datetime = Field(default_factory=_now)
    category: Literal[
        "regime_pattern", "vehicle_preference", "recurring_bias", "category_hit_rate"
    ]
    title: str
    body: str
    statistical_backing: str = ""
    references: list[str] = Field(default_factory=list)


# ────────────────────────── union ────────────────────────────────────────────


JournalEntry = Annotated[
    TriggerRecord
    | WorldStateBrief
    | Hypothesis
    | TradeExpression
    | ResearchBundle
    | BullCase
    | BearCase
    | Verdict
    | GuardDecision
    | PrincipleWarning
    | TradeEvent
    | LongTermLesson,
    Field(discriminator="kind"),
]
