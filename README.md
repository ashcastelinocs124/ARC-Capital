# Castelino Capital

A multi-asset macro hedge fund built as a **LangGraph DAG of LLM agents**, governed by a hard-coded constitution and a deterministic accounting floor. The fund trades equities, fixed income, commodities, and FX through a **hypothesis-first** funnel: every trade traces back to a falsifiable macro thesis, and every dollar of slippage is provably accounted for.

This is a portfolio piece — a working simulation, not connected to a real broker.

---

## What it does

For each macro event (FOMC, CPI release, OPEC decision, news surprise), the system runs a **9-stage agent pipeline** that produces 0–3 sized trades:

1. **Trigger** detects the event (calendar / news significance ≥ 0.7 / 24h cron fallback).
2. **Current Event Agent** compresses raw news into a structured `WorldStateBrief` — the only place an LLM sees uncurated text (prompt-injection containment).
3. **Hypothesis Agent** forms one falsifiable thesis with mandatory `kill_criteria`.
4. **Asset Selection Agent** picks 1–3 instruments across asset classes that best express the thesis.
5. **Research Desk** (4 parallel agents — web, technical, backtest, risk) builds a sealed evidence bundle. Numbers are computed in Python; the LLM only writes the natural-language interpretation.
6. **Bull and Bear** agents argue opposing reads of the same evidence.
7. **Debate Agent** adjudicates, citing the specific argument that tipped the call.
8. **Principles Guard** vets the trade. Hard rules (5% NAV cap, 40% asset-class cap, 10% drawdown freeze, VIX circuit breaker) are checked deterministically; soft rules (no averaging into thesis-broken trades, ≤2 trades per regime, kill-criterion citation) are LLM-evaluated.
9. **Portfolio Agent** translates the verdict into a concrete `TradeOrder`. A pure-function broker simulates the fill and the deterministic accounting layer updates `portfolio.json`.

A **mark loop** runs daily (out-of-band) to re-price positions, snapshot NAV, and trigger any stop-losses. A **memory curator** runs weekly to distill recurring patterns into long-term lessons that future agents read.

---

## Highlights

- **Hypothesis-first funnel** — top-down macro reasoning, not stock-picking. The schema literally rejects a thesis without kill criteria.
- **Constitutional governance layer** — `data/core_principles.md` is the human-edited constitution. Hard violations are deterministic vetoes; the LLM is short-circuited entirely so a future prompt regression cannot override the safety floor.
- **Asymmetric R/W memory architecture** — every component declares a `WriterIdentity`. The memory I/O layer refuses writes that don't match the design's read/write matrix. Reads are unrestricted; writes are gated.
- **Deterministic accounting floor** — `NAV_after = NAV_before − slippage_cost − commission_cost` is enforced on every state transition. The LLM never does arithmetic that hits the book.
- **Hybrid agents** — TA / Backtest / Risk / Guard pair Python computation with LLM interpretation. The LLM cannot lie about RSI(14) because it's instructed to copy verbatim.
- **Live multi-tier OpenAI integration** — `gpt-5.5` for reasoning nodes (Hypothesis, Asset Selection, Bull, Bear, Debate, Guard, Portfolio, Curator), `gpt-5.4-mini` for fast nodes (Current Event, Web, TA, Backtest, Risk, news significance).

---

## Architecture

```
                  ┌─────────────────────────┐
   real world ───►│  TRIGGER LAYER          │  function (no LLM)
                  └────────────┬────────────┘
                               ▼
                  ┌─────────────────────────┐
                  │  CURRENT EVENT AGENT    │  fast LLM
                  │  raw news → brief       │  ← only place LLM sees raw text
                  └────────────┬────────────┘
                               ▼
                  ┌─────────────────────────┐
                  │  HYPOTHESIS AGENT       │  reasoning LLM
                  │  (mandatory kill_crit.) │
                  └────────────┬────────────┘
                               ▼
                  ┌─────────────────────────┐
                  │  ASSET SELECTION AGENT  │  reasoning LLM
                  │  → 1–3 expressions      │
                  └────────────┬────────────┘
                               │ for each expression:
                               ▼
        ┌────────────────────────────────────────────┐
        │  RESEARCH DESK (4 agents)                  │  hybrid:
        │  Web · Technical · Backtest · Risk         │  Python compute,
        └────────────────────┬───────────────────────┘  LLM interpret
                             ▼
              ┌─────────────────────────────────┐
              │  BULL  ↔  BEAR                  │  reasoning LLMs
              └────────────────┬────────────────┘
                               ▼
                  ┌─────────────────────────┐
                  │  DEBATE AGENT           │  reasoning LLM
                  │  proceed | reject |     │  cites the specific
                  │  modify (size mult)     │  argument that won
                  └────────────┬────────────┘
                               ▼
   ─── ABOVE: agent decisions ─┼─ BELOW: deterministic accounting ───
                               ▼
                  ┌─────────────────────────┐
                  │  PRINCIPLES GUARD       │  hybrid
                  │  HARD: Python (veto)    │
                  │  SOFT: LLM (warn/amend) │
                  └────────────┬────────────┘
                               ▼
                  ┌─────────────────────────┐
                  │  PORTFOLIO AGENT        │  reasoning LLM
                  │  must cite kill crit.   │
                  └────────────┬────────────┘
                               ▼
                  ┌─────────────────────────┐
                  │  BROKER (pure function) │
                  │  fill + slippage + comm │
                  │  → portfolio.json       │
                  └─────────────────────────┘

  out-of-band   MARK LOOP (daily)        — re-prices, snapshots NAV, fires stops
  out-of-band   MEMORY CURATOR (weekly)  — distills lessons, prunes ST
```

