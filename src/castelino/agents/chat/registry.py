"""Maps each chat CommandName to a thin callable + safety metadata.

Mutating-ness lives HERE, never in the LLM output — the confirm gate trusts
this table, not the model.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from castelino.execution.portfolio import Portfolio
from castelino.agents.chat.models import CommandName
from castelino.agents.research.deep.orchestrator import DeepResearchOrchestrator
from castelino.orchestrator.approval import ApprovalQueue
from castelino.orchestrator.graph import build_graph
from castelino.orchestrator.state import FundState
from castelino.execution.mark_loop import run_mark_loop
from castelino.memory import io as memio
from castelino.forecast.regime import (
    GROWTH_INDICATORS_YAML,
    INFLATION_INDICATORS_YAML,
    IndicatorListConfig,
    TrainingConfig,
    train_and_forecast,
)
from castelino.forecast.risk_off import train_and_predict


@dataclass(frozen=True)
class CommandSpec:
    run: Callable[[dict[str, str]], str]   # takes args, returns printable summary
    mutating: bool
    help: str
    required_args: list[str] = field(default_factory=list)


# Command handlers implementation
def _status(_args: dict[str, str]) -> str:
    pf = Portfolio.load()
    lines = [
        f"NAV ${pf.nav:,.2f} | cash ${pf.cash:,.2f} | "
        f"gross ${pf.gross_exposure:,.2f} | net ${pf.net_exposure:,.2f} | "
        f"open positions {len(pf.positions)} | realized P&L ${pf.realized_pnl:,.2f}",
    ]
    for p in pf.positions:
        lines.append(f"  {p.instrument_id}: qty {p.quantity:+.2f} @ {p.avg_entry_price:.4f} "
                     f"now {p.current_price:.4f} uPnL ${p.unrealized_pnl:+,.2f}")
    return "\n".join(lines)


def _queue(_args: dict[str, str]) -> str:
    pending = ApprovalQueue().pending()
    if not pending:
        return "No pending approvals."
    return "\n".join(
        f"{i.entry_id}  [{i.gate}]  {i.submitted_at[:19]}" for i in pending
    )


def _research(args: dict[str, str]) -> str:
    sess = DeepResearchOrchestrator().run_sync(args["query"])
    if sess.status.value == "failed":
        return f"Research failed: {sess.error}"
    rep = sess.report
    srcs = "\n".join(f"  - {s.title or s.url} ({s.url})" for s in rep.sources)
    return f"{rep.exec_summary}\n\nSources:\n{srcs}\n(session {sess.id})"


def _forecast_regime(_args: dict[str, str]) -> str:
    b = train_and_forecast(
        growth_cfg=IndicatorListConfig.from_yaml(GROWTH_INDICATORS_YAML),
        inflation_cfg=IndicatorListConfig.from_yaml(INFLATION_INDICATORS_YAML),
        training_cfg=TrainingConfig(),
    )
    return (f"Growth: up={b.growth.up} (P={b.growth.prob_up:.2%}) | "
            f"Inflation: up={b.inflation.up} (P={b.inflation.prob_up:.2%})")


def _forecast_risk(_args: dict[str, str]) -> str:
    f = train_and_predict()
    return f"P(risk-off) = {f.prob_risk_off:.4f} (target {f.target_month})"


def _run(args: dict[str, str]) -> str:
    from castelino.memory.io import WriterIdentity
    from castelino.memory.schemas import TriggerRecord, TriggerSource

    headline = args["headline"]
    trg = TriggerRecord(
        source=TriggerSource.manual, headline=headline,
        significance=float(args.get("significance", "0.7")),
        asset_classes_affected=[], one_sentence_reason=headline,
    )
    memio.append_short_term(trg, WriterIdentity.TRIGGER_RUNNER)
    state = FundState(trigger=trg, recent_headlines=[headline],
                      portfolio=Portfolio.load(), **merge_forecast_into_state_kwargs())
    result = build_graph().invoke(state)
    g = result.get if isinstance(result, dict) else (lambda k, d=None: getattr(result, k, d))
    h = (result.get("hypothesis") if isinstance(result, dict) else getattr(result, "hypothesis", None))
    fills = (result.get("fills") if isinstance(result, dict) else getattr(result, "fills", None)) or []
    return f"Pipeline complete. Hypothesis: {getattr(h, 'thesis', '(none)')} | fills: {len(fills)}"


def _approve(args: dict[str, str]) -> str:
    item = ApprovalQueue().approve(args["entry_id"], notes=args.get("notes", ""))
    return f"Approved {item.entry_id} ({item.gate})"


def _reject(args: dict[str, str]) -> str:
    item = ApprovalQueue().reject(args["entry_id"], reason=args.get("reason", ""),
                                  notes=args.get("notes", ""))
    return f"Rejected {item.entry_id}"


def _reset(_args: dict[str, str]) -> str:
    from castelino.config import get_settings
    cfg = get_settings()
    for f in (cfg.resolved_paths.data / "portfolio.json",
              cfg.resolved_paths.data / "exposure_snapshot.json",
              cfg.resolved_paths.data / "system_state.json"):
        if f.exists():
            f.unlink()
    memio.reset_journals(confirm_token="I_KNOW_WHAT_I_AM_DOING")
    return "Wiped journals + portfolio."


def _mark(_args: dict[str, str]) -> str:
    pf = Portfolio.load()
    new_pf, fills, _warn = run_mark_loop(pf)
    new_pf.save()
    return f"NAV after mark ${new_pf.nav:,.2f} | stop-loss fills {len(fills)}"


REGISTRY: dict[CommandName, CommandSpec] = {
    CommandName.status: CommandSpec(_status, False, "Show NAV, exposure, positions, journal counts."),
    CommandName.queue: CommandSpec(_queue, False, "List pending approval items."),
    CommandName.research: CommandSpec(_research, False, "Run the deep-research engine.", ["query"]),
    CommandName.forecast_regime: CommandSpec(_forecast_regime, False, "Growth+inflation next-month MoM forecast."),
    CommandName.forecast_risk: CommandSpec(_forecast_risk, False, "Risk-off probability forecast."),
    CommandName.run: CommandSpec(_run, True, "Fire the trading pipeline from a headline.", ["headline"]),
    CommandName.approve: CommandSpec(_approve, True, "Approve a pending item.", ["entry_id"]),
    CommandName.reject: CommandSpec(_reject, True, "Reject a pending item.", ["entry_id"]),
    CommandName.reset: CommandSpec(_reset, True, "Wipe journals + portfolio (demo only)."),
    CommandName.mark: CommandSpec(_mark, True, "Run the daily mark loop."),
}