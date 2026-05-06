# OpenBB Integration Design

## Summary

Integrate OpenBB Platform into the Castelino Capital pipeline across three surfaces: data layer (primary pricing + research data), dashboard (OpenBB Workspace app), and human-in-the-loop approval gates.

## Architecture: Embedded SDK + Shared Module (Approach C)

```
┌─────────────────────────────────────────────────────────────┐
│                    castelino package                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  src/castelino/data/openbb_adapter.py   ← SDK wrapper        │
│       │                                                      │
│       ├── pricing.py (primary source, fallback to yf/fred)   │
│       ├── research agents (fundamentals, TA, screening)      │
│       └── dashboard app (live market widgets)                 │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│  src/castelino/dashboard/              ← FastAPI app         │
│       ├── main.py        (FastAPI + CORS + endpoints)        │
│       ├── widgets.json   (widget registry)                   │
│       ├── apps.json      (layout/tabs)                       │
│       └── endpoints/     (grouped by tab)                    │
│            ├── portfolio.py   (NAV, positions, fills)         │
│            ├── macro.py       (indicators, calendar, news)    │
│            ├── research.py    (TA, screening, correlations)   │
│            ├── risk.py        (exposure, attribution)         │
│            ├── agents.py      (hypotheses, triggers, logs)    │
│            └── approvals.py   (HITL queue)                    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

The dashboard imports directly from `castelino.*` (Portfolio.load(), memio.read_short_term(), pricing.history()) — no separate state files to sync.

## Data Layer: OpenBB Adapter

Single wrapper module `src/castelino/data/openbb_adapter.py`:

- Initializes OpenBB SDK once with PAT from `OPENBB_PAT` env var
- Exposes domain-specific methods:
  - **Pricing:** `latest_price()`, `history()`
  - **Technical Analysis:** `technical_indicators()`, `moving_averages()`
  - **Fundamentals:** `income_statement()`, `balance_sheet()`, `analyst_estimates()`, `earnings_calendar()`
  - **Screening:** `screen_equities()`, `sector_performance()`
  - **Risk/Quant:** `correlation_matrix()`, `volatility()`
  - **Macro/Economy:** `economic_indicators()`, `economic_calendar()`, `yield_curve()`, `news()`

### Pricing Fallback Chain

```
pricing.py:latest() →
  1. Try openbb_adapter.latest_price(symbol) [PRIMARY]
  2. Fallback: yfinance adapter (existing)
  3. Fallback: FRED adapter (existing, for yields)