Full architectural design: [`docs/plans/2026-05-03-castelino-capital-design.md`](docs/plans/2026-05-03-castelino-capital-design.md).

---

## Repository layout

```
Castelino-Capital/
├── README.md
├── pyproject.toml
├── config.yaml                     # tunable knobs (models, risk caps, RSS feeds)
│
├── data/
│   └── core_principles.md          # human-edited constitution
│
├── src/castelino/
│   ├── config.py                   # typed Settings + env loader
│   ├── data/instruments.py         # tradable universe (~30 instruments)
│   ├── execution/
│   │   ├── pricing.py              # yfinance + FRED + cache + bad-data guards
│   │   ├── portfolio.py            # Portfolio model + NAV history
│   │   ├── broker.py               # pure-function fill simulator
│   │   └── mark_loop.py            # daily mark + stop-loss execution
│   ├── memory/
│   │   ├── schemas.py              # discriminated union of journal entries
│   │   └── io.py                   # WriterIdentity-gated R/W matrix
│   ├── agents/
│   │   ├── base.py                 # OpenAI structured-output client + FakeLLMClient
│   │   ├── current_event.py
│   │   ├── hypothesis.py
│   │   ├── asset_selection.py
│   │   ├── research/{web,technical,backtest,risk}.py
│   │   ├── bull.py · bear.py · debate.py
│   │   ├── guard.py                # hybrid: Python hard rules + LLM soft rules
│   │   ├── portfolio.py            # translates verdict → TradeOrder
│   │   └── curator.py              # weekly memory consolidation
│   ├── triggers/
│   │   ├── calendar.py             # curated econ calendar
│   │   ├── news.py                 # RSS ingestion + dedupe
│   │   ├── significance.py         # batched LLM headline classifier
│   │   └── runner.py               # `castelino watch` polling loop
│   ├── orchestrator/
│   │   ├── state.py                # FundState (LangGraph state)
│   │   ├── graph.py                # the DAG
│   │   └── cli.py                  # `castelino` Typer app
│   └── reporting/
│       ├── equity_curve.py         # equity + drawdown PNGs
│       ├── exposure.py             # by class + by instrument
│       ├── attribution.py          # by instrument + by hypothesis
│       ├── trade_card.py           # per-fill HTML cards
│       └── dashboard.py            # live single-page dashboard
│
├── scripts/
│   ├── seed_book.py                # demo: open 3 small positions
│   ├── reset_demo.py               # wipe journals + portfolio
│   └── replay.py                   # backfill from cached news
│
└── tests/                          # 83 tests, ~1.5s
    ├── test_accounting_invariant.py    # the sacred test
    ├── test_broker_fills.py
    ├── test_guard_hard_rules.py
    ├── test_mark_loop_journal.py
    ├── test_memory_io_asymmetry.py
    ├── test_pipeline_e2e.py            # mocked LLMs, full DAG
    ├── test_principles_yaml_schema.py
    ├── test_trigger_layer.py
    └── test_curator_and_reports.py
```

---

## Requirements

- Python 3.11+
- An OpenAI API key with access to `gpt-5.5` and `gpt-5.4-mini` (or override the model IDs in `config.yaml`)
- A FRED API key (optional — falls back to keyless CSV endpoint)
- `uv` recommended for dependency management

---

## Setup

```bash
# Clone
git clone https://github.com/ashcastelinocs124/Castelino-Capital.git
cd Castelino-Capital

# Install
uv venv --python 3.11 .venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# Configure secrets (.env is gitignored)
cat > .env <<EOF
OPENAI_API_KEY=sk-...
FRED_API_KEY=...        # optional
EOF
chmod 600 .env

# Run the test suite (no network required — LLMs and pricing are mocked)
pytest -q
```

