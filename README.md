# CKM Capital

A multi-asset macro hedge fund built as a **LangGraph DAG of LLM agents**, governed by a hard-coded constitution and a deterministic accounting floor. The fund trades equities, fixed income, commodities, FX, and Bitcoin (via IBIT ETF in risk-on regimes) through a **hypothesis-first** funnel: every trade traces back to a falsifiable macro thesis, and every dollar of slippage is provably accounted for.

This is a portfolio piece — a working simulation, not connected to a real broker.

---

## What it does

The system monitors macro news, economic data, prediction markets, and **live policy speech audio** through a **multi-layered trigger system** that fires the pipeline based on accumulated conviction — not just single headlines. When triggered, a **9-stage agent pipeline** produces 0–3 sized trades:

### Trigger Layer (6 paths)

1. **Black swan override** — single headline with materiality ≥ 0.9 fires instantly (war, unscheduled FOMC, sovereign default).
2. **Regime shift** — XGBoost nowcaster detects growth/inflation quadrant flip (Reflation → Stagflation, etc.).
3. **Accumulated conviction** — a directional conviction ledger tracks headlines with exponential decay (12h half-life). Fires when growth or inflation signals accumulate past threshold. This catches the slow-burn "five headlines all pointing to Eurozone weakness" that no single headline triggers.
4. **Calendar** — high-impact macro releases due within the polling window (FOMC, CPI, NFP, ECB, BoJ).
5. **Speech deviation** — live Fed/ECB audio streamed through Deepgram STT, scored sentence-by-sentence on a hawkish/dovish lexicon, fires when a 5-sentence rolling window deviates >1.5σ from the speaker's own 12-month rhetorical baseline. A dovish Powell turning hawkish carries far more information than the words themselves.
6. **Cron fallback** — nothing fired for 24h, low-significance reassessment.

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

The system is split into three layers — **trigger detection** (when does the pipeline fire?), **agent reasoning** (what trade?), and **enforcement** (is the trade allowed?). Color-coded below by layer.

### Full pipeline

