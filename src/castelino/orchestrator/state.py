"""FundState — the dataclass that flows through the LangGraph DAG.

Every node consumes some keys, produces others, and the graph stitches them
together. Defined as a Pydantic model (LangGraph accepts both TypedDict and
Pydantic states); we use Pydantic for validation + nicer ergonomics in tests.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from castelino.agents.portfolio import PortfolioDecision
from castelino.execution.broker import Fill, TradeOrder
from castelino.execution.portfolio import Portfolio
from castelino.memory.schemas import (
    BearCase,
    BullCase,
    GuardDecision,
    Hypothesis,
    ResearchBundle,
    TradeExpression,
    TriggerRecord,
    Verdict,
    WorldStateBrief,
)


class FundState(BaseModel):
    """All state passed through the pipeline DAG.

    Lists are append-only by node; per-expression nodes (research, debate,
    guard, portfolio) walk them in the same index order so they stay aligned.
    """

    trigger: TriggerRecord
    recent_headlines: list[str] = Field(default_factory=list)
    source_summaries: list[str] = Field(default_factory=list)

    # Filled by nodes
    world_state: Optional[WorldStateBrief] = None
    hypothesis: Optional[Hypothesis] = None
    expressions: list[TradeExpression] = Field(default_factory=list)
    research_bundles: list[ResearchBundle] = Field(default_factory=list)
    bull_cases: list[BullCase] = Field(default_factory=list)
    bear_cases: list[BearCase] = Field(default_factory=list)
    verdicts: list[Verdict] = Field(default_factory=list)
    guard_decisions: list[GuardDecision] = Field(default_factory=list)
    gate_decisions: list = Field(default_factory=list)  # list[GateDecision]
    portfolio_decisions: list[PortfolioDecision] = Field(default_factory=list)
    orders: list[TradeOrder] = Field(default_factory=list)
    fills: list[Fill] = Field(default_factory=list)

    portfolio: Portfolio  # snapshot at start; overwritten after fills

    # From `data/regime_forecast.json` + `regime_sector_cheat_sheet.yaml` (optional)
    macro_regime_key: str = ""
    macro_regime_label: str = ""
    preferred_sectors: list[str] = Field(default_factory=list)
    preferred_instrument_ids: list[str] = Field(default_factory=list)
    macro_regime_blurb: str = ""
    growth_forecast_up: Optional[bool] = None
    inflation_forecast_up: Optional[bool] = None
    growth_prob_up: Optional[float] = None
    inflation_prob_up: Optional[float] = None
    regime_feature_month: str = ""
    regime_target_month: str = ""
    regime_lead_months: int = 0

    aborted: bool = False
    abort_reason: str = ""

    model_config = {"arbitrary_types_allowed": True}
