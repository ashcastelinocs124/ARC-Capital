"""End-to-end pipeline test with a mocked LLM client.

Proves the LangGraph DAG composes correctly: trigger → world state → hypothesis
→ asset selection → research → debate → guard → portfolio → fills. Every LLM
call is intercepted by a `FakeLLMClient`; pricing is monkeypatched too so the
test never touches the network.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from castelino.agents import base as agent_base
from castelino.agents.base import FakeLLMClient
from castelino.agents.portfolio import PortfolioDecision
from castelino.config import get_settings
from castelino.execution import pricing
from castelino.execution.portfolio import Portfolio
from castelino.execution.pricing import Price
from castelino.memory import io as memio
from castelino.memory.schemas import (
    BacktestReport,
    BearCase,
    BullCase,
    Conviction,
    Direction,
    GuardDecision,
    Hypothesis,
    KillCriterion,
    LeadingIndicatorRead,
    Regime,
    RiskReport,
    TAReport,
    TradeExpression,
    TriggerRecord,
    TriggerSource,
    Verdict,
    WebResearch,
    WorldStateBrief,
)
from castelino.orchestrator.graph import build_graph
from castelino.orchestrator.state import FundState


@pytest.fixture(autouse=True)
def auto_approve_gates(monkeypatch):
    """Auto-approve all gates in tests so pipeline doesn't stall."""
    from castelino.orchestrator.approval import ApprovalQueue

    def instant_approve(self, entry_id, poll_interval=2.0):
        self.approve(entry_id)
        return self.get(entry_id)

    monkeypatch.setattr(ApprovalQueue, "wait_for_resolution", instant_approve)


@pytest.fixture(autouse=True)
def _isolate_data(tmp_path, monkeypatch):
    """Redirect every journal + portfolio path into a tmp dir."""

    def fake_paths():
        return memio.JournalPaths(
            short_term_md=tmp_path / "st.md",
            short_term_index=tmp_path / "st_index.json",
            long_term_md=tmp_path / "lt.md",
            principles_md=tmp_path / "principles.md",
        )

    monkeypatch.setattr(memio, "_paths", fake_paths)
    # Write a stub principles file so Hypothesis prompts don't crash.
    (tmp_path / "principles.md").write_text("# stub principles\n")

    # Portfolio default path
    monkeypatch.setattr(
        Portfolio, "default_path", classmethod(lambda cls: tmp_path / "portfolio.json")
    )

    # Exposure snapshot writer
    from castelino.execution import mark_loop
    monkeypatch.setattr(
        mark_loop,
        "write_exposure_snapshot",
        lambda pf, path=None: None,
    )

    yield


@pytest.fixture
def fake_pricing(monkeypatch):
    """Stub pricing so neither yfinance nor FRED is called."""
    fake_price = 90.0

    def _latest(iid):
        return Price(
            instrument_id=iid, price=fake_price, asof=datetime.now(UTC),
            source=pricing.PriceSource.YFINANCE,
        )

    def _history(iid, lookback_days=252):
        idx = pd.date_range("2024-01-01", periods=400, freq="B")
        rng = np.random.default_rng(seed=hash(iid) % (2**31))
        rets = rng.normal(0.0003, 0.012, size=400)
        prices = 100 * (1 + pd.Series(rets)).cumprod()
        df = pd.DataFrame(
            {
                "open": prices.values,
                "high": prices.values * 1.005,
                "low": prices.values * 0.995,
                "close": prices.values,
                "volume": 1_000_000,
            },
            index=idx,
        )
        return df.tail(lookback_days)

    monkeypatch.setattr(pricing, "latest", _latest)
    monkeypatch.setattr(pricing, "history", _history)
    # Also patch through the agent imports
    from castelino.execution import mark_loop
    monkeypatch.setattr(mark_loop, "latest", _latest)
    from castelino.agents.research import technical, backtest, risk
    monkeypatch.setattr(technical, "history", _history)
    monkeypatch.setattr(backtest, "history", _history)
    monkeypatch.setattr(risk, "history", _history)
    from castelino.agents import guard, portfolio
    monkeypatch.setattr(guard, "latest", _latest)
    monkeypatch.setattr(portfolio, "latest", _latest)