```
══════════════════════════════════════════════════════════════════════════
                          TRIGGER LAYER (deterministic + LLM scorer)
══════════════════════════════════════════════════════════════════════════

   FRED + yfinance     RSS feeds      Sonar non-US      FIGURE SOURCES
   (calendar)          (headlines)    (calendar)        (audio + tweets)
        │                  │                │                │
        ▼                  ▼                ▼                ▼
  ┌──────────┐       ┌──────────┐    ┌────────────┐  ┌──────────────────────┐
  │ Calendar │       │ ~20 head-│    │ Calendar   │  │ Audio: Deepgram      │
  │ events   │       │ lines    │    │ events     │  │   • Powell · Williams│
  └────┬─────┘       └─────┬────┘    └─────┬──────┘  │   · Bullard · Waller │
       │                   │               │         │ X API: tweet polling │
       │                   │               │         │   • Trump            │
       │           ┌───────▼─────────┐     │         │   (since_id, 5 min)  │
       │           │ SIGNIFICANCE    │ P1  │         └──────┬───────────────┘
       │           │ SCORER (LLM)    │     │                │
       │           │ → 0–1 + growth  │     │         ┌──────▼────────────┐
       │           │   /inflation    │     │         │ FigurePost stream │
       │           │   direction     │     │         │ (uniform across   │
       │           └───────┬─────────┘     │         │  audio + tweets)  │
       │                   │               │         └──────┬────────────┘
       │           ┌───────▼──────────┐    │                │
       │           │ TECHNICAL        │    │         ┌──────▼──────────────────┐
       │           │ READINESS x0.7-1.5│   │         │ MULTI-LEXICON SCORER    │
       │           │ (RSI/MACD/OBV)   │    │         │ (per-figure config)     │
       │           └───────┬──────────┘    │         │ Powell → hawkish_dovish │
       │                   │               │         │ Trump  → trade_protect. │
       │           ┌───────▼──────────┐    │         │       + fed_pressure    │
       │           │ TWO-PASS ENRICH  │ P2 │         │       + regulatory(×4)  │
       │           │ Polymarket + X   │    │         └──────┬──────────────────┘
       │           │ (borderlines)    │    │                │
       │           └───────┬──────────┘    │         ┌──────▼──────────────────────┐
       │                   │               │         │ DEVIATION GATE              │
       │           ┌───────▼──────────┐    │         │ z-score vs persona baseline │
       │           │ CONVICTION       │◀───┼─────────┤ Powell:  >1.5σ on hawk/dove │
       │           │ LEDGER           │    │         │ Trump :  >1.5σ on trade,    │
       │           │ (12h decay)      │    │         │          fed-pressure       │
       │           └───────┬──────────┘    │         │  + movement filter          │
       │                   │               │         └──────┬──────────────────────┘
       │                   │               │                │
       │                   │               │         ┌──────▼──────────────────────┐
       │                   │               │         │ STAGE B (LLM gate)          │
       │                   │               │         │ + FigureProfile RAG         │
       │                   │               │         │   Powell card · Trump card  │
       │                   │               │         │   "starting Monday" tells,  │
       │                   │               │         │   71% follow-through, etc.  │
       │                   │               │         └──────┬──────────────────────┘
       │                   │               │                │
       │                   │               │           emit FIGURE_DEVIATION
       │                   │               │           with directional_tags
       │                   │               │           (Powell→[rates_up,gold_dn] ·
       │                   │               │            Trump→[usd_up,em_dn,semis])
       └────────┬──────────┼───────────────┘                │
                │          │                                │
                ▼          ▼                                ▼
       ╔══════════════════════════════════════════════════════╗
       ║  6 PARALLEL TRIGGER PATHS                            ║
       ║  ① Black swan        single ≥ 0.9                   ║
       ║  ② Regime shift      XGBoost label flip             ║
       ║  ③ Conviction        decayed sum ≥ 2.5              ║
       ║  ④ Calendar          high-impact event imminent     ║
       ║  ⑤ Figure deviation  >1.5σ + LLM confirms (audio +   ║
       ║                       X tweets, multi-lexicon)       ║
       ║  ⑥ Cron fallback     24h since last fire            ║
       ╚════════════════╤═════════════════════════════════════╝
                        │
══════════════════════│════════════════════════════════════════════════════
                      │     AGENT REASONING (LangGraph DAG)
══════════════════════│════════════════════════════════════════════════════
                      │
        ┌─────────────▼─────────────┐
        │ SONAR DEEP-READS          │  ~200 word search-grounded
        │ (significant headlines)   │  summaries per headline
        └─────────────┬─────────────┘
                      │
        ┌─────────────▼─────────────┐
        │ REGIME NOWCASTER          │  XGBoost: growth × inflation
        │ → Sector Resolution       │  → 4 quadrants → preferred ETFs
        └─────────────┬─────────────┘
                      │
        ┌─────────────▼─────────────┐
        │ CURRENT EVENT AGENT       │  fast LLM
        │ (only LLM that sees       │  → WorldStateBrief
        │  uncurated text)          │     + leading indicator reads
        └─────────────┬─────────────┘
                      ▼
        ┌─────────────────────────┐
        │ HYPOTHESIS AGENT        │  reasoning LLM
        │ (mandatory kill criteria│  → falsifiable thesis
        │  enforced by schema)    │     + regime + conviction
        └─────────────┬───────────┘
                      ▼
        ┌─────────────────────────┐
        │ ⏸ HITL GATE — HYPOTHESIS│  pipeline blocks until human
        │ (CLI or Dashboard)      │  approves / rejects with notes
        └─────────────┬───────────┘
                      ▼
        ┌─────────────────────────┐
        │ ASSET SELECTION AGENT   │  reasoning LLM
        │ (regime-aware: prefers  │  → 1–3 TradeExpressions
        │  regime ETFs)           │
        └─────────────┬───────────┘
                      ▼  for each expression:
        ┌─────────────────────────────────────┐
        │ RESEARCH DESK (4 parallel agents)   │  hybrid:
        │ Web · Technical · Backtest · Risk   │  Python computes,
        │ → sealed ResearchBundle             │  LLM interprets
        └─────────────┬───────────────────────┘
                      ▼
        ┌─────────────────────────┐
        │ BULL  ↔  BEAR           │  reasoning LLMs
        │ adversarial debate      │  argue opposing reads
        └─────────────┬───────────┘
                      ▼
        ┌─────────────────────────┐
        │ DEBATE AGENT            │  reasoning LLM
        │ proceed | reject |      │  cites the decisive
        │ modify (size mult)      │  argument
        └─────────────┬───────────┘
                      ▼
        ┌─────────────────────────┐
        │ ⏸ HITL GATE — DEBATE    │  human reviews verdict
        │                         │  before execution
        └─────────────┬───────────┘
                      │
══════════════════════│════════════════════════════════════════════════════
                      │     ENFORCEMENT LAYER (deterministic)
══════════════════════│════════════════════════════════════════════════════
                      ▼
        ┌─────────────────────────┐
        │ PRINCIPLES GUARD        │  hybrid
        │ ─────────────────────── │  HARD rules: Python (veto)
        │ H1–H5 hard rules        │  SOFT rules: LLM (warn/amend)
        │ S1–S6 soft rules        │
        └─────────────┬───────────┘
                      ▼
        ┌─────────────────────────┐
        │ RISK-OFF GATE           │  XGBoost classifier
        │ ─────────────────────── │  P(SPY drawdown >5% next month)
        │ 4 tiers: pass/downsize/ │  → size_multiplier per trade
        │ veto/contrarian-amplify │
        └─────────────┬───────────┘
                      ▼
        ┌─────────────────────────┐
        │ PORTFOLIO AGENT         │  reasoning LLM
        │ (must cite kill crit;   │  → TradeOrder
        │  defense-in-depth veto) │
        └─────────────┬───────────┘
                      ▼
        ┌─────────────────────────┐
        │ BROKER (pure function)  │  deterministic
        │ fill + slippage + comm  │  → portfolio.json
        │ NAV invariant enforced  │
        └─────────────────────────┘

  out-of-band ─ MARK LOOP (daily)        re-prices, snapshots NAV, fires stops
  out-of-band ─ MEMORY CURATOR (weekly)  distills lessons → long_term_journal.md
```

