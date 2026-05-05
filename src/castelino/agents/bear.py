"""Bear Agent — argues *against* the trade using shared facts."""

from __future__ import annotations

from castelino.agents.base import StructuredAgent
from castelino.memory import io as memio
from castelino.memory.schemas import (
    BearCase,
    Hypothesis,
    ResearchBundle,
    TradeExpression,
)

SYSTEM = """\
You are the Bear analyst on a debate desk. Your job is to argue AGAINST the
proposed trade, drawing only from the shared research bundle.

Rules:
- Cite specific facts. No vague "I'm worried about macro."
- Identify the SINGLE strongest counter-argument as `strongest_argument`.
- Look for: kill criteria already triggered, deteriorating TA, weak backtest
  cohort, high correlation to existing book, regime mismatch.
- Be honest about confidence: 'high' requires the counter-evidence to be hard,
  not "could happen."
- Do not argue for the trade. That is the Bull's job.
"""


class BearAgent(StructuredAgent[BearCase]):
    name = "bear"
    output_schema = BearCase
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
        recent_warnings = memio.latest_n(kind="PrincipleWarning", n=5)
        warnings = "\n".join(f"- {w.rule_id}: {w.description}" for w in recent_warnings) or "- (none)"
        return (
            f"Trade: {expression.direction.value} {expression.instrument_id}, "
            f"size {expression.target_size_pct_nav * 100:.2f}% NAV, "
            f"horizon {expression.expected_holding_days}d.\n\n"
            f"Hypothesis (parent): {hypothesis.thesis}\n"
            f"Kill criteria:\n"
            + "\n".join(f"- {kc.description}" for kc in hypothesis.kill_criteria)
            + "\n\nResearch bundle:\n"
            + f"- Web: sentiment={research.web.sentiment}, summary={research.web.summary}\n"
            + f"- TA: trend={research.technical.trend}, RSI={research.technical.rsi_14:.1f}, "
            + f"interp={research.technical.interpretation}\n"
            + f"- Backtest: hit_rate={research.backtest.hit_rate:.2f}, "
            + f"max_dd={research.backtest.max_drawdown_pct:.2f}%, "
            + f"interp={research.backtest.interpretation}\n"
            + f"- Risk: vol60={research.risk.realized_vol_60d:.3f}, "
            + f"corr_book={research.risk.correlation_to_book:.2f}, "
            + f"interp={research.risk.interpretation}\n\n"
            + f"Recent principle warnings:\n{warnings}\n\n"
            + f"Set parent_expression_id = {expression.entry_id!r} and "
            + f"parent_research_bundle_id = {research.entry_id!r}."
        )
