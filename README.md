# CKM Capital

A multi-asset macro hedge fund built as a **LangGraph DAG of LLM agents**, governed by a hard-coded constitution and a deterministic accounting floor. The fund trades equities, fixed income, commodities, FX, and Bitcoin (via IBIT ETF in risk-on regimes) through a **hypothesis-first** funnel: every trade traces back to a falsifiable macro thesis, and every dollar of slippage is provably accounted for.

This is a portfolio piece — a working simulation, not connected to a real broker.

---

## What it does

The system monitors macro news, economic data, and prediction markets through a **multi-layered trigger system** that fires the pipeline based on accumulated conviction — not just single headlines. When triggered, a **9-stage agent pipeline** produces 0–3 sized trades:

### Trigger Layer (4 paths)

1. **Black swan override** — single headline with materiality ≥ 0.9 fires instantly (war, unscheduled FOMC, sovereign default).
2. **Regime shift** — XGBoost nowcaster detects growth/inflation quadrant flip (Reflation → Stagflation, etc.).
3. **Accumulated conviction** — a directional conviction ledger tracks headlines with exponential decay (12h half-life). Fires when growth or inflation signals accumulate past threshold. This catches the slow-burn "five headlines all pointing to Eurozone weakness" that no single headline triggers.
4. **Cron fallback** — nothing fired for 24h, low-significance reassessment.

### Significance Scoring (two-pass)

Every headline gets scored 0–1 with growth/inflation direction (up/down/neutral). Borderline headlines (0.4–0.8) get a **second pass** enriched with:
- **Polymarket** prediction market prices — is money actually flowing on this event?
- **X/Twitter sentiment** (via Perplexity Sonar) — is fintwit paying attention?

This separates real macro signals from noise.

### Input Enrichment

Headlines that enter the pipeline are enriched via **Perplexity Sonar** with ~200-word search-grounded summaries. The Current Event Agent sees full context, not bare 10-word titles. Non-US calendar events (ECB, BoJ, OPEC) are also sourced from Sonar in real-time.

### Agent Pipeline

1. **Regime Nowcaster** — XGBoost classifiers predict month-ahead growth (ISM PMI) and inflation (CPI) direction. Maps to a 4-quadrant label: Reflation, Goldilocks, Stagflation, Disinflation.
2. **Sector Resolution** — maps the regime quadrant to preferred sectors/ETFs (e.g., Reflation → XLE, XLI, GLD, IBIT).
3. **Current Event Agent** — compresses enriched headlines into a structured `WorldStateBrief` with leading indicator reads. The only place an LLM sees uncurated text (prompt-injection containment).
4. **Hypothesis Agent** — forms one falsifiable thesis with mandatory `kill_criteria`, informed by regime context + leading indicator reads.
5. **⏸ Human approval gate** — pipeline stalls until the hypothesis is approved/rejected/edited via CLI.
6. **Asset Selection Agent** — picks 1–3 instruments, prioritizing regime-preferred ETFs.
7. **Research Desk** (4 agents — web, technical, backtest, risk) — sealed evidence bundle. Numbers computed in Python; LLM writes interpretation.
8. **Bull and Bear** agents argue opposing reads with regime context.
9. **Debate Agent** adjudicates, citing the specific argument that tipped the call.
10. **⏸ Human approval gate** — verdict review before execution.
11. **Principles Guard** — hard rules (5% NAV cap, 40% asset-class cap, VIX circuit breaker) checked deterministically; soft rules LLM-evaluated.
12. **Portfolio Agent** → **Broker** — translates verdict to `TradeOrder`, simulates fill, updates `portfolio.json`.

A **mark loop** runs daily to re-price and trigger stop-losses. A **memory curator** runs weekly to distill patterns into long-term lessons.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                          TRIGGER LAYER                           │
│  RSS news / FRED calendar / Sonar non-US cal / cron fallback     │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                    ┌──────▼──────┐
                    │ SIGNIFICANCE │  LLM scores 0-1 + growth/inflation
                    │   SCORER     │  direction per headline
                    └──────┬──────┘
                           │
                 ┌─────────▼──────────┐
                 │  TWO-PASS ENRICHMENT│  Borderlines (0.4-0.8) re-scored
                 │  Polymarket prices  │  with prediction market + X
                 │  X/Twitter via Sonar│  sentiment context
                 └─────────┬──────────┘
                           │
              ┌────────────▼──────────────┐
              │  CONVICTION LEDGER         │  Decaying directional sums
              │  growth ↑↓ / inflation ↑↓  │  (12h half-life)
              └────────────┬──────────────┘
                           │ 4 trigger paths: black swan / regime
                           │ shift / accumulated conviction / cron
                           ▼
              ┌─────────────────────────┐
              │  SONAR DEEP-READS       │  ~200 word enriched summaries
              └────────────┬────────────┘
                           ▼
              ┌─────────────────────────┐
              │  REGIME NOWCASTER       │  XGBoost growth + inflation
              │  → Sector Resolution    │  → preferred instruments
              └────────────┬────────────┘
                           ▼
              ┌─────────────────────────┐
              │  CURRENT EVENT AGENT    │  + leading indicator catalog
              └────────────┬────────────┘
                           ▼
              │  HYPOTHESIS → ⏸ HITL GATE → ASSET SELECTION  │
              │  RESEARCH → BULL/BEAR → DEBATE → ⏸ HITL GATE │
              │  GUARD → PORTFOLIO → BROKER                   │
              └───────────────────────────────────────────────┘
