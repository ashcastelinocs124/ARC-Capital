# Castelino Capital — Design Document

**Date:** 2026-05-03
**Status:** Approved design, pending implementation plan
**Goal:** Portfolio-piece multi-asset macro fund built as a LangGraph DAG of LLM agents

---

## 1. Pitch

Castelino Capital is a multi-asset macro fund implemented as a LangGraph DAG of LLM agents. It runs on real economic events (CPI, FOMC, central-bank decisions) detected by a significance-filtered trigger layer. Every event seeds a falsifiable macro thesis, which selects its own optimal expression across equities, fixed income, commodities, and FX. A shared research desk feeds opposing Bull and Bear analysts whose debate is adjudicated and then validated against a hard-coded constitution before any trade executes against a custom mark-to-market simulator. The system maintains short-term and long-term institutional memory, with a curator agent distilling lessons across regimes — so the fund actually learns which kinds of theses pay off.

### Distinctive elements vs. existing agent-trading repos

1. **Hypothesis-first funnel** — top-down macro, not stock-picker
2. **Constitutional governance layer** — `core_principles.md` + tiered Principles Guard
3. **Asymmetric R/W memory architecture** — institutional memory done correctly
4. **Deterministic execution / agent decision separation** — the accounting is provably right

---

## 2. Goals & non-goals

**Goals:**
- A portfolio-piece-grade multi-agent system that demonstrates novel architectural ideas (constitution, hypothesis funnel, librarian agent).
- True multi-asset reasoning across equities, fixed income, commodities, and FX.
- Reproducible accounting — the equity curve and attribution must be verifiable, not vibes.
- Institutional memory that visibly improves decisions over time.

**Non-goals (v1):**
- Real broker integration
- Intraday / hourly cadence
- Multi-leg derivatives (options, spreads)
- RL / agent self-edit / parameter tuning loops
- Web UI / multi-user / live alerting

---

## 3. Universe & cadence

**Universe (~30 instruments at start):**

| Asset class | Instruments | Source |
|---|---|---|
| Equities | Top S&P names + sector ETFs (XLE, XLK, XLF, XLV, XLY...) | yfinance |
| Fixed income | TLT, IEF, SHY (duration-bucket ETFs) + FRED yields (DGS2, DGS10) | yfinance + FRED |
| Commodities | GLD, USO, UNG (ETFs) and CL=F, GC=F, NG=F (front-month futures) | yfinance |
| FX | EURUSD, USDJPY, GBPUSD, AUDUSD, USDCAD | yfinance |

Bonds-via-ETF is standard practice at real macro funds for liquidity reasons; this is not a cop-out.

**Cadence:** event-driven with a 24-hour cron fallback. Pipeline runs only when something materially changes in the world (high-impact economic release, surprise news classified ≥ 0.7 by significance filter), or once daily if nothing has fired.

**Initial NAV:** $1,000,000 simulated.

**Position sizing baseline:** 1–3% of NAV per trade, conviction-scaled, hard cap 5% in `core_principles.md`.

**Holding horizon:** days-to-weeks. Closure on stop-loss or thesis-broken.

---

## 4. End-to-end flow

```
                ┌──────────────────────────┐
                │  TRIGGER LAYER           │
                │  - Econ calendar         │
                │  - News significance     │
                │  - 24h cron fallback     │
                └────────────┬─────────────┘
                             │ writes TriggerRecord to ST
                             ▼
                ┌──────────────────────────┐
                │  Current Event Agent     │  broad scan: what changed in the world?
                └────────────┬─────────────┘
                             ▼
                ┌──────────────────────────┐
                │  Macro Hypothesis Agent  │  reads: events + ST + LT + core_principles
                │                          │  outputs: thesis (regime, kill-criteria, conviction)
                └────────────┬─────────────┘
                             ▼
                ┌──────────────────────────┐
                │  Asset Selection Agent   │  reads: thesis + ST + LT
                │                          │  outputs: 1-3 TradeExpressions across asset classes
                └────────────┬─────────────┘
                             │ for each expression, run targeted research:
                             ▼
        ┌────────────────────────────────────────────┐
        │  Targeted Research Layer (parallel)        │
        │  • Web Agent      (instrument-specific)    │
        │  • TA Agent       (charts, levels)         │
        │  • Backtest Agent (similar-setup history)  │
        │  • Risk Agent     (vol, correlations, VaR) │
        └────────────────────┬───────────────────────┘
                             │ shared research bundle
                             ▼
                ┌──────────────────────────┐
                │  Bull Agent ↔ Bear Agent │  same facts, opposing reads + ST precedent
                └────────────┬─────────────┘
                             ▼
                ┌──────────────────────────┐
                │  Debate Agent            │  adjudicates → (trade | no-trade | adjusted size)
                └────────────┬─────────────┘
                             ▼
                ┌──────────────────────────┐
                │  Principles Guard        │  hard rules: deterministic veto.
                │                          │  soft rules: LLM warn + log.
                └────────────┬─────────────┘
                             ▼
                ┌──────────────────────────┐
                │  Portfolio Agent         │  emits TradeOrder (open / close / trim / hold)
                └────────────┬─────────────┘
                             ▼
                ┌──────────────────────────┐
                │  Execution (deterministic)│ broker.py simulates fill, writes portfolio.json
                └──────────────────────────┘

  [out-of-band]   Mark Loop (daily)        — updates current_price, NAV, exposures, stops
  [out-of-band]   Memory Curator (weekly)  — consolidates LT, prunes stale lessons
```