@pytest.fixture
def fake_llm():
    """A fully wired FakeLLMClient that produces a coherent pipeline run."""
    client = FakeLLMClient()

    def world(_sys, _user):
        return WorldStateBrief(
            parent_trigger_id="trg-fake",
            headlines=["FOMC pauses rate hikes", "10y yield drops 8 bps"],
            macro_signals=["short-end rally", "DXY softens"],
            surprises=["dot plot more dovish than expected"],
            leading_indicator_reads=[
                LeadingIndicatorRead(
                    indicator_key="real_policy_rate",
                    read="Hold combined with softer inflation prints implies less negative "
                    "real policy on the margin.",
                    supporting_headline="FOMC pauses rate hikes",
                ),
                LeadingIndicatorRead(
                    indicator_key="yield_curve_10y_2y",
                    read="Long-end yields fell on the session, moving curve dynamics.",
                    supporting_headline="10y yield drops 8 bps",
                ),
            ],
            summary="The Fed paused; rates pricing eased materially.",
        )

    def hypothesis(_sys, _user):
        return Hypothesis(
            parent_trigger_id="trg-fake",
            parent_world_state_id="wsb-fake",
            thesis="Disinflation extends; long duration outperforms.",
            regime=Regime.DISINFLATION,
            horizon_days=21,
            conviction=Conviction.MEDIUM,
            kill_criteria=[KillCriterion(description="10y yield > 4.7%", metric="DGS10", threshold=4.7, direction="above")],
            rationale="Soft inflation + dovish dots; bonds catch the bid.",
            contradicting_evidence="Sticky services CPI could re-accelerate.",
        )

    def asset_selection(_sys, _user):
        from castelino.agents.asset_selection import AssetSelectionOutput
        return AssetSelectionOutput(
            expressions=[
                TradeExpression(
                    parent_hypothesis_id="hyp-fake",
                    instrument_id="TLT",
                    direction=Direction.LONG,
                    rationale="Long-duration ETF expresses disinflation thesis.",
                    expected_holding_days=21,
                    target_size_pct_nav=0.03,
                    initial_stop_pct=0.04,
                ),
            ],
            rationale_overall="One clean duration trade.",
        )

    def web(_sys, _user):
        return WebResearch(
            instrument_id="TLT",
            headlines=["FOMC dovish"], sentiment="positive",
            catalysts=["next CPI in 2 weeks"], summary="Bullish for duration.",
        )

    def ta(_sys, _user):
        return TAReport(
            instrument_id="TLT", trend="uptrend", rsi_14=58.0,
            sma_50=92.0, sma_200=88.0, realized_vol_30d=0.16,
            key_support=85.0, key_resistance=95.0,
            interpretation="Above 50/200 SMA, RSI moderate.",
        )

    def bt(_sys, _user):
        return BacktestReport(
            instrument_id="TLT", similar_setups_found=42, hit_rate=0.62,
            avg_return_pct=1.8, max_drawdown_pct=-3.5, sample_period_years=10.0,
            interpretation="Constructive cohort.",
        )

    def risk(_sys, _user):
        return RiskReport(
            instrument_id="TLT", realized_vol_60d=0.18,
            correlation_to_book=0.0, marginal_var_pct_nav=0.001,
            suggested_max_size_pct_nav=0.03,
            interpretation="Reasonable size for this vol regime.",
        )

    def bull(_sys, _user):
        return BullCase(
            parent_expression_id="exp-fake",
            parent_research_bundle_id="rsb-fake",
            arguments=["Trend up", "Hit rate 62%", "Macro dovish"],
            strongest_argument="Hit rate 62% on similar setups",
            confidence=Conviction.MEDIUM,
        )

    def bear(_sys, _user):
        return BearCase(
            parent_expression_id="exp-fake",
            parent_research_bundle_id="rsb-fake",
            arguments=["Sticky services CPI risk"],
            strongest_argument="CPI surprise could break thesis",
            confidence=Conviction.LOW,
        )

    def verdict(_sys, _user):
        return Verdict(
            parent_expression_id="exp-fake",
            parent_bull_id="bul-fake",
            parent_bear_id="ber-fake",
            decision="proceed",
            decisive_factor="Strong cohort hit rate aligned with macro dovish surprise.",
            dissent="CPI risk acknowledged but not active.",
            size_multiplier=1.0,
        )

    def guard(_sys, _user):
        return GuardDecision(
            parent_verdict_id="vdc-fake",
            decision="approved",
            triggered_rules=[],
            rationale="No soft-rule violations; trade clean.",
            warnings=[],
        )

    def pa(_sys, _user):
        return PortfolioDecision(
            action="open",
            quantity_pct_nav=0.03,
            stop_loss_pct=0.04,
            notes="Open TLT long for duration tilt.",
            cite_kill_criterion="10y yield > 4.7%",
        )

    client.register("WorldStateBrief", world)
    client.register("Hypothesis", hypothesis)
    client.register("AssetSelectionOutput", asset_selection)
    client.register("WebResearch", web)
    client.register("TAReport", ta)
    client.register("BacktestReport", bt)
    client.register("RiskReport", risk)
    client.register("BullCase", bull)
    client.register("BearCase", bear)
    client.register("Verdict", verdict)
    client.register("GuardDecision", guard)
    client.register("PortfolioDecision", pa)

    agent_base.set_llm_client(client)
    yield client
    agent_base.set_llm_client(agent_base.OpenAIClient.__new__(agent_base.OpenAIClient))  # placeholder reset