### The 10 named agents

| # | Agent | Tier | Output | Role |
|---|-------|------|--------|------|
| 1 | **Significance Scorer** | fast | `HeadlineScore[]` | Score every headline 0–1 + growth/inflation direction |
| 2 | **Current Event** | fast | `WorldStateBrief` | Compress news to structured brief; only place LLM sees uncurated text |
| 3 | **Hypothesis** | reasoning | `Hypothesis` | Form one falsifiable thesis with mandatory kill criteria |
| 4 | **Asset Selection** | reasoning | `TradeExpression[]` | Pick 1–3 instruments that express the thesis |
| 5 | **Web Research** | fast | `WebResearch` | Per-instrument news/sentiment summary |
| 6 | **Technical Analysis** | fast | `TAReport` | RSI/MACD/SMA/vol — Python computes, LLM interprets |
| 7 | **Backtest** | fast | `BacktestReport` | Similar-setup hit rate over 10y history |
| 8 | **Risk** | fast | `RiskReport` | Realized vol, correlation to book, marginal VaR |
| 9 | **Bull** | reasoning | `BullCase` | Argues for the trade with research evidence |
| 10 | **Bear** | reasoning | `BearCase` | Argues against the trade with research evidence |
| 11 | **Debate** | reasoning | `Verdict` | Adjudicates Bull vs Bear; cites decisive argument |
| 12 | **Principles Guard** | reasoning + Python | `GuardDecision` | Hard rules deterministic; soft rules LLM-judged |
| 13 | **Portfolio** | reasoning | `PortfolioDecision` + `TradeOrder` | Translates verdict to order; cites kill criterion |
| 14 | **Memory Curator** | reasoning | `LongTermLesson[]` | Weekly: distills patterns from short-term journal |

Plus three deterministic gates with no LLM:
- **Regime Nowcaster** — XGBoost growth + inflation classifiers; outputs quadrant + probabilities
- **Risk-Off Gate** — XGBoost drawdown classifier; outputs size multiplier per trade
- **Technical Readiness** — RSI/MACD/OBV alignment; outputs materiality multiplier on headlines

### Live Speech Sub-Pipeline (auto-spawned per calendar event)

Wakes up before scheduled FOMC pressers, ECB rate decisions, and Powell speeches. Six-stage flow runs in a background thread per event:

| Stage | Purpose |
|-------|---------|
| **Orchestrator** | Polls calendar; if event has `has_live_stream` and is within 5 min, spawns a daemon thread |
| **Deepgram STT** | Streams audio → text events (`nova-2-finance` model, financial-vocab tuned) |
| **Sentence segmenter** | Stream of partials → complete sentences (respects "Mr.", "U.S.", abbrevs) |
| **Lexicon scorer** | Each sentence → hawkish/dovish scalar score using `data/lexicons/hawkish_dovish_v1.yaml`. Same scorer used for offline persona baseline (load-bearing invariant) |
| **Deviation detector** | Rolling 5-sentence window → z-score vs the speaker's 12-month rhetorical baseline (half-life 6 months). Threshold: 1.5σ |
| **LLM gate (Stage B)** | `gpt-4o-mini` confirms the deviation is a structural policy shift, not a quote/hypothetical/aside |
| **Emitter** | Constructs `TriggerRecord(source=SPEECH_DEVIATION)` with cooldown (one fire per `event_id`) |