### Two architectural rules

1. **Decisions vs. accounting are separated.** Every node above the dashed line is an LLM agent producing structured Pydantic output. Everything below — execution, marking, NAV — is deterministic Python. **LLMs never do arithmetic that affects the book.**
2. **Read-write asymmetry on memory.** Agents read ST/LT/principles freely. Only the Portfolio Agent and Memory Curator write to journals. Only the human writes `core_principles.md`. Enforced at the file-access layer.

---

## 5. Agents & responsibilities

| # | Agent | Inputs | Outputs | Model tier | Job |
|---|---|---|---|---|---|
| 0 | **Trigger** *(function)* | Econ calendar, news feeds, last_run_ts | `TriggerRecord` (event, significance, ts) | — | Decide whether to fire the pipeline. |
| 1 | **Current Event Agent** | TriggerRecord + last 24h news | `WorldStateBrief` (events, regime signals, surprises) | Fast | Compress "what just changed" into a structured brief. |
| 2 | **Macro Hypothesis Agent** | WorldStateBrief + ST + LT + core_principles | `Hypothesis` (thesis, regime, conviction, horizon, kill_criteria) | Reasoning | Form a falsifiable view. Must declare what kills the thesis. |
| 3 | **Asset Selection Agent** | Hypothesis + ST (book) + LT (vehicle hit-rates) | List of `TradeExpression` (1-3) | Reasoning | "Best vehicle to express this thesis." Considers existing book correlation. |
| 4a | **Web Agent (targeted)** | TradeExpression | `WebResearch` (news, sentiment, catalysts) | Fast | Drill into chosen instrument via search. |
| 4b | **Technical Analysis Agent** | TradeExpression + price history | `TAReport` (trend, levels, momentum, vol regime) | Fast | Numbers via deterministic functions; LLM interprets. |
| 4c | **Backtesting Agent** | TradeExpression + Hypothesis | `BacktestReport` (similar setups, hit rate, avg P&L, max DD) | Fast | Deterministic similarity search; LLM summarizes. |
| 4d | **Risk Agent** | TradeExpression + portfolio.json | `RiskReport` (vol, correlation, marginal VaR, max size) | Fast | Quantitative computation in Python; LLM frames in natural language. |
| 5a | **Bull Agent** | All of (4a–4d) + ST precedent | `BullCase` | Reasoning | Argue *for* the trade using shared facts. |
| 5b | **Bear Agent** | All of (4a–4d) + ST precedent | `BearCase` | Reasoning | Argue *against* using the same facts. |
| 6 | **Debate Agent** | BullCase + BearCase + Hypothesis | `Verdict` (proceed/reject/modify, decisive_factor, dissent) | Reasoning | Adjudicate. Must cite the specific argument that tipped the decision. |
| 7 | **Principles Guard** *(rules engine + LLM)* | Verdict + portfolio.json + core_principles | `GuardDecision` (approved / hard_veto / soft_warning + amended trade) | Mixed | Hard rules = Python. Soft rules = LLM judgment with logged reasoning. |
| 8 | **Portfolio Agent** | GuardDecision + portfolio.json | `TradeOrder` (open/close/trim/hold + size + stop) | Reasoning | Translate verdict to book operation. Reconciles with existing positions. |
| 9 | **Memory Curator** *(weekly cron)* | LT + recently-aged-out ST entries | Updated long_term_journal | Reasoning | Consolidate lessons, prune contradictions, build category indices. |