def test_full_pipeline_runs_to_fill(fake_pricing, fake_llm):
    cfg = get_settings()
    pf = Portfolio(cash=cfg.fund.initial_nav, initial_nav=cfg.fund.initial_nav)
    trg = TriggerRecord(
        source=TriggerSource.NEWS,
        headline="FOMC pauses rate hikes",
        significance=0.85,
        asset_classes_affected=["bond_etf"],
    )
    state = FundState(trigger=trg, recent_headlines=[trg.headline], portfolio=pf)
    graph = build_graph()

    result = graph.invoke(state)

    # The result is a dict-like state from LangGraph
    assert result is not None
    assert result["world_state"] is not None
    assert result["hypothesis"] is not None
    assert len(result["expressions"]) == 1
    assert result["expressions"][0].instrument_id == "TLT"
    assert len(result["verdicts"]) == 1
    assert result["verdicts"][0].decision == "proceed"
    assert len(result["guard_decisions"]) == 1
    assert result["guard_decisions"][0].decision == "approved"
    assert len(result["fills"]) == 1
    fill = result["fills"][0]
    assert fill.instrument_id == "TLT"
    assert fill.side.value == "buy"
    assert fill.fill_price > 0


def test_pipeline_writes_journal_entries(fake_pricing, fake_llm):
    cfg = get_settings()
    pf = Portfolio(cash=cfg.fund.initial_nav, initial_nav=cfg.fund.initial_nav)
    trg = TriggerRecord(
        source=TriggerSource.NEWS, headline="FOMC pauses", significance=0.9,
    )
    state = FundState(trigger=trg, recent_headlines=[trg.headline], portfolio=pf)

    build_graph().invoke(state)
    counts = memio.journal_summary()
    # Every agent should have written at least one entry kind
    for kind in (
        "WorldStateBrief", "Hypothesis", "TradeExpression", "ResearchBundle",
        "BullCase", "BearCase", "Verdict", "GuardDecision", "TradeEvent",
    ):
        assert counts.get(kind, 0) >= 1, f"missing journal entries of kind {kind}"


