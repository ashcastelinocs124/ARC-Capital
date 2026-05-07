"""LangGraph DAG — wires every agent into the end-to-end pipeline.

Nodes mirror `docs/plans/2026-05-03-castelino-capital-design.md` §4 1:1.
For M3 we run the per-expression sub-pipeline sequentially; M4 introduces
parallel fanout.
"""

from __future__ import annotations

import logging

from langgraph.graph import END, StateGraph

from castelino.orchestrator.approval import ApprovalQueue, ApprovalStatus, GateType

from castelino.agents.asset_selection import AssetSelectionAgent
from castelino.agents.bear import BearAgent
from castelino.agents.bull import BullAgent
from castelino.agents.current_event import CurrentEventAgent
from castelino.agents.debate import DebateAgent
from castelino.agents.guard import run_guard
from castelino.agents.hypothesis import HypothesisAgent
from castelino.agents.portfolio import run_portfolio_agent
from castelino.agents.research.backtest import run_backtest
from castelino.agents.research.risk import run_risk
from castelino.agents.research.technical import run_ta
from castelino.agents.research.web import run_web
from castelino.execution.broker import execute, trade_event_from_fill
from castelino.forecast.regime_sectors import format_macro_block_for_prompt
from castelino.memory import io as memio
from castelino.memory.io import WriterIdentity
from castelino.memory.schemas import ResearchBundle
from castelino.orchestrator.state import FundState

log = logging.getLogger(__name__)


# ───────────────────────── individual nodes ───────────────────────────────


def _node_current_event(state: FundState) -> dict:
    log.info("→ current_event")
    brief = CurrentEventAgent()(
        trigger=state.trigger,
        recent_headlines=state.recent_headlines,
        source_summaries=state.source_summaries,
    )
    memio.append_short_term(brief, WriterIdentity.CURRENT_EVENT_AGENT)
    return {"world_state": brief}


def _node_hypothesis(state: FundState) -> dict:
    log.info("→ hypothesis")
    if state.world_state is None:
        return {"aborted": True, "abort_reason": "no world_state"}
    macro_ctx = format_macro_block_for_prompt(state)
    h = HypothesisAgent()(world_state=state.world_state, macro_context=macro_ctx)
    memio.append_short_term(h, WriterIdentity.HYPOTHESIS_AGENT)
    return {"hypothesis": h}


def _node_asset_selection(state: FundState) -> dict:
    log.info("→ asset_selection")
    if state.hypothesis is None:
        return {"aborted": True, "abort_reason": "no hypothesis"}
    macro_ctx = format_macro_block_for_prompt(state)
    out = AssetSelectionAgent()(
        hypothesis=state.hypothesis,
        portfolio=state.portfolio,
        macro_context=macro_ctx,
    )
    for exp in out.expressions:
        memio.append_short_term(exp, WriterIdentity.ASSET_SELECTION_AGENT)
    return {"expressions": out.expressions}


def _node_research(state: FundState) -> dict:
    log.info("→ research (n=%d)", len(state.expressions))
    bundles: list[ResearchBundle] = []
    if state.world_state is None or state.hypothesis is None:
        return {"aborted": True, "abort_reason": "missing prereqs for research"}
    for exp in state.expressions:
        web = run_web(exp, state.world_state)
        ta = run_ta(exp)
        bt = run_backtest(exp, state.hypothesis)
        risk = run_risk(exp, state.portfolio)
        bundle = ResearchBundle(
            parent_expression_id=exp.entry_id,
            web=web, technical=ta, backtest=bt, risk=risk,
        )
        memio.append_short_term(bundle, WriterIdentity.RESEARCH_AGENT)
        bundles.append(bundle)
    return {"research_bundles": bundles}


def _node_debate(state: FundState) -> dict:
    log.info("→ debate (n=%d)", len(state.expressions))
    if state.hypothesis is None:
        return {"aborted": True, "abort_reason": "no hypothesis"}
    macro_ctx = format_macro_block_for_prompt(state)
    bull_cases, bear_cases, verdicts = [], [], []
    for exp, bundle in zip(state.expressions, state.research_bundles, strict=True):
        bull = BullAgent()(
            expression=exp,
            hypothesis=state.hypothesis,
            research=bundle,
            macro_context=macro_ctx,
        )
        bear = BearAgent()(
            expression=exp,
            hypothesis=state.hypothesis,
            research=bundle,
            macro_context=macro_ctx,
        )
        memio.append_short_term(bull, WriterIdentity.BULL_AGENT)
        memio.append_short_term(bear, WriterIdentity.BEAR_AGENT)
        verdict = DebateAgent()(
            bull=bull,
            bear=bear,
            hypothesis=state.hypothesis,
            macro_context=macro_ctx,
        )
        memio.append_short_term(verdict, WriterIdentity.DEBATE_AGENT)
        bull_cases.append(bull)
        bear_cases.append(bear)
        verdicts.append(verdict)
    return {
        "bull_cases": bull_cases,
        "bear_cases": bear_cases,
        "verdicts": verdicts,
    }


def _node_guard(state: FundState) -> dict:
    log.info("→ guard (n=%d)", len(state.verdicts))
    if state.hypothesis is None:
        return {"aborted": True, "abort_reason": "no hypothesis"}
    decisions = []
    for exp, verdict in zip(state.expressions, state.verdicts, strict=True):
        decision = run_guard(
            verdict=verdict,
            expression=exp,
            hypothesis=state.hypothesis,
            portfolio=state.portfolio,
        )
        memio.append_short_term(decision, WriterIdentity.GUARD_AGENT)
        for w in decision.warnings:
            memio.append_short_term(w, WriterIdentity.GUARD_AGENT)
        decisions.append(decision)
    return {"guard_decisions": decisions}


