# Thesis Charts for Deep Research — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or superpowers:subagent-driven-development) to implement this plan task-by-task.

**Goal:** Let a completed Deep Research report carry supporting charts backed by real OpenBB/FRED data, chosen by the Synthesizer from a closed 4-type menu, rendered with recharts on the dashboard and listed in the CLI.

**Architecture:** The Synthesizer additionally emits structured `chart_specs[]` (a closed enum menu, no data). A new deterministic `ChartResolver` (no LLM) maps each spec to exactly one OpenBB adapter call, attaches real data arrays, and drops any chart whose data can't be fetched. The orchestrator's `finish()` runs the resolver once on the final report. Dashboard renders `report.charts[]` with recharts; CLI lists them.

**Tech Stack:** Python 3.11, Pydantic v2, OpenBB adapter (`data/openbb_adapter.py`), `FakeLLMClient` test infra, FastAPI, React + recharts (already a dep), TanStack Query. Run everything with `uv run`.

**Design doc:** `docs/plans/2026-05-31-thesis-charts-design.md`

---

## Critical context from `learnings.md` (READ BEFORE STARTING)

- **Reasoning models eat the output budget.** All deep-research LLM calls already pass `max_tokens=cfg.deep_research.max_output_tokens` (16000). Adding `chart_specs` to the synthesizer's output schema makes the response bigger — the generous cap already covers it; do NOT lower it.
- **`chat.completions.parse` uses `max_completion_tokens`** (handled in `OpenAIClient.parse`). You don't touch this; just keep using the agent infra.
- **Injectable fakes for determinism.** Tests use `FakeLLMClient` (register a handler per output schema name) and must use a **`FakeOpenBBAdapter`** (new, this plan) — never hit live OpenBB in tests.
- **Frontend `npm run build` is pre-existingly broken** (missing vitest/testing-library devDeps). Verify the page compiles with a scoped check, NOT a full build: `cd frontend && npx tsc --noEmit -p tsconfig.json 2>&1 | grep DeepResearchPage` (expect no errors on our file).
- **OpenBB adapter contracts (verified):**
  - `history(symbol, lookback_days=252)` → `pd.DataFrame` indexed by `date`, columns include `close`.
  - `economic_indicators(series_ids: list[str])` → `pd.DataFrame` indexed by `date`, one column per series id.
  - `yield_curve()` → `pd.DataFrame` with ONE row, columns are tenor labels `1M,3M,6M,1Y,2Y,5Y,10Y,30Y`.
  - `sector_performance()` → `list[dict]`.
  - `get_adapter()` returns a process singleton; all methods raise `OpenBBError` on failure.

## Wave plan (for subagent-driven execution)

- **Wave 1 (parallel):** Task 1 (models), Task 2 (config). Different files, no deps.
- **Wave 2:** Task 3 (ChartResolver) — needs Task 1 + 2.
- **Wave 3:** Task 4 (synthesizer emits specs) — needs Task 1.
- **Wave 4:** Task 5 (orchestrator wiring) — needs Tasks 3 + 4.
- **Wave 5 (parallel):** Task 6 (endpoint serialization test), Task 7 (CLI list), Task 8 (frontend) — independent surfaces.
- **Wave 6:** Task 9 (wrap-up: full suite + design summary).

---

### Task 1: Chart data models

**Files:**
- Modify: `src/castelino/agents/research/deep/models.py`
- Test: `tests/test_deep_research_chart_models.py` (create)

**Step 1: Write the failing test**

```python
# tests/test_deep_research_chart_models.py
from castelino.agents.research.deep.models import (
    ChartType, ChartSpec, ChartPoint, ChartSeries, ResolvedChart,
    DeepResearchReport,
)


def test_chart_spec_defaults():
    spec = ChartSpec(type=ChartType.PRICE_HISTORY, title="AAPL 1Y")
    assert spec.type == "price_history"
    assert spec.symbols == []
    assert spec.series_id == ""
    assert spec.lookback_days == 365
    assert spec.rationale == ""


def test_resolved_chart_roundtrip():
    chart = ResolvedChart(
        type=ChartType.PRICE_HISTORY,
        title="AAPL — 1Y price",
        rationale="rate sensitive",
        series=[ChartSeries(name="AAPL", points=[ChartPoint(x="2026-01-01", y=190.0)])],
        y_label="USD",
    )
    assert chart.source == "OpenBB"
    assert chart.series[0].points[0].y == 190.0
    # serializes to JSON cleanly (used by the endpoint)
    dumped = chart.model_dump(mode="json")
    assert dumped["series"][0]["points"][0]["x"] == "2026-01-01"


def test_report_has_charts_field_default_empty():
    rep = DeepResearchReport(exec_summary="hi")
    assert rep.charts == []
```

**Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_deep_research_chart_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'ChartType'`.

**Step 3: Implement**

In `models.py`, the file already imports `StrEnum` from `enum` and `BaseModel, Field` from pydantic. Add after the `SourceRef` class:

```python
class ChartType(StrEnum):
    PRICE_HISTORY = "price_history"
    YIELD_CURVE = "yield_curve"
    ECON_INDICATOR = "econ_indicator"
    COMPARISON = "comparison"


class ChartSpec(BaseModel):
    """A chart the Synthesizer requests (no data — just the request)."""
    type: ChartType
    title: str
    rationale: str = ""
    symbols: list[str] = Field(default_factory=list)
    series_id: str = ""
    lookback_days: int = 365


class ChartPoint(BaseModel):
    x: str
    y: float


class ChartSeries(BaseModel):
    name: str
    points: list[ChartPoint] = Field(default_factory=list)


class ResolvedChart(BaseModel):
    """A chart with real data grafted on by the ChartResolver."""
    type: ChartType
    title: str
    rationale: str = ""
    series: list[ChartSeries] = Field(default_factory=list)
    y_label: str = ""
    source: str = "OpenBB"
```

Then add the `charts` field to `DeepResearchReport` (alongside `findings`, `sources`, etc.):

```python
    charts: list[ResolvedChart] = Field(default_factory=list)
```

**Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_deep_research_chart_models.py -v`
Expected: PASS (3 tests).

**Step 5: Commit**

```bash
git add src/castelino/agents/research/deep/models.py tests/test_deep_research_chart_models.py
git commit -m "feat(deep-research): chart data models (spec + resolved)"
```

---

### Task 2: Config knobs

**Files:**
- Modify: `src/castelino/config.py` (the `DeepResearchCfg` class)
- Modify: `config.yaml` (the `deep_research:` block)
- Test: `tests/test_deep_research_chart_config.py` (create)

**Step 1: Write the failing test**

```python
# tests/test_deep_research_chart_config.py
from castelino.config import get_settings


def test_chart_config_defaults():
    dr = get_settings().deep_research
    assert dr.max_charts == 4
    assert dr.chart_lookback_days_default == 365
```

**Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_deep_research_chart_config.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'max_charts'`.

**Step 3: Implement**

In `config.py`, `DeepResearchCfg`, add after `max_output_tokens`:

```python
    # Charts: hard cap on charts per report (bounds OpenBB calls) + default window.
    max_charts: int = 4
    chart_lookback_days_default: int = 365
```

In `config.yaml`, under `deep_research:`, add:

```yaml
  # Thesis charts: cap per report (bounds OpenBB calls) + default lookback window.
  max_charts: 4
  chart_lookback_days_default: 365
```

**Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_deep_research_chart_config.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/castelino/config.py config.yaml tests/test_deep_research_chart_config.py
git commit -m "feat(deep-research): chart config knobs (max_charts, default lookback)"
```

---

### Task 3: ChartResolver

**Files:**
- Create: `src/castelino/agents/research/deep/chart_resolver.py`
- Test: `tests/test_deep_research_chart_resolver.py` (create)

This is the core. No LLM. Injectable adapter. Maps each `ChartType` to one
adapter call, sanitizes symbols, normalizes comparison series, drops on failure.

**Step 1: Write the failing test** (use a hand-rolled fake adapter, no network)