def test_hard_veto_blocks_fills(fake_pricing, fake_llm, monkeypatch):
    """If the deterministic guard finds a hard violation, no fill happens."""
    # Force a hard veto by making the proposed size exceed the cap
    cfg = get_settings()
    pf = Portfolio(cash=cfg.fund.initial_nav, initial_nav=cfg.fund.initial_nav)

    def asset_selection_oversized(_sys, _user):
        from castelino.agents.asset_selection import AssetSelectionOutput
        # 4.5% size with a 1.5x verdict multiplier = 6.75% > 5% cap
        return AssetSelectionOutput(
            expressions=[
                TradeExpression(
                    parent_hypothesis_id="hyp-fake",
                    instrument_id="TLT",
                    direction=Direction.LONG,
                    rationale="oversized",
                    expected_holding_days=21,
                    target_size_pct_nav=0.045,
                    initial_stop_pct=0.04,
                ),
            ],
            rationale_overall="oversized",
        )

    fake_llm.register("AssetSelectionOutput", asset_selection_oversized)

    def verdict_big(_sys, _user):
        return Verdict(
            parent_expression_id="exp-fake",
            parent_bull_id="bul-fake", parent_bear_id="ber-fake",
            decision="proceed",
            decisive_factor="big size on conviction",
            size_multiplier=1.5,
        )

    fake_llm.register("Verdict", verdict_big)

    trg = TriggerRecord(
        source=TriggerSource.NEWS, headline="x", significance=0.8,
    )
    state = FundState(trigger=trg, recent_headlines=[trg.headline], portfolio=pf)
    result = build_graph().invoke(state)

    assert len(result["guard_decisions"]) == 1
    assert result["guard_decisions"][0].decision == "hard_veto"
    assert "H1" in result["guard_decisions"][0].triggered_rules
    assert len(result["fills"]) == 0


def test_hard_veto_skips_portfolio_agent_llm(fake_pricing, fake_llm):
    """When the Guard hard-vetoes, the Portfolio Agent LLM must not be called.
    Otherwise a future prompt regression could turn a constitutional veto into
    a fill — that defeats the structural guarantee.
    """
    cfg = get_settings()
    pf = Portfolio(cash=cfg.fund.initial_nav, initial_nav=cfg.fund.initial_nav)

    # Force a hard veto via oversized expression (same trick as the other test)
    def asset_selection_oversized(_sys, _user):
        from castelino.agents.asset_selection import AssetSelectionOutput
        return AssetSelectionOutput(
            expressions=[
                TradeExpression(
                    parent_hypothesis_id="hyp-fake", instrument_id="TLT",
                    direction=Direction.LONG, rationale="r",
                    expected_holding_days=21, target_size_pct_nav=0.04,
                    initial_stop_pct=0.04,
                ),
            ],
            rationale_overall="r",
        )

    fake_llm.register("AssetSelectionOutput", asset_selection_oversized)
    fake_llm.register(
        "Verdict",
        lambda s, u: Verdict(
            parent_expression_id="exp-fake", parent_bull_id="bul-fake",
            parent_bear_id="ber-fake", decision="proceed",
            decisive_factor="big", size_multiplier=2.0,  # 4% * 2x = 8% > 5% cap → veto
        ),
    )

    # PortfolioDecision handler should NEVER be called — replace with a sentinel raise
    def _should_not_be_called(_s, _u):
        raise AssertionError("PortfolioDecision LLM was invoked despite hard_veto!")

    fake_llm.register("PortfolioDecision", _should_not_be_called)

    trg = TriggerRecord(source=TriggerSource.NEWS, headline="x", significance=0.8)
    state = FundState(trigger=trg, recent_headlines=[trg.headline], portfolio=pf)
    result = build_graph().invoke(state)

    assert result["guard_decisions"][0].decision == "hard_veto"
    # The synthetic PortfolioDecision still appears (so journal is coherent),
    # but action is 'hold' — no order, no fill.
    assert len(result["portfolio_decisions"]) == 1
    assert result["portfolio_decisions"][0].action == "hold"
    assert len(result["fills"]) == 0


def test_pipeline_aborts_with_no_expressions(fake_pricing, fake_llm):
    """Asset Selection returning no expressions aborts before research."""
    def empty_selection(_sys, _user):
        from castelino.agents.asset_selection import AssetSelectionOutput
        # Bypass min_length validator using model_construct
        return AssetSelectionOutput.model_construct(expressions=[], rationale_overall="no fit")

    fake_llm.register("AssetSelectionOutput", empty_selection)

    cfg = get_settings()
    pf = Portfolio(cash=cfg.fund.initial_nav, initial_nav=cfg.fund.initial_nav)
    trg = TriggerRecord(source=TriggerSource.MANUAL, headline="quiet day", significance=0.3)
    state = FundState(trigger=trg, recent_headlines=[trg.headline], portfolio=pf)

    result = build_graph().invoke(state)
    assert len(result["expressions"]) == 0
    assert len(result["fills"]) == 0