```

---

## Highlights

- **Conviction-based triggers** — accumulated directional signals, not single-event reactions. Medium-significance headlines that individually wouldn't fire the pipeline can collectively trigger it when they all point the same direction.
- **Two-pass significance scoring** — borderline headlines get re-scored with Polymarket prediction market data and X/Twitter sentiment to separate real signals from noise.
- **Perplexity Sonar integration** — headlines enriched with ~200-word search-grounded summaries. Non-US calendar events (ECB, BoJ, OPEC) fetched in real-time.
- **Regime-aware pipeline** — XGBoost nowcasters (growth + inflation) label the macro environment. Agents receive regime context; asset selection prioritizes regime-aligned instruments.
- **Bitcoin in risk-on** — IBIT (BlackRock Bitcoin Trust ETF) available as a trade expression in Reflation regimes only.
- **Human-in-the-loop gates** — pipeline stalls after hypothesis and after debate verdicts until human approves via CLI.
- **Hypothesis-first funnel** — top-down macro reasoning. The schema rejects a thesis without kill criteria.
- **Constitutional governance** — `data/core_principles.md` is the human-edited constitution. Hard violations are deterministic vetoes; the LLM is short-circuited entirely.
- **Deterministic accounting floor** — `NAV_after = NAV_before − slippage − commission` enforced on every state transition.
- **Leading indicator catalog** — 15+ canonical macro indicators (ISM, jobless claims, yield curve, credit spreads). Current Event Agent maps headlines to these indicators; Hypothesis Agent references them.

---

## Repository layout

```
CKM-Capital/
├── README.md
├── pyproject.toml
├── config.yaml                     # tunable knobs (models, risk, triggers, enrichment)
│
├── data/
│   ├── core_principles.md          # human-edited constitution
│   ├── macro_leading_indicators.yaml
│   ├── growth_leading_indicators.yaml
│   ├── inflation_leading_indicators.yaml
│   ├── regime_sector_cheat_sheet.yaml
│   └── ism_manufacturing_pmi.csv   # INDPRO-based proxy for ISM PMI
│
├── src/castelino/
│   ├── config.py                   # typed Settings + env loader
│   ├── data/
│   │   ├── instruments.py          # tradable universe (~30 instruments + IBIT)
│   │   ├── leading_indicators.py   # canonical indicator catalog
│   │   └── openbb_adapter.py       # OpenBB SDK integration
│   ├── execution/
│   │   ├── pricing.py              # yfinance + FRED + OpenBB + cache
│   │   ├── portfolio.py            # Portfolio model + NAV history
│   │   ├── broker.py               # pure-function fill simulator
│   │   └── mark_loop.py            # daily mark + stop-loss execution
│   ├── memory/
│   │   ├── schemas.py              # discriminated union of journal entries
│   │   └── io.py                   # WriterIdentity-gated R/W matrix
│   ├── agents/
│   │   ├── base.py                 # OpenAI structured-output client
│   │   ├── current_event.py        # + Sonar deep-reads + indicator catalog
│   │   ├── hypothesis.py           # + macro_context + indicator reads
│   │   ├── asset_selection.py      # + regime-preferred instruments
│   │   ├── research/{web,technical,backtest,risk}.py
│   │   ├── bull.py · bear.py · debate.py  # all regime-aware
│   │   ├── guard.py                # hybrid: Python hard rules + LLM soft rules
│   │   ├── portfolio.py            # translates verdict → TradeOrder
│   │   └── curator.py              # weekly memory consolidation
│   ├── triggers/
│   │   ├── calendar.py             # FRED US + Sonar non-US calendar
│   │   ├── news.py                 # RSS + Sonar deep-reads + X sentiment
│   │   ├── significance.py         # two-pass scorer (directional + enriched)
│   │   ├── conviction.py           # directional conviction ledger
│   │   ├── polymarket.py           # Polymarket CLOB API integration
│   │   └── runner.py               # `castelino watch` — 4 trigger paths
│   ├── forecast/
│   │   ├── regime.py               # XGBoost growth + inflation nowcasters
│   │   ├── regime_sectors.py       # quadrant → sector/ETF mapping
│   │   └── search.py               # leading indicator search CLI
│   ├── orchestrator/
│   │   ├── state.py                # FundState (LangGraph state)
│   │   ├── graph.py                # the DAG + HITL gates
│   │   ├── approval.py             # approval queue (disk-persisted)
│   │   └── cli.py                  # `castelino` Typer app
│   ├── dashboard/                  # OpenBB Workspace integration (6 tabs)
│   └── reporting/
│       ├── equity_curve.py · exposure.py · attribution.py
│       ├── trade_card.py · dashboard.py
│
├── scripts/
│   ├── seed_book.py · reset_demo.py · replay.py
│   └── build_ism_pmi_proxy.py
│
└── tests/
```

---

## Requirements

- Python 3.11+
- An OpenAI API key (`gpt-5.5` + `gpt-5.4-mini`, or override in `config.yaml`)
- A Perplexity API key (for Sonar deep-reads, X sentiment, non-US calendar)
- A FRED API key (optional — for US economic calendar)
- `uv` recommended for dependency management

---

## Setup

```bash
# Clone
git clone https://github.com/ashcastelinocs124/CKM-Capital.git
cd CKM-Capital