### Hybrid agents

TA, Backtest, Risk, and Principles Guard all have a deterministic compute layer + an LLM interpretation layer. Pattern: Python computes the numbers (RSI, correlations, concentration percentages), Pydantic packages them, LLM reads and frames them for downstream consumers. Math correct, LLM context small.

### Total LLM cost

~9 reasoning-tier + ~5–7 fast-tier calls *per trade idea*. With 1–3 expressions per hypothesis, a typical run is 25–50 calls — sub-$1 per pipeline run on OpenAI's mid-tier.

### LLM provider

OpenAI. Reasoning-tier model (e.g. GPT-5 with reasoning / o-series) for Hypothesis, Asset Selection, Bull, Bear, Debate, Portfolio, Curator. Faster model (GPT-5-mini class) for Current Event, Web, TA, Backtest, Risk, and the trigger significance filter. Specific model IDs picked at implementation time.

---

## 6. State & memory model

### Three persistent files

| File | Purpose | Writer |
|---|---|---|
| `data/core_principles.md` | Constitution, hand-edited | Human only |
| `data/short_term_journal.md` | Rolling working memory (~20 closed trades + open positions + last 30d hypotheses + 30d triggers + 90d warnings) | Portfolio Agent + Memory Curator (trim only) + Execution (trade events) |
| `data/long_term_journal.md` | Condensed lessons by category | Memory Curator only |
| `data/portfolio.json` | Deterministic state (positions, cash, NAV history) | Execution / Mark Loop / Portfolio Agent |

### `core_principles.md` — the constitution

Two sections, two enforcement modes.

**Hard rules (Principles Guard veto):**
- Position sizing: no single position > 5% NAV; no asset class > 40% gross; no new positions if drawdown > 10%.
- Liquidity: no instrument with 30d ADV < $50M; no position > 1% of ADV.
- Risk circuit breakers: VIX > 40 → gross capped at 50%; 5d P&L < -5% → no new positions until 3 flat/positive days.

**Soft rules (warn + log):**
- Avoid averaging down on thesis-broken trades.
- Avoid > 2 active trades in same regime hypothesis.
- No new position within 24h of closing same instrument at a loss.
- Every trade must cite kill criteria from parent hypothesis.
- 3 consecutive losses in a thesis category → flag for LT review.

Exact rules are tunable; structure is fixed.

### `short_term_journal.md` — rolling working memory

Markdown for human readability + LLM ingestibility. Sister file `short_term_index.json` maps IDs → byte offsets for cheap retrieval.

Entry types: TriggerRecord, Hypothesis, TradeExpression, ResearchBundle, BullCase / BearCase / Verdict, Trade (open / closed), PrincipleWarning.

Capacity: 20 closed trades + all open positions + last 30 days of hypotheses + 30 days of triggers + 90 days of principle warnings. Curator trims oldest into LT.

### `long_term_journal.md` — condensed lessons

Curator-written, organized by category, 1-2 lines per entry with statistical backing.

Sections: Regime patterns, Vehicle preferences, Recurring biases, Per-thesis-category hit rates.

### Read/write matrix

| Component | core_principles | short_term | long_term | portfolio.json |
|---|---|---|---|---|
| Hypothesis Agent | R | R | R | — |
| Asset Selection | R | R | R | — |
| Research agents | R | R | — | R (Risk only) |
| Bull / Bear | R | R | R | — |
| Debate Agent | R | R | R | — |
| Principles Guard | R | R | — | R |
| Portfolio Agent | R | **W** | — | **W** |
| Memory Curator | R | **W (trim)** | **W** | R |
| Execution / Mark Loop | — | **W (trade events)** | — | **W** |
| Human | **W** | — | — | — |

Enforced via `src/memory/io.py`, which takes a `WriterIdentity` and refuses writes that violate the matrix.

---

## 7. Trigger system

### Three trigger sources