```python
# tests/test_deep_research_chart_resolver.py
import pandas as pd

from castelino.agents.research.deep.models import ChartSpec, ChartType
from castelino.agents.research.deep.chart_resolver import ChartResolver


class FakeOpenBBAdapter:
    """Minimal stand-in for OpenBBAdapter — only the methods the resolver calls."""
    def __init__(self, *, raise_on=None):
        self.raise_on = raise_on or set()

    def history(self, symbol, lookback_days=252):
        if "history" in self.raise_on or symbol == "BAD":
            raise RuntimeError("no data")
        idx = pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"])
        base = 100.0 if symbol == "AAPL" else 400.0
        return pd.DataFrame({"close": [base, base * 1.1, base * 1.2]}, index=idx)

    def economic_indicators(self, series_ids):
        if "econ" in self.raise_on:
            raise RuntimeError("no series")
        idx = pd.to_datetime(["2026-01-01", "2026-02-01"])
        return pd.DataFrame({series_ids[0]: [3.1, 3.4]}, index=idx)

    def yield_curve(self):
        if "yc" in self.raise_on:
            raise RuntimeError("no curve")
        return pd.DataFrame([{"3M": 4.5, "2Y": 4.2, "10Y": 4.4, "30Y": 4.6}])

    def sector_performance(self):
        return [{"sector": "Technology", "change_percent": 1.2},
                {"sector": "Energy", "change_percent": -0.5}]


def _resolver(**kw):
    return ChartResolver(adapter=FakeOpenBBAdapter(**kw))


def test_price_history_maps_to_one_series_of_dates():
    out = _resolver().resolve_all([
        ChartSpec(type=ChartType.PRICE_HISTORY, title="AAPL 1Y", symbols=["AAPL"]),
    ])
    assert len(out) == 1
    chart = out[0]
    assert chart.type == "price_history"
    assert len(chart.series) == 1
    assert chart.series[0].name == "AAPL"
    assert [p.x for p in chart.series[0].points] == ["2026-01-01", "2026-01-02", "2026-01-03"]
    assert chart.series[0].points[0].y == 100.0


def test_comparison_normalizes_to_100_at_t0():
    out = _resolver().resolve_all([
        ChartSpec(type=ChartType.COMPARISON, title="AAPL vs MSFT",
                  symbols=["AAPL", "MSFT"]),
    ])
    chart = out[0]
    assert {s.name for s in chart.series} == {"AAPL", "MSFT"}
    # both rebased to 100 at t0 regardless of absolute price
    for s in chart.series:
        assert s.points[0].y == 100.0
        assert round(s.points[2].y, 1) == 120.0  # +20% in both fake series


def test_econ_indicator_maps_series_id():
    out = _resolver().resolve_all([
        ChartSpec(type=ChartType.ECON_INDICATOR, title="US CPI", series_id="CPIAUCSL"),
    ])
    chart = out[0]
    assert chart.series[0].name == "CPIAUCSL"
    assert [p.y for p in chart.series[0].points] == [3.1, 3.4]


def test_yield_curve_x_is_maturity():
    out = _resolver().resolve_all([
        ChartSpec(type=ChartType.YIELD_CURVE, title="UST curve"),
    ])
    chart = out[0]
    xs = [p.x for p in chart.series[0].points]
    assert xs == ["3M", "2Y", "10Y", "30Y"]  # preserves column order


def test_bad_ticker_is_rejected_and_chart_dropped():
    out = _resolver().resolve_all([
        ChartSpec(type=ChartType.PRICE_HISTORY, title="bad", symbols=["not a ticker!!"]),
    ])
    assert out == []  # sanitizer rejects, no data, dropped


def test_fetch_error_drops_only_that_chart():
    out = _resolver(raise_on={"history"}).resolve_all([
        ChartSpec(type=ChartType.PRICE_HISTORY, title="x", symbols=["AAPL"]),
        ChartSpec(type=ChartType.YIELD_CURVE, title="curve"),
    ])
    titles = [c.title for c in out]
    assert titles == ["curve"]  # price dropped, curve survived


def test_max_charts_cap_respected(monkeypatch):
    from castelino.config import get_settings
    get_settings().deep_research.max_charts = 1
    out = _resolver().resolve_all([
        ChartSpec(type=ChartType.YIELD_CURVE, title="a"),
        ChartSpec(type=ChartType.YIELD_CURVE, title="b"),
    ])
    assert len(out) == 1
    get_settings().deep_research.max_charts = 4  # restore
```

**Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_deep_research_chart_resolver.py -v`
Expected: FAIL — `ModuleNotFoundError: chart_resolver`.

**Step 3: Implement**

```python
# src/castelino/agents/research/deep/chart_resolver.py
from __future__ import annotations

import logging
import re

import pandas as pd

from castelino.agents.research.deep.models import (
    ChartPoint,
    ChartSeries,
    ChartSpec,
    ChartType,
    ResolvedChart,
)
from castelino.config import get_settings
from castelino.data.openbb_adapter import get_adapter

log = logging.getLogger(__name__)

_TICKER_RE = re.compile(r"^[A-Z.\-]{1,6}$")


def _clean_symbols(raw: list[str]) -> list[str]:
    out = []
    for s in raw or []:
        t = (s or "").strip().upper()
        if _TICKER_RE.match(t):
            out.append(t)
    return out


def _series_from_close(name: str, df: pd.DataFrame) -> ChartSeries:
    pts = [
        ChartPoint(x=idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx),
                   y=float(val))
        for idx, val in df["close"].dropna().items()
    ]
    return ChartSeries(name=name, points=pts)


