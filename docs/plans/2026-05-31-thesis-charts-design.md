# Thesis Charts for Deep Research — Design

**Date:** 2026-05-31
**Status:** Approved (brainstorming complete; implementation plan next)
**Author:** Ashley Castelino (with Claude)

## 1. Summary & placement

Extend the Deep Research engine so a completed report can carry **supporting
charts** backed by **real OpenBB/FRED data**. The Synthesizer emits structured
**chart specifications** from a **closed menu**; a new deterministic
**ChartResolver** maps each spec to exactly one OpenBB adapter call and attaches
the resolved data to the report. The dashboard renders the charts with
**recharts**; the CLI lists them.

- **Home:** `src/castelino/agents/research/deep/` (extends the existing engine).
- **Consumer:** the analyst, on the existing `/deep-research` dashboard page.
- **Reuses:** `OpenBBAdapter` (`data/openbb_adapter.py`), `recharts` (already a
  frontend dep; `EquityCurveChart.tsx` precedent), the spec→result split the
  engine already uses (`SubQuestion`→`SubFinding`), and the injectable-fake
  test pattern (`FakeSonarClient` → new `FakeOpenBBAdapter`).

### Decisions locked during brainstorming
1. **Data source:** OpenBB real data — numbers come from OpenBB/FRED, never the LLM.
2. **Selection:** Synthesizer emits `chart_specs[]` from a fixed 4-type menu (no extra agent).
3. **Rendering:** frontend recharts (backend returns spec + raw data arrays as JSON).
4. **Menu (v1):** price history, yield curve, economic indicator, sector/comparison.
5. **Failure mode:** a chart whose data can't be fetched is **dropped** (logged); the report never fails because of a chart.

## 2. Architecture & flow

The pipeline is unchanged through synthesis. The Synthesizer additionally emits
`chart_specs[]`; a new deterministic `ChartResolver` step runs between synthesis
and report completion.

```
... SubAgents → Synthesizer
                   ├─ exec_summary, findings, sources   (as today)
                   └─ chart_specs[]   ← NEW: structured requests from a closed menu
                        │
                   ChartResolver (NEW, deterministic — no LLM)
                        │  spec → ONE OpenBB adapter call → data arrays
                        │  on any failure: drop that chart (logged), continue
                        ▼
              DeepResearchReport.charts[]   ← resolved chart + data, attached to report
                        │
        ┌───────────────┴───────────────┐
   Dashboard (recharts)            CLI (lists chart titles + data refs)
```

Properties:
- **LLM picks only from a closed menu** (4 types) and supplies parameters — it
  cannot invent chart types or fabricate data points.
- **ChartResolver is pure plumbing** — spec → adapter method → data. No LLM,
  fully unit-testable with a fake adapter.
- **A chart is never load-bearing** — any fetch failure drops just that chart;
  the report always completes.

## 3. Data model (Pydantic, `models.py`)

```python
class ChartType(StrEnum):
    PRICE_HISTORY  = "price_history"   # one ticker over time
    YIELD_CURVE    = "yield_curve"     # UST curve snapshot
    ECON_INDICATOR = "econ_indicator"  # a FRED series over time
    COMPARISON     = "comparison"      # normalized multi-ticker, or sector perf

class ChartSpec(BaseModel):          # the REQUEST (LLM-emitted, no data)
    type: ChartType
    title: str
    rationale: str = ""              # WHY it supports the thesis (shown as caption)
    symbols: list[str] = []          # tickers for price/comparison
    series_id: str = ""              # FRED id for econ_indicator
    lookback_days: int = 365

class ChartPoint(BaseModel):
    x: str                           # ISO date or category label
    y: float

class ChartSeries(BaseModel):
    name: str                        # legend label
    points: list[ChartPoint]

class ResolvedChart(BaseModel):      # the RESULT (data grafted on by resolver)
    type: ChartType
    title: str
    rationale: str
    series: list[ChartSeries]        # 1+ series; multi for comparison
    y_label: str = ""
    source: str = "OpenBB"

# DeepResearchReport gains:
    charts: list[ResolvedChart] = Field(default_factory=list)
```

The synthesizer's own output model gains `chart_specs: list[ChartSpec]`. Spec
and resolved are deliberately separate — the LLM's request never carries data;
data is grafted on only by the deterministic resolver. The generic
`series[]` of `{name, points[]}` covers all four chart types with one uniform
shape, so the frontend has one resilient renderer that only switches *style* on
`type`.

## 4. ChartResolver & OpenBB mapping

New file `src/castelino/agents/research/deep/chart_resolver.py`. No LLM;
injectable adapter for deterministic tests.

```python
class ChartResolver:
    def __init__(self, *, adapter=None):
        self._adapter = adapter or get_adapter()

    def resolve_all(self, specs: list[ChartSpec]) -> list[ResolvedChart]:
        out = []
        for spec in specs[: cfg.deep_research.max_charts]:    # hard cap
            try:
                chart = self._resolve_one(spec)
                if chart and chart.series and any(s.points for s in chart.series):
                    out.append(chart)            # keep only charts with real data
            except Exception as e:
                log.warning("chart dropped: %s (%s)", spec.title, e)   # never raise
        return out
```