The downstream pipeline (Hypothesis → Asset Selection → Research → Bull/Bear → Debate → Guard → Risk-Off Gate → Portfolio) is unchanged — speech is just a sixth way the trigger fires, with a richer `raw_event_data` payload (speaker, deviation magnitude, deviating sentences).

**Why this matters:** text headlines are already priced by the time they hit RSS. Live tone shifts on policy speeches are not. A dovish Powell turning hawkish carries more information than the words themselves — the system reacts within seconds of the words being spoken.

CLI:
- `castelino persona-refresh --speaker powell` — rebuild speaker baseline from historical corpus
- `castelino speech-test --transcript-file path --dry-run` — replay a transcript through the listener

### Schemas enforce safety

Every agent's output is a **Pydantic model with hard constraints**. Examples:

- `Hypothesis.kill_criteria` → `min_length=1` — the LLM literally cannot emit a thesis without falsification conditions
- `TradeExpression.target_size_pct_nav` → `gt=0.0, le=0.05` — schema rejects > 5% NAV before Guard ever sees it
- `Verdict.size_multiplier` → `ge=0.0, le=2.0` — bounded
- `WriterIdentity` enum + R/W matrix — memory I/O refuses out-of-matrix writes

---

## Highlights

- **Conviction-based triggers** — accumulated directional signals, not single-event reactions. Medium-significance headlines that individually wouldn't fire the pipeline can collectively trigger it when they all point the same direction.
- **Persona-relative figure-deviation engine** — multi-source / multi-lexicon tone-scoring tracks named public figures (Powell + Fed officials via Deepgram audio, Trump via X API v2 tweet polling). Each figure scores against their *own* twelve-month rhetorical baseline, so a dovish Powell turning hawkish — or Trump escalating from "considering tariffs" to "starting Monday" — produces a signal that absolute-tone scoring would miss. Trump scores on three lexicons in parallel (`trade_protectionist_v1`, `fed_pressure_v1`, `regulatory_stance_v1` with crypto/oil/defence/tech sub-axes); a single tweet can fire on multiple dimensions independently.
- **FigureProfile RAG layer** — per-figure Chroma corpus (track record, behavioural patterns, tweet→outcome examples, current cabinet, rhetorical tells) retrieved into Stage B confirmation and the Hypothesis Agent's analogy reasoning. Stage B sees behavioural-pattern slices ("starting Monday" → 71% follow-through with named advisors); the Hypothesis Agent sees outcome examples and track record for analogy-based horizon/conviction calibration.
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
│   ├── ism_manufacturing_pmi.csv   # INDPRO-based proxy for ISM PMI
│   ├── lexicons/                   # versioned tone-deviation lexicons
│   │   ├── hawkish_dovish_v1.yaml  #   Fed speech (Powell, Bullard, Williams)
│   │   ├── trade_protectionist_v1.yaml  # Trump trade rhetoric
│   │   ├── fed_pressure_v1.yaml         # Trump Fed-pressuring rhetoric
│   │   └── regulatory_stance_v1.yaml    # Trump sectoral stance (4 sub-axes)
│   ├── personas/                   # audio-source SpeakerPersona files
│   │   └── <speaker_id>/<lexicon>.json  # nested layout (Wave 2.3)
│   ├── figure_baselines/           # generic FigureBaseline files (per fig × lex)
│   └── figure_profiles/            # per-figure RAG corpus (Chroma + sources/)
│       └── <figure_id>/{sources/,index.json,card.json,version.json}
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
│   │   ├── conviction.py           # directional conviction ledger (12h decay)
│   │   ├── readiness.py            # technical readiness multiplier (RSI/MACD/OBV)
│   │   ├── polymarket.py           # Polymarket CLOB API integration
│   │   ├── risk_gate.py            # 4-tier risk-off enforcement gate
│   │   ├── figure_deviation/       # multi-source / multi-lexicon tone-deviation
│   │   │   ├── models.py           #   FigurePost, FigureBaseline, LexiconScore,
│   │   │   │                       #   FigureDeviationTrigger
│   │   │   ├── speech_models.py    #   audio-source-specific types (legacy)
│   │   │   ├── source/
│   │   │   │   ├── base.py         #   FigurePostSource ABC
│   │   │   │   ├── audio.py        #   Deepgram → SpeechSegment → FigurePost
│   │   │   │   └── x_api.py        #   X API v2 tweet polling (since_id)
│   │   │   ├── scorer.py           #   multi-lexicon scorer + sub-axis support
│   │   │   ├── baseline.py         #   audio-source baseline builder (legacy)
│   │   │   ├── baseline_store.py   #   per-(figure × lexicon) FigureBaseline
│   │   │   │                       #   with version-mismatch hard-fail
│   │   │   ├── gate.py             #   per-pair Stage A z-score gate
│   │   │   ├── deviation.py        #   single-shot z-score helper (legacy)
│   │   │   ├── stage_b.py          #   LLM confirmation + profile retrieval
│   │   │   ├── dispatcher.py       #   fan-out across N lexicons + cooldown
│   │   │   ├── polling.py          #   poll all non-audio sources on cadence
│   │   │   ├── conviction_feed.py  #   tag→growth/inflation translation feed
│   │   │   ├── orchestrator.py     #   audio listener orchestration (legacy)
│   │   │   ├── listener.py         #   stream → SpeechSegment per sentence
│   │   │   ├── stt_deepgram.py     #   Deepgram nova-2-finance integration
│   │   │   ├── persona.py          #   audio-source persona builder (nested layout)
│   │   │   ├── llm_gate.py         #   speech-specific Stage B (legacy)
│   │   │   ├── emitter.py          #   constructs FIGURE_DEVIATION trigger
│   │   │   ├── queue.py            #   hand-off to runner.tick()
│   │   │   ├── streams.py · stt.py · events.py
│   │   │   ├── scrapers/fed.py     #   federalreserve.gov speech scraper
│   │   │   └── profile/            #   FigureProfile RAG layer
│   │   │       ├── models.py       #     FigureCard, RetrievedChunk, Chunk
│   │   │       ├── store.py        #     Chroma-shaped per-figure store
│   │   │       └── hypothesis_helpers.py  # Hypothesis Agent context builder
│   │   └── runner.py               # `castelino watch` — 6 trigger paths
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
│   ├── build_ism_pmi_proxy.py
│   └── migrate_persona_layout.py   # data/personas/<id>.json → nested (reversible)
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
DEEPGRAM_API_KEY=...         # optional — for the live speech listener
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
castelino serve                   # FastAPI backend + React frontend (port 7779)
castelino forecast-regime         # run XGBoost regime nowcaster
castelino forecast-risk           # run XGBoost risk-off classifier
castelino growth-search           # explore growth leading indicators
castelino inflation-search        # explore inflation leading indicators
castelino persona-refresh --speaker powell   # rebuild speaker baseline from corpus
castelino speech-test --transcript-file PATH --dry-run    # replay transcript
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