| Source | Mechanism | Significance |
|---|---|---|
| Economic calendar | Daily pull from free API (investpy / ForexFactory). Filters to high-impact: FOMC, CPI, NFP, PCE, GDP, ECB, BoJ, OPEC. | Pre-classified high/med/low. Surprise magnitude (actual vs consensus z-score) multiplies. |
| News significance filter | RSS pulls every N minutes (Reuters, AP, FT, central-bank press). Cheap LLM batch-scores headlines 0-1. | ≥ 0.7 fires; 0.4-0.7 logs only; < 0.4 dropped. |
| 24h cron fallback | If nothing fires within 24h, fire anyway. | Always 0.3. Hypothesis Agent knows it's a "no-news check-in." |

### Significance classifier

Single fast-tier LLM call, batched. Pydantic schema with materiality score, asset_classes_affected, one-sentence reason. System prompt enforces tough judging — false positives pollute memory.

### TriggerRecord (written to ST)

Every fire writes a structured record so the Current Event Agent and downstream agents know *why* the pipeline ran.

### Off-switch

`data/system_state.json` flag (`trading_enabled: bool`). Pipeline runs to a recommended trade and logs as "would-have-traded" without executing. Useful for review mode, demos, post-incident pause.

### Prompt-injection containment

The Trigger layer is the only place LLMs see un-curated raw news. Once a trigger fires, downstream agents see the *structured brief* the Current Event Agent produced — never raw RSS.

---

## 8. Execution & accounting

### Three components

| File | Job |
|---|---|
| `src/execution/broker.py` | Pure-function fill simulator: `execute(order, portfolio) -> portfolio` |
| `src/execution/mark_loop.py` | Daily NAV / exposure / stop-loss check |
| `src/execution/pricing.py` | Unified price adapter (yfinance + FRED + cache) |

### Order types

Only four: `MARKET_OPEN`, `MARKET_CLOSE`, `TRIM`, `STOP_LOSS`. No limits, no GTC, no OCO. v1 macro funds don't need them and they obscure agent reasoning behind execution noise.

### Slippage model (flat by asset class)

| Asset class | Slippage | Commission |
|---|---|---|
| Equity / sector ETF | 5 bps | $0 |
| Bond ETF | 5 bps | $0 |
| Commodity ETF | 10 bps | $0 |
| Front-month futures | 15 bps | $2/contract |
| Major FX pair | 8 bps | $0 |

### Mark loop

Daily after US close (separate scheduled process, not part of LangGraph DAG):
1. Mark every open position to market (FX-converted).
2. Snapshot NAV; append to nav_history.
3. Stop-loss check; if hit, emit synthetic close order.
4. Recompute exposure metrics → `data/exposure_snapshot.json` (read by Principles Guard).

### Pricing adapter

Single `latest(instrument: str) -> Price` function. Hides source via `INSTRUMENT_REGISTRY`. 15-min LRU cache + on-disk price-history cache. Bad-data defense: NaN, stale-timestamp, or > 5σ tick raises rather than feeds garbage upstream.

### Accounting invariant (sacred)

> `NAV_after_trade == NAV_before_trade − slippage_cost − commission_cost`

Single test that catches 90% of accounting bugs. Runs in CI on every state transition.

### Reporting (free outputs)

- Equity curve (`nav_history` plot)
- Drawdown curve
- Attribution by asset class / thesis / category
- Exposure dashboard (current % NAV breakdown)
- Trade detail page (full debate transcript + research bundle + outcome)

Static HTML / matplotlib PNGs regenerated after every mark and pipeline run. No app server.

---

## 9. Repo layout