def _node_portfolio_and_execute(state: FundState) -> dict:
    """Run the Portfolio Agent + execute the resulting orders deterministically."""
    log.info("→ portfolio + execute (n=%d)", len(state.guard_decisions))
    if state.hypothesis is None:
        return {"aborted": True, "abort_reason": "no hypothesis"}

    pf = state.portfolio
    p_decisions = []
    orders = []
    fills = []
    for exp, verdict, guard in zip(
        state.expressions, state.verdicts, state.guard_decisions, strict=True,
    ):
        decision, order = run_portfolio_agent(
            verdict=verdict,
            guard=guard,
            expression=exp,
            hypothesis=state.hypothesis,
            portfolio=pf,
        )
        p_decisions.append(decision)
        if order is None:
            continue
        orders.append(order)
        pf, fill = execute(order, pf)
        fills.append(fill)
        memio.journal_trade_event(
            trade_event_from_fill(order, fill),
            who=WriterIdentity.EXECUTION,
        )

    pf.save()
    return {
        "portfolio_decisions": p_decisions,
        "orders": orders,
        "fills": fills,
        "portfolio": pf,
    }


# ───────────────────────── HITL gate nodes ───────────────────────────────────


def _node_gate_hypothesis(state: FundState) -> dict:
    """HITL gate: stall until human approves/edits/rejects the hypothesis."""
    log.info("⏸ GATE: awaiting hypothesis approval")
    if state.hypothesis is None:
        return {"aborted": True, "abort_reason": "no hypothesis to approve"}

    queue = ApprovalQueue()
    item = queue.submit(
        gate=GateType.POST_HYPOTHESIS,
        payload={
            "thesis": state.hypothesis.thesis,
            "regime": state.hypothesis.regime.value,
            "conviction": state.hypothesis.conviction.value,
            "horizon_days": state.hypothesis.horizon_days,
            "kill_criteria": [c.description for c in state.hypothesis.kill_criteria],
        },
        entry_id=f"H-{state.hypothesis.entry_id}",
    )
    result = queue.wait_for_resolution(item.entry_id)

    if result.status == ApprovalStatus.REJECTED:
        return {"aborted": True, "abort_reason": f"hypothesis rejected: {result.rejection_reason}"}
    return {}


def _node_gate_debate(state: FundState) -> dict:
    """HITL gate: stall until human approves/rejects debate verdicts."""
    log.info("⏸ GATE: awaiting debate verdict approval")
    if not state.verdicts:
        return {"aborted": True, "abort_reason": "no verdicts to approve"}

    queue = ApprovalQueue()
    for exp, verdict in zip(state.expressions, state.verdicts, strict=True):
        item = queue.submit(
            gate=GateType.POST_DEBATE,
            payload={
                "instrument": exp.instrument_id,
                "direction": exp.direction.value,
                "decision": verdict.decision,
                "size_multiplier": verdict.size_multiplier,
                "decisive_factor": verdict.decisive_factor,
                "dissent": verdict.dissent,
            },
            entry_id=f"V-{verdict.entry_id}",
        )
        result = queue.wait_for_resolution(item.entry_id)
        if result.status == ApprovalStatus.REJECTED:
            return {"aborted": True, "abort_reason": f"verdict rejected for {exp.instrument_id}: {result.rejection_reason}"}
    return {}


# ───────────────────────── edge logic ─────────────────────────────────────


def _route_after_asset_selection(state: FundState) -> str:
    if state.aborted:
        return "abort"
    if not state.expressions:
        return "abort"
    return "research"


def _route_after_hypothesis(state: FundState) -> str:
    return "abort" if state.aborted else "asset_selection"


# ───────────────────────── builder ────────────────────────────────────────


def build_graph():
    """Compile and return the runnable LangGraph."""
    g = StateGraph(FundState)
    g.add_node("current_event", _node_current_event)
    g.add_node("hypothesis", _node_hypothesis)
    g.add_node("gate_hypothesis", _node_gate_hypothesis)
    g.add_node("asset_selection", _node_asset_selection)
    g.add_node("research", _node_research)
    g.add_node("debate", _node_debate)
    g.add_node("gate_debate", _node_gate_debate)
    g.add_node("guard", _node_guard)
    g.add_node("portfolio", _node_portfolio_and_execute)

    g.set_entry_point("current_event")
    g.add_edge("current_event", "hypothesis")
    g.add_conditional_edges(
        "hypothesis",
        _route_after_hypothesis,
        {"asset_selection": "gate_hypothesis", "abort": END},
    )
    g.add_conditional_edges(
        "gate_hypothesis",
        lambda s: "abort" if s.aborted else "asset_selection",
        {"asset_selection": "asset_selection", "abort": END},
    )
    g.add_conditional_edges(
        "asset_selection",
        _route_after_asset_selection,
        {"research": "research", "abort": END},
    )
    g.add_edge("research", "debate")
    g.add_edge("debate", "gate_debate")
    g.add_conditional_edges(
        "gate_debate",
        lambda s: "abort" if s.aborted else "guard",
        {"guard": "guard", "abort": END},
    )
    g.add_edge("guard", "portfolio")
    g.add_edge("portfolio", END)
    return g.compile()
