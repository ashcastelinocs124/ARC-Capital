"""Maps each chat CommandName to a thin callable + safety metadata.

Mutating-ness lives HERE, never in the LLM output — the confirm gate trusts
this table, not the model.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, UTC

from castelino.execution.portfolio import Portfolio
from castelino.agents.chat.models import CommandName
from castelino.agents.research.deep.orchestrator import DeepResearchOrchestrator
from castelino.agents.research.deep.sonar_client import PerplexitySonarClient
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
from castelino.agents.personas.agent import PersonaAgent
from castelino.agents.personas.models import PersonaConversation
from castelino.agents.base import get_llm_client


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


_research_pending_id: str | None = None


def _format_report(sess) -> str:
    rep = sess.report
    srcs = "\n".join(f"  - {s.title or s.url} ({s.url})" for s in rep.sources)
    return f"{rep.exec_summary}\n\nSources:\n{srcs}\n(session {sess.id})"


def _clear_pending_research() -> None:
    global _research_pending_id
    _research_pending_id = None


def _submit_research_answers(user_text: str) -> str:
    global _research_pending_id
    sid = _research_pending_id
    _research_pending_id = None
    if sid is None:
        return "No pending clarification to answer."
    orch = DeepResearchOrchestrator()
    sess = orch.run_first_round(sid, answers={"clarification": user_text})
    if sess.status.value == "failed":
        return f"Research failed: {sess.error}"
    sess = orch.finish(sid)
    return _format_report(sess)


def _research(args: dict[str, str]) -> str:
    global _research_pending_id
    query = args["query"]
    _research_pending_id = None
    orch = DeepResearchOrchestrator()
    sess = orch.start(query)
    if sess.clarifying_questions:
        _research_pending_id = sess.id
        lines = [f"\u2b50 {sess.reworded_query}", ""]
        for i, q in enumerate(sess.clarifying_questions, 1):
            lines.append(f"  {i}. {q.question}")
            if q.why:
                lines.append(f"     \u2014 {q.why}")
        lines.append("")
        lines.append("Reply with your answers to run the deep research.")
        return "\n".join(lines)
    sess = orch.run_first_round(sess.id, answers={})
    if sess.status.value == "failed":
        return f"Research failed: {sess.error}"
    sess = orch.finish(sess.id)
    return _format_report(sess)


_PERSONAS: dict[str, str] = {
    "krugman": "Paul Krugman",
    "elerian": "Mohamed El-Erian",
    "summers": "Larry Summers",
    "druckenmiller": "Stanley Druckenmiller",
    "dalio": "Ray Dalio",
    "tudor_jones": "Paul Tudor Jones",
}

_discuss_pending_persona: str | None = None
_discuss_pending_conv: PersonaConversation | None = None


def _clear_pending_discuss() -> None:
    global _discuss_pending_persona, _discuss_pending_conv
    _discuss_pending_persona = None
    _discuss_pending_conv = None


def _handle_discuss_message(user_text: str) -> str:
    global _discuss_pending_persona, _discuss_pending_conv
    if _discuss_pending_persona is None or _discuss_pending_conv is None:
        return "No active persona conversation."
    full_name = _PERSONAS.get(_discuss_pending_persona, _discuss_pending_persona)
    try:
        agent = PersonaAgent(persona_id=_discuss_pending_persona, client=get_llm_client())
        msg = agent.chat(conversation=_discuss_pending_conv, user_text=user_text, approval_payload={})
    except FileNotFoundError:
        _clear_pending_discuss()
        return (f"Persona \"{_discuss_pending_persona}\" not built. "
                f"Run: ckm persona-build --persona {_discuss_pending_persona} ...")
    return f"**{full_name}:** {msg.text}"


async def _run_panel(question: str) -> str:
    client = get_llm_client()

    async def _ask_one(pid, full_name):
        try:
            agent = PersonaAgent(persona_id=pid, client=client)
            conv = PersonaConversation(entry_id="cli", persona_id=pid, started_at=datetime.now(UTC))
            msg = await asyncio.to_thread(agent.chat, conversation=conv, user_text=question, approval_payload={})
            return f"**{full_name}:** {msg.text}"
        except FileNotFoundError:
            return f"**{full_name}:** (not built — run: ckm persona-build --persona {pid})"
        except Exception as e:
            return f"**{full_name}:** ({type(e).__name__}: {e})"

    tasks = [_ask_one(pid, name) for pid, name in _PERSONAS.items()]
    responses = await asyncio.gather(*tasks, return_exceptions=True)
    lines = []
    for r in responses:
        if isinstance(r, Exception):
            lines.append(f"(error: {r})")
        else:
            lines.append(r)
    return "\n\n".join(lines)


def _discuss(args: dict[str, str]) -> str:
    global _discuss_pending_persona, _discuss_pending_conv
    raw = args["query"].strip()
    parts = raw.split(maxsplit=1)
    sub = parts[0].lower().rstrip(",.:;!?") if parts else ""
    question = parts[1] if len(parts) > 1 else ""

    if sub == "list":
        lines = ["Available personas:"]
        for pid, name in _PERSONAS.items():
            alias = min([a for a in ["krugman", "elerian", "summers", "druckenmiller", "dalio", "tudor_jones"] if a == pid], key=len)
            lines.append(f"  /{pid:<16} — {name}")
        return "\n".join(lines)

    if sub == "panel":
        if not question:
            return "Usage: /discuss panel <question>"
        return asyncio.run(_run_panel(question))

    persona_id = sub
    full_name = _PERSONAS.get(persona_id)
    if not full_name:
        lower = raw.lower()
        for pid, name in _PERSONAS.items():
            pid_spaceless = lower.replace("-", "").replace(" ", "")
            if pid in lower or pid.replace("_", " ") in lower or pid in pid_spaceless:
                persona_id = pid
                full_name = name
                question = raw
                break
            last = name.split()[-1].lower()
            if last in lower:
                persona_id = pid
                full_name = name
                question = raw
                break
        if not full_name:
            return f"Unknown persona: \"{persona_id}\". Available: {', '.join(_PERSONAS)}"

    if not question:
        _discuss_pending_persona = persona_id
        _discuss_pending_conv = PersonaConversation(
            entry_id="cli", persona_id=persona_id, started_at=datetime.now(UTC),
        )
        return f"**{full_name}** — ask your question or type exit to leave."

    try:
        agent = PersonaAgent(persona_id=persona_id, client=get_llm_client())
        conv = PersonaConversation(entry_id="cli", persona_id=persona_id, started_at=datetime.now(UTC))
        msg = agent.chat(conversation=conv, user_text=question, approval_payload={})
    except FileNotFoundError:
        return (f"Persona \"{persona_id}\" not built. "
                f"Run: ckm persona-build --persona {persona_id} "
                f"--full-name \"{full_name}\"")
    return f"**{full_name}:** {msg.text}"


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


_MARKET_OVERVIEW_QUERY = (
    "Give a concise current market snapshot across these asset classes. "
    "Mention specific ticker/index levels where possible. "
    "Use the latest available information from real sources. "
    "For each asset class, summarize the main move and the key driver in 1-2 sentences. "
    "Keep it compact and factual.\n\n"
    "Equities: SPX, NDX, DJIA — levels, % move on the day, key driver.\n"
    "Rates: US10Y, US2Y — yield levels, curve shape, key driver.\n"
    "FX: DXY, EURUSD — levels, % move, key driver.\n"
    "Commodities: WTI crude, gold (XAUUSD) — prices, % move, key driver.\n"
    "Crypto: BTCUSD, ETHUSD — prices, % move, key driver.\n"
    "Credit: IG spreads (CDX IG), high yield (HYG) — spread levels, direction, key driver."
)


def _market_overview(_args: dict[str, str]) -> str:
    sonar = PerplexitySonarClient()
    result = sonar.search(_MARKET_OVERVIEW_QUERY)
    if not result.content.strip():
        return "I couldn't get current market coverage right now."
    return result.content.strip()


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
    CommandName.market_overview: CommandSpec(_market_overview, False,
        "Get a broad current cross-asset market snapshot (equities, rates, FX, commodities, crypto, credit)."),
    CommandName.discuss: CommandSpec(_discuss, False,
        "Consult macro personas on a topic. /discuss <persona|panel|list> <question>", ["query"]),
}