Closed-menu dispatch — each type → exactly one adapter method:

| ChartType | OpenBB adapter call | Series shape |
|---|---|---|
| `PRICE_HISTORY` | `history(symbol, lookback_days)` → close col | 1 series, x=date |
| `COMPARISON` | `history()` per symbol, **normalized to 100** at t₀ (or `sector_performance()`) | N series, x=date |
| `YIELD_CURVE` | `yield_curve()` | 1 series, x=maturity (3M…30Y) |
| `ECON_INDICATOR` | `economic_indicators([series_id])` | 1 series, x=date |

Guardrails in the resolver:
- **Symbol sanitation** — uppercase, strip, regex `^[A-Z.\-]{1,6}$`; reject
  before it reaches OpenBB (defends against the LLM emitting prose as a ticker).
- **Comparison normalization** — rebased to 100 at t₀ so different price scales
  are visually comparable.
- **Empty frame = failure** → chart dropped.
- **`max_charts` cap** (config, default 4) bounds OpenBB calls per report.

Orchestrator wiring — one block in `finish()`, after synthesis:

```python
report = syn.synthesize(...)
report = report.model_copy(update={
    "charts": ChartResolver().resolve_all(report.chart_specs),
})
```

The reflection loop is untouched — charts resolve once, on the final report.

## 5. Synthesizer prompt change

`SYNTH_SYSTEM` gains a charts instruction; the schema (`chart_specs: list[ChartSpec]`)
constrains output to the enum + defined fields:

> "Propose 0–4 charts that would visually support your answer, choosing only
> from the available chart types. For each, give a title and a one-line
> rationale tying it to the thesis. Only request a chart when real
> market/economic data would strengthen the argument — prefer none over a weak
> chart. Use real tickers (e.g. AAPL) and FRED series IDs (e.g. CPIAUCSL,
> FEDFUNDS, UNRATE) you are confident exist."

"0–4 / prefer none" means a topic with no market data yields an empty list, not
a garbage chart. Prompt = first filter; resolver = safety net.

## 6. Surfaces

**Dashboard (`DeepResearchPage.tsx`):** a `<ThesisCharts>` section below the
exec-summary, above sources. A `ChartCard` switches render style on `type`:
- `price_history` / `econ_indicator` → `<LineChart>`
- `comparison` → multi-line normalized `<LineChart>` (or `<BarChart>` for sector)
- `yield_curve` → `<LineChart>` x=maturity

Each card shows **title, chart, rationale caption, and a "Source: OpenBB"
footer** — every graph visibly tied to the thesis and auditable. Reuses the
dark-theme recharts styling from `EquityCurveChart.tsx`. Renderer guards empty
series defensively.

**CLI (`castelino research`):** after the exec-summary, a compact list:
```
Supporting charts:
  • AAPL — 1Y price [price_history, 252 pts] — "Revenue is rate-sensitive…"
  • US CPI YoY [econ_indicator, 60 pts] — "Inflation backdrop for…"
```
No ASCII plotting (YAGNI). The dashboard is the visual surface.

## 7. Error handling

Three layers, all decided:
1. **Prompt** — "prefer none over a weak chart."
2. **Resolver** — drops any chart that errors or returns empty (logged, never
   raises); `max_charts` cap; symbol sanitation.
3. **Frontend** — guards empty series.

Net: charts can only add value or be absent — they cannot break a report or
display fabricated data.

## 8. Testing (deterministic: `FakeLLMClient` + new `FakeOpenBBAdapter`)

- **Resolver units** — each of the 4 types maps to the right call & shape; bad
  ticker rejected; empty frame → dropped; `max_charts` respected; one spec
  raising doesn't kill the batch; comparison series rebased to 100 at t₀.
- **Synthesizer** — `chart_specs` parse into the schema.
- **Orchestrator** — `finish()` attaches resolved charts; all-charts-fail →
  report still `COMPLETE` with `charts=[]`.
- **Endpoint** — `report.charts` serializes in `GET /research/{id}` JSON.

## 9. Config (new knobs in `deep_research:`)

| Knob | Default | Meaning |
|---|---|---|
| `max_charts` | 4 | hard cap on charts per report (bounds OpenBB calls) |
| `chart_lookback_days_default` | 365 | default window when the spec omits one |

## 10. Out of scope (deferred)

- LLM-extracted data series (chart numbers the model mentions) — OpenBB-only for v1.
- Candlestick/OHLC, drawdown, correlation-heatmap chart types — line/bar menu only.
- Chart export (PNG/CSV download) from the dashboard.
- Auto-refresh of chart data after the report is generated (snapshot at synthesis time).
- Attaching charts to an `ApprovalItem` / feeding them to the trading pipeline.
