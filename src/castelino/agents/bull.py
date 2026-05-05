"""Bull Agent — argues *for* the trade using shared facts."""

from __future__ import annotations

from castelino.agents.base import StructuredAgent
from castelino.memory import io as memio
from castelino.memory.schemas import (
    BullCase,
    Hypothesis,
    ResearchBundle,
    TradeExpression,
)

SYSTEM = """\
You are the Bull analyst on a debate desk. Your job is to argue FOR the
proposed trade, drawing only from the shared research bundle.

Rules:
- Cite specific facts from the research bundle. No vibes.
- Identify the SINGLE strongest argument and put it in `strongest_argument`.
- Be honest about confidence: 'high' requires multiple corroborating signals.
- Do not argue against the trade — that is the Bear's job.
- Acknowledge precedent from past similar setups in short-term memory.
"""


class BullAgent(StructuredAgent[BullCase]):
    name = "bull"
    output_schema = BullCase
    tier = "reasoning"

    def system_prompt(self) -> str:
        return SYSTEM

    def user_prompt(
        self,
        *,
        expression: TradeExpression,
        hypothesis: Hypothesis,
        research: ResearchBundle,
    ) -> str:
        precedent_entries = memio.latest_n(kind="Verdict", n=5)
        precedent = "\n".join(
            f"- {e.decision}: {e.decisive_factor}" for e in precedent_entries
        ) or "- (none)"
        return (
            f"Trade: {expression.direction.value} {expression.instrument_id}, "
            f"size {expression.target_size_pct_nav * 100:.2f}% NAV, "
            f"horizon {expression.expected_holding_days}d, "
            f"stop {expression.initial_stop_pct * 100:.1f}% from entry.\n\n"
            f"Hypothesis: {hypothesis.thesis}\n"
            f"Conviction: {hypothesis.conviction.value}, regime: {hypothesis.regime.value}\n\n"
            f"Research bundle:\n"
            f"- Web: sentiment={research.web.sentiment}, summary={research.web.summary}\n"
            f"- TA: trend={research.technical.trend}, RSI={research.technical.rsi_14:.1f}, "
            f"vol30={research.technical.realized_vol_30d:.3f}, "
            f"interp={research.technical.interpretation}\n"
            f"- Backtest: hit_rate={research.backtest.hit_rate:.2f}, "
            f"avg_ret={research.backtest.avg_return_pct:.2f}%, "
            f"n={research.backtest.similar_setups_found}, "
            f"interp={research.backtest.interpretation}\n"
            f"- Risk: vol60={research.risk.realized_vol_60d:.3f}, "
            f"corr_book={research.risk.correlation_to_book:.2f}, "
            f"max_size={research.risk.suggested_max_size_pct_nav:.4f}, "
            f"interp={research.risk.interpretation}\n\n"
            f"Recent verdicts:\n{precedent}\n\n"
            f"Set parent_expression_id = {expression.entry_id!r} and "
            f"parent_research_bundle_id = {research.entry_id!r}."
        )