---

## Usage

### Fire a single pipeline pass

```bash
castelino run "Fed signals pause as core PCE softens to 2.4% YoY" \
  --significance 0.85 \
  --source news \
  --asset-classes "bond_etf,equity,fx"
```

This runs the full DAG: trigger → world state → hypothesis → asset selection → research → debate → guard → portfolio → fills. ~12–30 LLM calls, ~$0.15–0.40 on `gpt-5.5` for the heavy nodes.

### Live position dashboard

```bash
castelino dashboard
```

Renders `reports/dashboard.html` and opens it in the browser. Shows:
- 6 KPI tiles (NAV, cash, gross/net exposure, unrealized + realized P&L)
- Open positions table with live marks, % NAV, unrealized P&L, stop-losses, parent hypothesis
- Recent fills (clickable → per-trade HTML cards with full debate transcript)
- Recent hypotheses, triggers, and principle warnings
- Charts: equity curve, drawdown, exposure by class/instrument, attribution by instrument/hypothesis

Auto-refreshes every 60s. Re-prices every position via live yfinance/FRED on each render.

### Daily mark loop

```bash
castelino mark
```

Marks every open position to live prices, appends a NAV snapshot, executes any synthetic stop-loss orders, journals the fills, and updates `data/exposure_snapshot.json`.

### Continuous trigger watcher

```bash
castelino watch --poll-minutes 15
```

Polls calendar + RSS every 15 min. Fires the pipeline when significance ≥ 0.7, or daily as a cron fallback.

### Other commands

```bash
castelino status                  # tabular NAV + positions + journal counts
castelino report                  # regenerate all charts + trade cards + dashboard
castelino replay --days 30        # backfill from cached news + calendar
castelino seed                    # open 3 demo positions
castelino reset --yes             # wipe journals + portfolio (demo only)
```

---

## Configuration

All tunable knobs live in [`config.yaml`](config.yaml):

```yaml
fund:
  initial_nav: 1000000.0

models:
  reasoning: "gpt-5.5"          # heavy nodes
  fast: "gpt-5.4-mini"          # fast nodes
  significance: "gpt-5.4-mini"  # news classifier

triggers:
  cron_fallback_hours: 24
  news_significance_min: 0.7
  rss_feeds: [reuters, fed-press, ecb-press]

risk:
  position_max_pct_nav: 0.05         # constitutional 5% cap
  asset_class_max_pct_gross: 0.40    # constitutional 40% cap
  drawdown_freeze_pct: 0.10
  vix_circuit_breaker: 40.0

execution:
  slippage_bps:
    equity: 5
    bond_etf: 5
    commodity_etf: 10
    futures: 15
    fx: 8
```

The constitution itself ([`data/core_principles.md`](data/core_principles.md)) is the source of truth for the *rules* (H1–H5 hard, S1–S6 soft); `config.yaml` only holds numeric thresholds.

---

## Tests

```bash
pytest -q
```

83 tests, ~1.5 seconds. No network or OpenAI calls in the test suite — the `FakeLLMClient` and a yfinance/FRED stub make end-to-end pipeline tests deterministic.

Highlights:
- `test_accounting_invariant.py` — the **sacred test**. NAV_after = NAV_before − slippage − commission, parametrized across all asset classes including over-close edge cases.
- `test_memory_io_asymmetry.py` — every R/W-matrix entry is verified; out-of-band writers raise `WriteForbidden`.
- `test_pipeline_e2e.py` — full DAG runs with `FakeLLMClient`; asserts journal entries, fills, and that hard vetoes structurally short-circuit the Portfolio Agent (no LLM call when constitutional rules are violated).
- `test_guard_hard_rules.py` — every H1–H5 hard rule + VIX-outage skip + 5d-PnL freeze.
- `test_mark_loop_journal.py` — stop-loss fills are journalled with `WriterIdentity.MARK_LOOP` so trade cards / attribution / curator all see them.

---

## Cost discipline

A typical pipeline run on `gpt-5.5` + `gpt-5.4-mini` is ~$0.15–0.40 in OpenAI spend. The architecture is built so:
- Hard-rule violations short-circuit the Portfolio Agent LLM (no call wasted on a vetoed trade).
- Hybrid agents only ask the LLM to interpret — the math is in Python.
- Trigger filtering is one batched fast-tier call.
- Pricing is cached (15-min in-memory LRU + on-disk parquet) so the same yfinance ticker is fetched at most a few times per day.

---

## License

This repository is a portfolio piece. No commercial use intended.

## Acknowledgements

Built on top of `langgraph`, `openai`, `pydantic`, `yfinance`, FRED.