```

OpenBB failures are never fatal. Adapter logs warnings, raises PricingError which existing validation handles.

### Integration with Existing Modules

| Module | Change |
|--------|--------|
| `pricing.py` | OpenBB as first-try in latest()/history(). Keep yf/FRED fallback. |
| `instruments.py` | Add `PriceSource.OPENBB` enum. Existing instruments optionally switch. |
| `research/technical.py` | Replace manual TA with adapter calls |
| `research/risk.py` | Add correlation_matrix(), volatility() |
| `research/backtest.py` | Use adapter history() for richer OHLCV |
| `research/web.py` | Add adapter news() alongside RSS |
| `triggers/calendar.py` | Optionally source from adapter economic_calendar() |
| `reporting/dashboard.py` | Unchanged — static HTML remains as fallback |

## Dashboard: OpenBB Workspace App (6 Tabs)

Run via: `uvicorn castelino.dashboard.main:app --reload --port 7779`
Connect in Workspace: Settings → Data Connectors → Add: http://localhost:7779

### Tab 1: Portfolio

- NAV / Cash / Gross / Net Exposure (metric widgets)
- Unrealized P&L / Realized P&L (metric widgets)
- Open Positions (table with live marks)
- Recent Fills (table)
- Equity Curve (Plotly line chart)
- Drawdown (Plotly area chart)

### Tab 2: Macro & Signals

- Live Macro Indicators — CPI, GDP, PMI, NFP (table)
- Yield Curve — 2Y/5Y/10Y/30Y (chart)
- Recent Triggers (table from journal)
- Active Hypotheses (table from journal)
- News Feed (newsfeed widget via OpenBB)
- Economic Calendar (table via OpenBB)

### Tab 3: Research & Technicals

- Instrument Screener (table)
- Technical Dashboard — RSI, MACD, BBands (chart)
- Correlation Heatmap (chart)
- Sector Performance (table)
- Analyst Estimates (table)
- Synced via "Group 1" on symbol parameter

### Tab 4: Risk & Attribution

- Exposure by Asset Class (pie/bar chart)
- Exposure by Instrument (bar chart)
- Attribution by Hypothesis (table)
- Principle Warnings (table)
- VIX / Volatility (metric)

### Tab 5: Agent Decisions

- Bull vs Bear Verdicts (table)
- Guard Decisions (table)
- Agent Reasoning Log (markdown)
- Pipeline Run History (table)

### Tab 6: Approval Queue

- Pending Approvals count (metric)
- Hypothesis Queue (table — regime, conviction, thesis, kill criteria)
- Debate Verdict Queue (table — bull/bear summaries, action, size)
- Decision History (table — past approvals/rejections)

## Human-in-the-Loop: Approval Gates

### Two mandatory gates:

1. **Post-Hypothesis** — after Hypothesis Agent forms thesis, pipeline stalls. Human approves, edits, or rejects.
2. **Post-Debate** — after Debate Agent verdict, pipeline stalls again. Human approves, overrides, or rejects.

### Behavior:

- Pipeline stalls indefinitely until explicit CLI action (no timeout, no auto-proceed)
- Pending approvals stored in `state/approval_queue.json` (survives restarts)
- Dashboard Tab 6 renders the queue in real-time
- Guard hard_veto remains automatic (no human override needed for safety rules)

### CLI Commands:

```bash
castelino queue                           # list pending items
castelino approve H-<id>                  # approve hypothesis
castelino edit H-<id> --thesis "..."      # edit and approve
castelino reject H-<id> --reason "..."    # reject hypothesis
castelino approve V-<id>                  # approve verdict
castelino reject V-<id> --reason "..."    # reject verdict
```

### Pipeline Flow with Gates:

```
Trigger → Current Event → Hypothesis Agent
                              │
                         [GATE 1: stall]
                              │
                    approve/edit/reject via CLI
                              │
                    Bull/Bear → Debate Agent
                              │
                         [GATE 2: stall]
                              │
                    approve/reject via CLI
                              │
                    Guard → Portfolio → Broker → Execute
```

## Error Handling

- OpenBB adapter failures → fallback to yfinance/FRED, log warning
- Dashboard endpoint failures → return empty arrays (widgets show "no data")
- SDK initialization failure → pipeline runs on legacy sources, dashboard shows portfolio-only data
- Approval queue corruption → pipeline refuses to proceed, logs error

## Caching

- Disk cache: parquet files in `cache/prices/` (same pattern as existing)
- In-memory: LRU with 15-minute buckets (same as existing yfinance)
- Dashboard endpoints: 30s TTL for market data, 5s TTL for portfolio state

## Configuration

```yaml
# config.yaml (new section)
openbb:
  preferred_provider: yfinance
  fallback_enabled: true
  cache_ttl_minutes: 15

approval:
  gates:
    - post_hypothesis
    - post_debate
  timeout: null  # stall indefinitely
```

```bash
# .env (gitignored)
OPENBB_PAT=your_pat_here
```

## Dependencies

```
openbb >= 4.0
```

## File Structure (net new)

```
src/castelino/
├── data/
│   └── openbb_adapter.py
├── dashboard/
│   ├── main.py
│   ├── widgets.json
│   ├── apps.json
│   └── endpoints/
│       ├── portfolio.py
│       ├── macro.py
│       ├── research.py
│       ├── risk.py
│       ├── agents.py
│       └── approvals.py
├── orchestrator/
│   └── approval.py          ← gate logic + queue management
```

## Running

```bash
# Pipeline (unchanged)
castelino run "NFP beats expectations"

# Dashboard
uvicorn castelino.dashboard.main:app --reload --port 7779

# OpenBB Workspace: Settings → Data Connectors → Add http://localhost:7779
```

## Key Invariants

- Pipeline never executes a trade without passing both HITL gates
- OpenBB failures never crash the pipeline — graceful degradation always
- Dashboard is additive — existing static HTML dashboard unchanged
- Zero breaking changes to current test suite