```
Castelino-Capital/
├── CLAUDE.md
├── learnings.md
├── short_term_memory.md
├── long_term_memory.md
├── README.md
├── pyproject.toml
├── config.yaml
├── .env                            (gitignored)
│
├── docs/plans/2026-05-03-castelino-capital-design.md
│
├── data/                           (mostly gitignored)
│   ├── core_principles.md          (committed)
│   ├── short_term_journal.md       (machine-written)
│   ├── short_term_index.json
│   ├── long_term_journal.md        (Curator-written)
│   ├── portfolio.json              (deterministic state)
│   ├── exposure_snapshot.json
│   ├── system_state.json
│   └── cache/prices/
│
├── src/
│   ├── orchestrator/               # LangGraph DAG, FundState, runner CLI
│   ├── agents/                     # one file per agent
│   │   ├── base.py                 # shared OpenAI wrapper, retry, structured output
│   │   ├── current_event.py
│   │   ├── hypothesis.py
│   │   ├── asset_selection.py
│   │   ├── research/
│   │   │   ├── web.py
│   │   │   ├── technical.py
│   │   │   ├── backtest.py
│   │   │   └── risk.py
│   │   ├── bull.py · bear.py · debate.py
│   │   ├── guard.py
│   │   ├── portfolio.py
│   │   └── curator.py
│   ├── triggers/                   # calendar, news, significance, cron, runner
│   ├── execution/                  # broker, mark_loop, pricing
│   ├── memory/                     # io (R/W enforcement), schemas, retrieval
│   ├── data/                       # adapters: yfinance, fred, news_rss
│   └── reporting/                  # equity_curve, attribution, exposure, trade_card
│
├── reports/                        (gitignored)
├── scripts/                        # seed_book, replay, reset_demo
└── tests/
    ├── test_accounting_invariant.py    # the sacred test
    ├── test_broker_fills.py
    ├── test_guard_hard_rules.py
    ├── test_memory_io_asymmetry.py     # enforce R/W matrix
    ├── test_principles_yaml_schema.py
    └── test_pipeline_e2e.py            # mocked LLMs, full pipeline run
```

`agents/` mirrors the architecture diagram 1:1 — reviewers see the system's anatomy at a glance.

---

## 10. Build milestones

| Phase | Goal | Deliverable | Demo-able? |
|---|---|---|---|
| **M1 — Skeleton & accounting** | Walking-skeleton with no LLMs. portfolio.json + broker.py + mark_loop.py + pricing.py + accounting invariant test. | Manual trade scripts; passing CI. | "Watch the math be correct" |
| **M2 — Memory layer** | core_principles.md + ST/LT scaffolding + memory/io.py with R/W enforcement + ID schemas + indexing. Populate via scripts. | Every entry type writeable; retrieval working. | "Show the journal as a story" |
| **M3 — One-asset MVP** | Single-instrument pipeline (TLT). Hypothesis + Asset Selection + Bull + Bear + Debate + Guard + Portfolio Agent in LangGraph. Manual trigger. | `castelino run` opens or skips a trade based on a news event. | "Watch one full debate fire and decide" |
| **M4 — Full universe + research layer** | Plug in 4 research sub-agents. Expand registry to ~30 instruments. Multi-expression handling (1-3 in parallel). | Multi-asset pipeline runs cleanly; reports/ generates equity curve and attribution after replay. | "The fund operates across 4 asset classes" |
| **M5 — Trigger layer** | Calendar puller + news RSS + significance classifier + 24h cron + off-switch. `castelino watch` runs continuously. | System is autonomous; each fire produces a journal entry. | "It runs itself for a week" |
| **M6 — Curator + reports + replay** | Memory Curator (weekly cron) + all reports + `replay.py` for backfilling. | Static report site (GitHub Pages-ready). Replay 90 days of triggers to seed memory. | "The portfolio piece is shippable" |

**Critical sequencing rule:** M1 (accounting) before M3 (agents). Building agents first means debugging state corruption *and* prompts simultaneously — two unrelated failure modes. Build the deterministic floor first; agents become *just additions*.

---

## 11. Out of scope (v1)

- Real broker integration (deferred behind `broker_adapter` interface)
- Intraday / hourly cadence
- Options, futures spreads, multi-leg derivatives
- Parameter-tuning / RL / agent self-edit
- Web UI (static reports only)
- Multi-user / authentication
- Live alerting / Slack integration

---

## 12. Open implementation questions (for the implementation plan)

1. Specific OpenAI model IDs per tier — pin in `config.yaml`.
2. Backtesting Agent's similarity-search algorithm: feature-vector cosine on macro state, or rule-based filter?
3. Risk Agent's correlation window: 30d, 60d, or regime-conditional?
4. News RSS sources for v1 — start with 3-4, add more once significance filter is calibrated.
5. Curator cadence: weekly is the default; consider monthly LT *consolidation* on top of weekly *rolling*.
6. Whether stop-loss closes route through Portfolio Agent (journal coherence) or bypass directly (simpler).
   - Decision: **route through Portfolio Agent** for journal coherence and so the Agent can add context to the close ("kill criterion #2 hit") rather than just a bare price-cross close.

---

## 13. Approval

Design approved by user across all six sections on 2026-05-03. Proceeds to writing-plans for implementation plan.