speech:
  enabled: true
  stt_provider: deepgram
  deepgram_model: nova-2-finance
  lexicon_version: hawkish_dovish_v1
  window_size: 5                # rolling sentence window
  deviation_threshold_sigma: 1.5
  half_life_months: 6.0         # baseline decay
  baseline_window_days: 365
  llm_model: gpt-4o-mini        # Stage B structural-shift gate
  speakers:
    - id: powell
      full_name: Jerome H. Powell
      role: Chair, Federal Reserve

risk_gate:
  caution_min: 0.3              # P(risk-off) above which to start downsizing
  caution_size_mult: 0.5        # 0.3-0.6: half-size risk-on trades
  danger_min: 0.6               # 0.6-0.85: veto risk-on equity
  capitulation_min: 0.85        # ≥0.85: contrarian flip
  capitulation_amplify: 1.3

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

### Backtest regression suite

`tests/backtest/` holds component-level regression tests over the deterministic
layer (risk-off gate, figure-deviation Powell scorer, `materialize_order`).
Each test is hand-curated against a historical event or a property over
generated cases.

Run it:

```bash
pytest -m backtest                                   # CI go/no-go
castelino backtest-regression                        # diagnostic report
castelino backtest-regression --components risk_off  # one component
```

Companion to the full-pipeline backtest in `src/castelino/backtest/`
(`docs/plans/2026-05-08-backtest-design.md`).

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