class ChartResolver:
    """Deterministic spec -> OpenBB data. No LLM. Drops any chart that fails."""

    def __init__(self, *, adapter=None):
        self._adapter = adapter or get_adapter()

    def resolve_all(self, specs: list[ChartSpec]) -> list[ResolvedChart]:
        cfg = get_settings().deep_research
        out: list[ResolvedChart] = []
        for spec in (specs or [])[: cfg.max_charts]:
            try:
                chart = self._resolve_one(spec)
            except Exception as e:  # never raise — a chart is never load-bearing
                log.warning("chart dropped: %s (%s)", spec.title, e)
                continue
            if chart and chart.series and any(s.points for s in chart.series):
                out.append(chart)
            else:
                log.info("chart dropped (no data): %s", spec.title)
        return out

    def _resolve_one(self, spec: ChartSpec) -> ResolvedChart | None:
        cfg = get_settings().deep_research
        lookback = spec.lookback_days or cfg.chart_lookback_days_default

        if spec.type == ChartType.PRICE_HISTORY:
            syms = _clean_symbols(spec.symbols)
            if not syms:
                return None
            df = self._adapter.history(syms[0], lookback_days=lookback)
            return ResolvedChart(
                type=spec.type, title=spec.title, rationale=spec.rationale,
                series=[_series_from_close(syms[0], df)], y_label="Price",
            )

        if spec.type == ChartType.COMPARISON:
            syms = _clean_symbols(spec.symbols)
            if not syms:
                return None
            series: list[ChartSeries] = []
            for sym in syms:
                df = self._adapter.history(sym, lookback_days=lookback)
                close = df["close"].dropna()
                if close.empty:
                    continue
                base = float(close.iloc[0])
                if base == 0:
                    continue
                pts = [
                    ChartPoint(
                        x=idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx),
                        y=round(float(val) / base * 100.0, 4),
                    )
                    for idx, val in close.items()
                ]
                series.append(ChartSeries(name=sym, points=pts))
            return ResolvedChart(
                type=spec.type, title=spec.title, rationale=spec.rationale,
                series=series, y_label="Indexed to 100",
            )

        if spec.type == ChartType.ECON_INDICATOR:
            sid = (spec.series_id or "").strip().upper()
            if not sid:
                return None
            df = self._adapter.economic_indicators([sid])
            col = df[sid] if sid in df.columns else df.iloc[:, 0]
            pts = [
                ChartPoint(
                    x=idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx),
                    y=float(val),
                )
                for idx, val in col.dropna().items()
            ]
            return ResolvedChart(
                type=spec.type, title=spec.title, rationale=spec.rationale,
                series=[ChartSeries(name=sid, points=pts)], y_label=sid,
            )

        if spec.type == ChartType.YIELD_CURVE:
            df = self._adapter.yield_curve()
            row = df.iloc[0]
            pts = [ChartPoint(x=str(label), y=float(val))
                   for label, val in row.items() if pd.notna(val)]
            return ResolvedChart(
                type=spec.type, title=spec.title, rationale=spec.rationale,
                series=[ChartSeries(name="UST yield", points=pts)], y_label="Yield %",
            )

        return None
```

**Note on COMPARISON via sector_performance:** v1 keeps COMPARISON = multi-ticker
normalized lines (above). Sector-performance bars are deferred unless the spec
has no `symbols` AND mentions sectors — out of scope to keep the resolver simple;
the synthesizer prompt steers COMPARISON toward tickers.

**Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_deep_research_chart_resolver.py -v`
Expected: PASS (7 tests).

**Step 5: Commit**

```bash
git add src/castelino/agents/research/deep/chart_resolver.py tests/test_deep_research_chart_resolver.py
git commit -m "feat(deep-research): ChartResolver maps specs to OpenBB data, drops on failure"
```

---

### Task 4: Synthesizer emits chart specs

**Files:**
- Modify: `src/castelino/agents/research/deep/synthesizer.py`
- Modify: `src/castelino/agents/research/deep/models.py` (synthesizer output carries `chart_specs`)
- Test: `tests/test_deep_research_chart_synth.py` (create)

The synthesizer currently parses straight into `DeepResearchReport`. Add
`chart_specs: list[ChartSpec]` to `DeepResearchReport` so the same parse call
returns the specs (then the orchestrator resolves them into `charts`). Keeping
specs and resolved charts on the same model is simplest; `chart_specs` is the
raw request, `charts` is the resolved result.

**Step 1: Write the failing test**

```python
# tests/test_deep_research_chart_synth.py
from castelino.agents.base import FakeLLMClient
from castelino.agents.research.deep.models import (
    ChartSpec, ChartType, DeepResearchReport, SubFinding,
)
from castelino.agents.research.deep.synthesizer import Synthesizer


def test_synthesizer_passes_through_chart_specs():
    fake = FakeLLMClient()
    fake.register("DeepResearchReport", lambda s, u: DeepResearchReport(
        exec_summary="Apple is rate sensitive.",
        confidence=0.8,
        chart_specs=[ChartSpec(type=ChartType.PRICE_HISTORY, title="AAPL 1Y",
                               symbols=["AAPL"], rationale="price trend")],
    ))
    syn = Synthesizer(llm=fake)
    report = syn.synthesize(
        reworded_query="How is Apple doing?",
        findings=[SubFinding(sub_question_id="q1", summary="up")],
    )
    assert len(report.chart_specs) == 1
    assert report.chart_specs[0].symbols == ["AAPL"]
```

**Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_deep_research_chart_synth.py -v`
Expected: FAIL — `DeepResearchReport` has no `chart_specs`.

**Step 3: Implement**

In `models.py`, add to `DeepResearchReport`:

```python
    chart_specs: list[ChartSpec] = Field(default_factory=list)
```

In `synthesizer.py`, extend `SYNTH_SYSTEM` with the charts instruction (append to the existing string):

```python
SYNTH_SYSTEM = """\
...existing text...
- chart_specs: propose 0-4 charts that would visually support your answer,
  choosing ONLY from these types: price_history (one ticker over time;
  set symbols=[TICKER]), comparison (2-4 tickers, set symbols), econ_indicator
  (set series_id to a FRED id like CPIAUCSL, FEDFUNDS, UNRATE, DGS10), or
  yield_curve (no params). Give each a short title and a one-line rationale
  tying it to the thesis. Only request a chart when real market/economic data
  would strengthen the argument — prefer none over a weak chart. Use real
  tickers and FRED series IDs you are confident exist.
"""
```

No change to the `parse()` call — `chart_specs` rides on the same
`DeepResearchReport` schema. The `model_copy(update=...)` at the end of
`synthesize()` must NOT drop it (it only sets `findings` and `sources`, so
`chart_specs` is preserved automatically).

**Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_deep_research_chart_synth.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/castelino/agents/research/deep/synthesizer.py src/castelino/agents/research/deep/models.py tests/test_deep_research_chart_synth.py
git commit -m "feat(deep-research): synthesizer emits chart_specs from a closed menu"
```

---

### Task 5: Orchestrator resolves charts in finish()

**Files:**
- Modify: `src/castelino/agents/research/deep/orchestrator.py`
- Test: `tests/test_deep_research_chart_orchestrator.py` (create)

**Step 1: Write the failing test**

```python
# tests/test_deep_research_chart_orchestrator.py
from castelino.agents.base import FakeLLMClient
from castelino.agents.research.deep.models import (
    ChartSpec, ChartType, DeepResearchReport, ReflectionResult, ResearchStatus,
)
from castelino.agents.research.deep.orchestrator import DeepResearchOrchestrator
from castelino.agents.research.deep.store import ResearchStore
from castelino.agents.research.deep.sonar_client import FakeSonarClient, SonarResult


def _fake_llm_with_chart():
    fake = FakeLLMClient()
    fake.register("ClarifierResult", lambda s, u: __import__(
        "castelino.agents.research.deep.models", fromlist=["ClarifierResult"]
    ).ClarifierResult(reworded_query="Q"))
    fake.register("DecompositionResult", lambda s, u: __import__(
        "castelino.agents.research.deep.models", fromlist=["DecompositionResult"]
    ).DecompositionResult(sub_questions=[]))
    fake.register("SubFinding", lambda s, u: __import__(
        "castelino.agents.research.deep.models", fromlist=["SubFinding"]
    ).SubFinding(sub_question_id="q1", summary="x"))
    fake.register("DeepResearchReport", lambda s, u: DeepResearchReport(
        exec_summary="answer",
        chart_specs=[ChartSpec(type=ChartType.YIELD_CURVE, title="curve")],
    ))
    fake.register("ReflectionResult", lambda s, u: ReflectionResult(is_sufficient=True))
    return fake


class _FakeAdapter:
    def yield_curve(self):
        import pandas as pd
        return pd.DataFrame([{"3M": 4.5, "10Y": 4.4}])


def test_finish_attaches_resolved_charts(tmp_path, monkeypatch):
    # Patch the resolver's adapter to the fake one.
    import castelino.agents.research.deep.chart_resolver as cr
    monkeypatch.setattr(cr, "get_adapter", lambda: _FakeAdapter())

    store = ResearchStore(root=tmp_path)
    orch = DeepResearchOrchestrator(
        llm=_fake_llm_with_chart(), sonar=FakeSonarClient(), store=store,
    )
    sess = orch.start("anything")
    sess = orch.run_first_round(sess.id, answers={})
    # force at least one round/finding so synth runs (decomposition empty → seed one)
    sess = orch.finish(sess.id)
    assert sess.status == ResearchStatus.COMPLETE
    assert len(sess.report.charts) == 1
    assert sess.report.charts[0].type == "yield_curve"
    assert sess.report.charts[0].series[0].points  # has real (fake) data


def test_finish_chart_failure_keeps_report_complete(tmp_path, monkeypatch):
    import castelino.agents.research.deep.chart_resolver as cr

    class _Boom:
        def yield_curve(self):
            raise RuntimeError("openbb down")

    monkeypatch.setattr(cr, "get_adapter", lambda: _Boom())
    store = ResearchStore(root=tmp_path)
    orch = DeepResearchOrchestrator(
        llm=_fake_llm_with_chart(), sonar=FakeSonarClient(), store=store,
    )
    sess = orch.start("anything")
    sess = orch.run_first_round(sess.id, answers={})
    sess = orch.finish(sess.id)
    assert sess.status == ResearchStatus.COMPLETE  # report NOT failed
    assert sess.report.charts == []  # chart dropped
```