# Install
uv venv --python 3.11 .venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# Configure secrets (.env is gitignored)
cat > .env <<EOF
OPENAI_API_KEY=sk-...
PERPLEXITY_API_KEY=pplx-...
FRED_API_KEY=...             # optional
EOF
chmod 600 .env

# Run tests (no network — LLMs and pricing are mocked)
pytest -q
```

---

## Usage

### Continuous trigger watcher

```bash
castelino watch --poll-minutes 15
```

Polls calendar + RSS every 15 min. Scores headlines, feeds the conviction ledger, and checks four trigger paths: black swan → regime shift → accumulated conviction → cron fallback.

### Fire a single pipeline pass

```bash
castelino run "ECB cuts deposit rate by 25bp" \
  --significance 0.85 --source news \
  --asset-classes "bond_etf,fx"
```

### Human-in-the-loop approval

```bash
castelino queue              # see pending approvals
castelino approve H-abc123   # approve a hypothesis
castelino reject V-def456 --reason "too correlated to existing book"
```

### Other commands

```bash
castelino mark                    # daily mark-to-market + stop-losses
castelino dashboard               # live HTML dashboard
castelino status                  # NAV + positions + journal counts
castelino report                  # regenerate charts + trade cards
castelino serve                   # OpenBB Workspace backend (port 7779)
castelino forecast-regime         # run XGBoost regime nowcaster
castelino growth-search           # explore growth leading indicators
castelino inflation-search        # explore inflation leading indicators
```

---

## Configuration

All tunable knobs live in [`config.yaml`](config.yaml):

```yaml
models:
  reasoning: "gpt-5.5"          # heavy nodes
  fast: "gpt-5.4-mini"          # fast nodes

enrichment:
  borderline_min: 0.4           # two-pass re-scoring range
  borderline_max: 0.8
  polymarket_enabled: true
  x_sentiment_enabled: true

conviction:
  half_life_hours: 12.0         # exponential decay window
  fire_threshold: 2.5           # single dimension sum to fire
  spread_threshold: 2.0         # |bullish - bearish| to fire
  cooldown_hours: 4.0           # min between conviction fires
  black_swan_min: 0.9           # instant-fire threshold

risk:
  position_max_pct_nav: 0.05    # constitutional 5% cap
  asset_class_max_pct_gross: 0.40
  drawdown_freeze_pct: 0.10
  vix_circuit_breaker: 40.0
```

The constitution ([`data/core_principles.md`](data/core_principles.md)) is the source of truth for rules; `config.yaml` holds numeric thresholds.

---

## Tests

```bash
pytest -q
```

No network or OpenAI calls in the test suite — `FakeLLMClient` and pricing stubs make end-to-end pipeline tests deterministic.

---

## Cost discipline

A typical pipeline run is ~$0.15–0.40 in OpenAI spend. The architecture minimizes waste:
- Hard-rule violations short-circuit the Portfolio Agent (no LLM call on vetoed trades)
- Two-pass scoring only enriches borderline headlines (2-5 per tick, not all 20-30)
- Sonar calls are cached (articles 24h, X sentiment 1h, calendar 12h)
- Polymarket API is free and public (no auth required)
- Pricing is cached (15-min LRU + on-disk)

---

## License

This repository is a portfolio piece. No commercial use intended.

## Acknowledgements

Built on `langgraph`, `openai`, `pydantic`, `yfinance`, FRED, OpenBB, Perplexity Sonar, Polymarket CLOB API, `xgboost`, `scikit-learn`.