> If `run_first_round` with an empty decomposition produces no findings and the
> synthesizer is skipped, adjust the fake `DecompositionResult` to return one
> `SubQuestion` and register a `FakeSonarClient` result so a finding exists. Keep
> the test focused on: charts attached on success; report stays COMPLETE on chart failure.

**Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_deep_research_chart_orchestrator.py -v`
Expected: FAIL — `report.charts` is empty (resolver not wired).

**Step 3: Implement**

In `orchestrator.py`, import the resolver at top:

```python
from castelino.agents.research.deep.chart_resolver import ChartResolver
```

In `finish()`, after the final `report = syn.synthesize(...)` / reflection loop,
just before `sess.report = report`, add:

```python
        # Resolve thesis charts from the synthesizer's specs (deterministic,
        # OpenBB-backed). Never fails the report — bad charts are dropped.
        try:
            resolved = ChartResolver().resolve_all(report.chart_specs)
        except Exception as e:  # defensive: resolver already swallows per-chart
            log.warning("chart resolution failed wholesale: %s", e)
            resolved = []
        report = report.model_copy(update={"charts": resolved})
```

Make sure this runs on the FINAL `report` (after the reflection while-loop), not
inside the loop — charts resolve once.

**Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_deep_research_chart_orchestrator.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/castelino/agents/research/deep/orchestrator.py tests/test_deep_research_chart_orchestrator.py
git commit -m "feat(deep-research): orchestrator resolves charts in finish(), never fails report"
```

---

### Task 6: Endpoint serialization (charts reach the API)

**Files:**
- Test: `tests/test_deep_research_chart_endpoint.py` (create)
- (No code change expected — `research_get` already does `sess.model_dump(mode="json")`. This task PROVES charts serialize, and only touches code if they don't.)

**Step 1: Write the failing test**

```python
# tests/test_deep_research_chart_endpoint.py
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from castelino.agents.research.deep.models import (
    ChartPoint, ChartSeries, ChartType, DeepResearchReport,
    ResearchSession, ResearchStatus, ResolvedChart,
)
from castelino.agents.research.deep.store import ResearchStore
import castelino.dashboard.endpoints.deep_research as dr
from castelino.dashboard.main import app


def test_report_charts_serialize_in_get(tmp_path):
    dr._store_root = tmp_path
    store = ResearchStore(root=tmp_path)
    now = datetime.now(UTC)
    sess = ResearchSession(
        id="abc123", original_query="q", status=ResearchStatus.COMPLETE,
        created_at=now, updated_at=now,
        report=DeepResearchReport(
            exec_summary="ok",
            charts=[ResolvedChart(
                type=ChartType.PRICE_HISTORY, title="AAPL",
                series=[ChartSeries(name="AAPL", points=[ChartPoint(x="2026-01-01", y=190.0)])],
            )],
        ),
    )
    store.save(sess)

    client = TestClient(app)
    r = client.get("/research/abc123")
    assert r.status_code == 200
    body = r.json()
    charts = body["report"]["charts"]
    assert len(charts) == 1
    assert charts[0]["type"] == "price_history"
    assert charts[0]["series"][0]["points"][0]["y"] == 190.0
    dr._store_root = None  # restore
```

**Step 2: Run**

Run: `uv run pytest tests/test_deep_research_chart_endpoint.py -v`
Expected: PASS immediately (the endpoint already dumps the whole session). If it
FAILS, the only fix permitted is ensuring `model_dump(mode="json")` is used —
do not add bespoke serialization.

**Step 5: Commit**

```bash
git add tests/test_deep_research_chart_endpoint.py
git commit -m "test(deep-research): charts serialize through GET /research/{id}"
```

---

### Task 7: CLI lists supporting charts

**Files:**
- Modify: `src/castelino/orchestrator/cli.py` (the `research` command, after it prints exec_summary)
- Test: `tests/test_deep_research_chart_cli.py` (create)

**Step 1: Write the failing test**

```python
# tests/test_deep_research_chart_cli.py
from typer.testing import CliRunner

from castelino.orchestrator.cli import app
from castelino.agents.research.deep.models import (
    ChartType, ChartSeries, ChartPoint, ResolvedChart, DeepResearchReport,
    ResearchSession, ResearchStatus,
)
from datetime import UTC, datetime
import castelino.orchestrator.cli as climod


def test_cli_prints_chart_list(monkeypatch):
    now = datetime.now(UTC)
    report = DeepResearchReport(
        exec_summary="Apple looks strong.",
        charts=[ResolvedChart(
            type=ChartType.PRICE_HISTORY, title="AAPL — 1Y price",
            rationale="momentum",
            series=[ChartSeries(name="AAPL",
                                points=[ChartPoint(x="2026-01-01", y=1.0),
                                        ChartPoint(x="2026-01-02", y=2.0)])],
        )],
    )
    sess = ResearchSession(id="x", original_query="apple",
                           status=ResearchStatus.COMPLETE, report=report,
                           created_at=now, updated_at=now)

    def fake_run_sync(self, query, answers=None):
        return sess
    monkeypatch.setattr(
        "castelino.agents.research.deep.orchestrator.DeepResearchOrchestrator.run_sync",
        fake_run_sync,
    )
    res = CliRunner().invoke(app, ["research", "apple", "--no-clarify"])
    assert res.exit_code == 0
    assert "Supporting charts" in res.stdout
    assert "AAPL — 1Y price" in res.stdout
    assert "price_history" in res.stdout
    assert "momentum" in res.stdout
```

**Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_deep_research_chart_cli.py -v`
Expected: FAIL — "Supporting charts" not in output.

**Step 3: Implement**

In `cli.py`, in the `research` command, after the block that prints the report's
`exec_summary` and sources, add (use the existing `print` from rich already
imported in that file):

```python
        charts = getattr(sess.report, "charts", []) or []
        if charts:
            print("\n[bold]Supporting charts:[/bold]")
            for c in charts:
                n_pts = sum(len(s.points) for s in c.series)
                line = f"  • {c.title} [{c.type}, {n_pts} pts]"
                if c.rationale:
                    line += f' — "{c.rationale}"'
                print(line)
```

**Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_deep_research_chart_cli.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/castelino/orchestrator/cli.py tests/test_deep_research_chart_cli.py
git commit -m "feat(deep-research): CLI lists supporting charts under the answer"
```

---

### Task 8: Frontend renders thesis charts (recharts)

**Files:**
- Create: `frontend/src/components/ThesisCharts.tsx`
- Modify: `frontend/src/pages/DeepResearchPage.tsx` (add the `Report` type fields + render `<ThesisCharts>`)
- Verify: scoped `tsc --noEmit` (NOT full build — pre-existing break)

**Step 1: Write `ThesisCharts.tsx`**

```tsx
// frontend/src/components/ThesisCharts.tsx
import {
  Bar, BarChart, CartesianGrid, Legend, Line, LineChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

type ChartPoint = { x: string; y: number };
type ChartSeries = { name: string; points: ChartPoint[] };
export type ResolvedChart = {
  type: "price_history" | "yield_curve" | "econ_indicator" | "comparison";
  title: string;
  rationale?: string;
  series: ChartSeries[];
  y_label?: string;
  source?: string;
};

const COLORS = ["#2563eb", "#16a34a", "#dc2626", "#9333ea", "#ea580c"];

// Merge N series into recharts row format: [{ x, <seriesName>: y, ... }]
function toRows(series: ChartSeries[]): Record<string, string | number>[] {
  const byX = new Map<string, Record<string, string | number>>();
  series.forEach((s) => {
    s.points.forEach((p) => {
      const row = byX.get(p.x) ?? { x: p.x };
      row[s.name] = p.y;
      byX.set(p.x, row);
    });
  });
  return Array.from(byX.values());
}

function ChartCard({ chart }: { chart: ResolvedChart }) {
  const rows = toRows(chart.series);
  if (rows.length === 0) return null;

  const isBar = false; // v1: all four types render as lines (yield curve included)

  return (
    <div className="border border-slate-300 rounded p-3 bg-white">
      <h4 className="font-medium text-black">{chart.title}</h4>
      {chart.rationale && (
        <p className="text-xs text-slate-600 mb-2">{chart.rationale}</p>
      )}
      <ResponsiveContainer width="100%" height={240}>
        {isBar ? (
          <BarChart data={rows}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="x" fontSize={11} stroke="#6b7280" />
            <YAxis fontSize={11} stroke="#6b7280" />
            <Tooltip />
            {chart.series.map((s, i) => (
              <Bar key={s.name} dataKey={s.name} fill={COLORS[i % COLORS.length]} />
            ))}
          </BarChart>
        ) : (
          <LineChart data={rows}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="x" fontSize={11} stroke="#6b7280" minTickGap={32} />
            <YAxis fontSize={11} stroke="#6b7280" domain={["auto", "auto"]} />
            <Tooltip
              contentStyle={{
                background: "#ffffff", border: "1px solid #e5e7eb",
                borderRadius: 8, fontSize: 12,
              }}
            />
            {chart.series.length > 1 && <Legend />}
            {chart.series.map((s, i) => (
              <Line key={s.name} type="monotone" dataKey={s.name}
                    stroke={COLORS[i % COLORS.length]} strokeWidth={2} dot={false} />
            ))}
          </LineChart>
        )}
      </ResponsiveContainer>
      <p className="text-[10px] text-slate-400 mt-1">Source: {chart.source ?? "OpenBB"}</p>
    </div>
  );
}

export function ThesisCharts({ charts }: { charts?: ResolvedChart[] }) {
  if (!charts || charts.length === 0) return null;
  return (
    <div className="space-y-3">
      <h3 className="font-medium">Supporting charts</h3>
      {charts.map((c, i) => (
        <ChartCard key={`${c.title}-${i}`} chart={c} />
      ))}
    </div>
  );
}
```

**Step 2: Wire into `DeepResearchPage.tsx`**

- Add `charts?: ResolvedChart[]` to the `Report` type (import the type from the component).
- Import: `import { ThesisCharts, type ResolvedChart } from "@/components/ThesisCharts";`
- In the `report &&` block, between the exec_summary `<p>` and the Caveats block, add:

```tsx
          <ThesisCharts charts={report.charts} />
```

- Update the `Report` type:

```tsx
type Report = {
  exec_summary: string;
  confidence: number;
  caveats: string[];
  sources: Source[];
  gaps_remaining: string[];
  charts?: ResolvedChart[];   // NEW
};
```

**Step 3: Verify it compiles (scoped — NOT full build)**

Run:
```bash
cd frontend && npx tsc --noEmit -p tsconfig.json 2>&1 | grep -E "ThesisCharts|DeepResearchPage" || echo "OUR FILES CLEAN"
```
Expected: `OUR FILES CLEAN` (the pre-existing __tests__ errors are unrelated; our two files must show no errors).

**Step 4: Manual smoke (optional, with servers up)**

Backend + frontend already run on :7779 / :3000. After Vite hot-reload, run a
research query on http://localhost:3000/deep-research that mentions a ticker
(e.g. "research apple") and confirm a price chart renders under the answer.

**Step 5: Commit**

```bash
git add frontend/src/components/ThesisCharts.tsx frontend/src/pages/DeepResearchPage.tsx
git commit -m "feat(deep-research): render thesis charts on the dashboard (recharts)"
```

---

### Task 9: Wrap-up — full suite, lint, docs

**Files:**
- Modify: `CLAUDE.md` (append to the Deep Research Agent entry under `## Completed Work`)
- Modify: `short_term_memory.md` (new task entry)

**Step 1: Run the full deep-research suite**

Run: `uv run pytest tests/ -k "deep_research" -q`
Expected: all green (existing 24 + new chart tests). Record the count.

**Step 2: Lint the changed Python files**

Run: `uv run ruff check src/castelino/agents/research/deep/ src/castelino/config.py src/castelino/orchestrator/cli.py`
Expected: clean (fix any new issues; pre-existing `UP037` on `config.py` `resolve()` is out of scope).

**Step 3: Live end-to-end smoke (needs .env keys)**

Run a real query through the orchestrator (or the dashboard) that mentions a
ticker and a macro angle, e.g. "How is Apple positioned given the rate
environment?" — confirm `status=complete` and `report.charts` is non-empty with
real data points. (This is the acceptance test for the whole feature.)

**Step 4: Update docs**

- In `CLAUDE.md`, under the existing `### 2026-05-30 — Deep Research Agent`
  entry (or a new dated sub-bullet), note: thesis charts added — synthesizer
  emits `chart_specs` from a closed 4-type menu, `ChartResolver` maps to OpenBB,
  charts drop on failure, rendered with recharts.
- Append a `short_term_memory.md` task entry summarizing what was built.

**Step 5: Commit**

```bash
git add CLAUDE.md short_term_memory.md
git commit -m "docs(deep-research): record thesis-charts completion"
```

---

## Definition of done

- [ ] `uv run pytest tests/ -k deep_research` fully green (24 existing + ~15 new).
- [ ] ruff clean on changed Python files.
- [ ] `ThesisCharts.tsx` + `DeepResearchPage.tsx` pass scoped `tsc --noEmit`.
- [ ] Live query mentioning a ticker produces a report with ≥1 real OpenBB-backed chart.
- [ ] A forced chart failure (bad ticker / OpenBB down) leaves the report `COMPLETE` with that chart dropped.
- [ ] No change to the trading pipeline; charts are analyst-only, snapshot at synthesis time.
```
