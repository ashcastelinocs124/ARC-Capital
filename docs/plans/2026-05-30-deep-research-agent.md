# Deep Research Agent Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a human-driven, multi-agent deep-research engine that takes an analyst's raw query, rewords it, asks clarifying questions, decomposes the enriched query into parallel sub-questions researched via Perplexity Sonar, and synthesizes a cited report with a bounded reflection loop — exposed via CLI and the dashboard.

**Architecture:** A plain `asyncio` orchestrator modeled as a state machine (CREATED → AWAITING_ANSWERS → RESEARCHING → SYNTHESIZING → COMPLETE/FAILED), reusing the existing `StructuredAgent`/`OpenAIClient`/`FakeLLMClient` infra (`agents/base.py`), the persona panel's `asyncio.gather` fan-out (`agents/personas/panel.py`), tiered model config, and the Sonar call pattern (`agents/personas/sonar_fetcher.py`). Reports persist to `data/research/<id>.json`. No LangGraph. Not auto-fed into the trading pipeline.

**Tech Stack:** Python 3.11, Pydantic v2, OpenAI SDK (`chat.completions.parse` for structured output; same SDK pointed at `https://api.perplexity.ai` for Sonar), `asyncio`, Typer (CLI), FastAPI (dashboard), pytest. Frontend: React + Vite + TanStack Query.

---

## Critical context from `learnings.md` (read before starting)

- **Run everything with the 3.11 venv:** `uv run …`. The repo's venv MUST be Python 3.11 (`uv sync --python 3.11`) — onnxruntime (via chromadb) has no cp312 macOS-arm64 wheel. If `uv run` fails on import, rebuild: `rm -rf .venv && uv sync --python 3.11`.
- **Sonar is called via the OpenAI SDK**, not httpx: `OpenAI(api_key=cfg.perplexity_api_key, base_url="https://api.perplexity.ai")` then `client.chat.completions.create(model=cfg.sonar.model, …)`. Perplexity returns the answer in `resp.choices[0].message.content` AND a top-level `resp.citations` list of source URLs. Key is optional — when `cfg.perplexity_api_key` is None, return empty/flagged results (existing "returns [] on failure" convention).
- **Atomic JSON writes:** prior corrupt-cache bugs came from partial writes. Always write session/report JSON to a temp file then `os.replace`.
- **Model tiers** resolve via `cfg.models.reasoning` / `cfg.models.fast`. Note: live config sets these to `gpt-5.5`/`gpt-5.4-mini` (not real OpenAI IDs) — out of scope to fix here, just inherit them.
- **Tests** use `FakeLLMClient` (register a handler per schema name) + a new `FakeSonarClient`. Live tests get `@pytest.mark.live` and are skipped in CI.

## Conventions

- Package home: `src/castelino/agents/research/deep/`
- Tests: flat in `tests/`, named `test_deep_research_*.py` (matches `test_personas_*.py` style).
- Run a single test: `uv run pytest tests/test_deep_research_models.py::test_name -v`
- Run the whole suite for this feature: `uv run pytest tests/ -k deep_research -v`
- Commit after every green step. Branch first (HARD RULE: never `git push` directly — use `/gitpush`).

---

## Task 0: Create a feature branch

**Step 1: Branch**

```bash
cd /Users/ash/ckmcapital
git checkout -b feat/deep-research-agent
```

**Step 2: Verify clean baseline**

Run: `uv run pytest tests/ -q 2>&1 | tail -5`
Expected: existing suite passes (or note pre-existing failures unrelated to this work).

**Step 3: Commit the already-written design doc**

```bash
git add docs/plans/2026-05-30-deep-research-agent-design.md docs/plans/2026-05-30-deep-research-agent.md
git commit -m "docs(deep-research): design + implementation plan"
```

---

## Task 1: Config — `DeepResearchCfg`

**Files:**
- Modify: `src/castelino/config.py` (add class near `PersonaCfg` ~line 166; add field to `Settings` ~line 294)
- Modify: `config.yaml` (add `deep_research:` block after the `personas:` block ~line 202)
- Test: `tests/test_deep_research_config.py`

**Step 1: Write the failing test**

```python
# tests/test_deep_research_config.py
from castelino.config import get_settings


def test_deep_research_config_defaults():
    cfg = get_settings()
    dr = cfg.deep_research
    assert dr.max_sub_questions == 6
    assert dr.max_rounds == 2
    assert dr.max_sonar_calls == 15
    assert dr.concurrency == 5
    assert dr.clarify_max_questions == 3
    assert dr.reasoning_tier == "reasoning"
    assert dr.fast_tier == "fast"
    assert dr.reports_dir == "data/research"
```

**Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_deep_research_config.py -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'deep_research'`

**Step 3: Implement**

Add to `src/castelino/config.py` (after `PersonaCfg`, before the figure_deviation section):

```python
class DeepResearchCfg(BaseModel):
    enabled: bool = True
    max_sub_questions: int = 6        # hard cap on decomposition fan-out
    max_rounds: int = 2              # reflection rounds, incl. first
    max_sonar_calls: int = 15        # global Sonar budget per report
    concurrency: int = 5             # asyncio semaphore over sub-agents
    clarify_max_questions: int = 3   # cap on clarifying questions
    reasoning_tier: str = "reasoning"  # tier for clarifier/lead/synthesizer
    fast_tier: str = "fast"            # tier for parallel sub-agents
    reports_dir: str = "data/research"
```

Add to the `Settings` class field list (near `personas:`):

```python
    deep_research: DeepResearchCfg = DeepResearchCfg()
```

Add to `config.yaml` after the `personas:` block:

```yaml
deep_research:
  enabled: true
  max_sub_questions: 6
  max_rounds: 2
  max_sonar_calls: 15
  concurrency: 5
  clarify_max_questions: 3
  reasoning_tier: reasoning
  fast_tier: fast
  reports_dir: data/research
```

**Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_deep_research_config.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/castelino/config.py config.yaml tests/test_deep_research_config.py
git commit -m "feat(deep-research): add DeepResearchCfg"
```

---

## Task 2: Package scaffold

**Files:**
- Create: `src/castelino/agents/research/deep/__init__.py`

**Step 1: Create the package**

```python
# src/castelino/agents/research/deep/__init__.py
"""Deep research engine — multi-agent, Sonar-backed, cited reports.

Public API:
    DeepResearchOrchestrator — drives the clarify → research → synthesize loop.
    DeepResearchReport, ResearchSession — output + session models.
"""
```

**Step 2: Verify it imports**

Run: `uv run python -c "import castelino.agents.research.deep; print('ok')"`
Expected: `ok`

**Step 3: Commit**

```bash
git add src/castelino/agents/research/deep/__init__.py
git commit -m "feat(deep-research): package scaffold"
```

---

## Task 3: Data models

**Files:**
- Create: `src/castelino/agents/research/deep/models.py`
- Test: `tests/test_deep_research_models.py`

**Step 1: Write the failing test**

```python
# tests/test_deep_research_models.py
from datetime import UTC, datetime

from castelino.agents.research.deep.models import (
    ClarificationQuestion, DeepResearchReport, ReflectionResult, ResearchSession,
    ResearchStatus, SourceRef, SubFinding, SubQuestion,
)


def test_source_ref_roundtrip():
    s = SourceRef(title="Fed minutes", url="https://x.com/a", snippet="...")
    assert s.url == "https://x.com/a"


def test_session_defaults_and_serialization():
    sess = ResearchSession(
        id="abc123",
        original_query="will the fed cut?",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    assert sess.status == ResearchStatus.CREATED
    assert sess.reworded_query == ""
    assert sess.clarifying_questions == []
    assert sess.sonar_calls_used == 0
    # round-trips through JSON cleanly (used by the disk store)
    blob = sess.model_dump_json()
    again = ResearchSession.model_validate_json(blob)
    assert again.id == "abc123"


def test_report_dedups_nothing_by_construction():
    rep = DeepResearchReport(
        exec_summary="summary",
        findings=[SubFinding(sub_question_id="q1", summary="f", key_points=["p"])],
        sources=[SourceRef(title="t", url="u", snippet="s")],
        confidence=0.7,
    )
    assert rep.findings[0].sub_question_id == "q1"
    assert rep.confidence == 0.7
```

**Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_deep_research_models.py -v`
Expected: FAIL — module not found.

**Step 3: Implement**

```python
# src/castelino/agents/research/deep/models.py
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ResearchStatus(str, Enum):
    CREATED = "created"
    AWAITING_ANSWERS = "awaiting_answers"
    RESEARCHING = "researching"
    SYNTHESIZING = "synthesizing"
    COMPLETE = "complete"
    FAILED = "failed"


class SourceRef(BaseModel):
    """A web source backing a finding. Web-oriented (vs persona Citation)."""
    title: str = ""
    url: str = ""
    snippet: str = ""


class ClarificationQuestion(BaseModel):
    question: str
    why: str = ""


class ClarifierResult(BaseModel):
    """Output of the Clarifier agent."""
    reworded_query: str
    clarifying_questions: list[ClarificationQuestion] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)  # used in --no-clarify mode


class SubQuestion(BaseModel):
    id: str
    text: str
    rationale: str = ""
    round: int = 1


class DecompositionResult(BaseModel):
    """Output of the Lead/decomposer agent."""
    sub_questions: list[SubQuestion] = Field(default_factory=list)


class SubFinding(BaseModel):
    sub_question_id: str
    summary: str = ""
    key_points: list[str] = Field(default_factory=list)
    citations: list[SourceRef] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    error: str | None = None


class ReflectionResult(BaseModel):
    is_sufficient: bool
    gaps: list[str] = Field(default_factory=list)
    new_sub_questions: list[SubQuestion] = Field(default_factory=list)


class DeepResearchReport(BaseModel):
    exec_summary: str
    findings: list[SubFinding] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    caveats: list[str] = Field(default_factory=list)
    gaps_remaining: list[str] = Field(default_factory=list)


class ResearchRound(BaseModel):
    round: int
    sub_questions: list[SubQuestion] = Field(default_factory=list)
    findings: list[SubFinding] = Field(default_factory=list)
    reflection: ReflectionResult | None = None


class ResearchSession(BaseModel):
    id: str
    original_query: str
    reworded_query: str = ""
    status: ResearchStatus = ResearchStatus.CREATED
    clarifying_questions: list[ClarificationQuestion] = Field(default_factory=list)
    answers: dict[str, str] = Field(default_factory=dict)
    rounds: list[ResearchRound] = Field(default_factory=list)
    report: DeepResearchReport | None = None
    sonar_calls_used: int = 0
    error: str | None = None
    created_at: datetime
    updated_at: datetime
```

**Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_deep_research_models.py -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add src/castelino/agents/research/deep/models.py tests/test_deep_research_models.py
git commit -m "feat(deep-research): pydantic data models"
```

---

## Task 4: Sonar client abstraction

A thin wrapper so sub-agents depend on an interface (real Perplexity in prod, fake in tests). Mirrors the `LLMClient`/`FakeLLMClient` split in `agents/base.py`.

**Files:**
- Create: `src/castelino/agents/research/deep/sonar_client.py`
- Test: `tests/test_deep_research_sonar_client.py`

**Step 1: Write the failing test**

```python
# tests/test_deep_research_sonar_client.py
from castelino.agents.research.deep.sonar_client import (
    FakeSonarClient, SonarResult,
)
from castelino.agents.research.deep.models import SourceRef


def test_fake_sonar_returns_registered_result():
    fake = FakeSonarClient()
    fake.register("inflation", SonarResult(
        content="CPI rose 3.1% YoY",
        sources=[SourceRef(title="BLS", url="https://bls.gov", snippet="CPI 3.1%")],
    ))
    out = fake.search("what is inflation right now")
    assert "3.1%" in out.content
    assert out.sources[0].url == "https://bls.gov"
    assert fake.call_count == 1


def test_fake_sonar_default_when_unmatched():
    fake = FakeSonarClient(default=SonarResult(content="no data", sources=[]))
    out = fake.search("anything")
    assert out.content == "no data"
```

**Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_deep_research_sonar_client.py -v`
Expected: FAIL — module not found.

**Step 3: Implement**

```python
# src/castelino/agents/research/deep/sonar_client.py
"""Sonar search client. Real impl hits Perplexity via the OpenAI SDK
(base_url=https://api.perplexity.ai); FakeSonarClient is for tests.

Perplexity returns the answer text in choices[0].message.content and a
top-level `citations` list of URLs on the response object.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from castelino.agents.research.deep.models import SourceRef
from castelino.config import get_settings

log = logging.getLogger(__name__)


class SonarResult:
    def __init__(self, *, content: str, sources: list[SourceRef]):
        self.content = content
        self.sources = sources


class SonarClient(ABC):
    @abstractmethod
    def search(self, query: str) -> SonarResult: ...


_SONAR_SYSTEM = (
    "You are a meticulous web research assistant. Answer the question using "
    "current, real web sources. Be specific and factual. Cite figures and "
    "dates. If you are unsure, say so rather than guessing."
)


class PerplexitySonarClient(SonarClient):
    """Real impl. Returns an empty result (no raise) when the key is unset
    or the call fails — matches the codebase 'returns [] on failure' rule."""

    def search(self, query: str) -> SonarResult:
        cfg = get_settings()
        api_key = cfg.perplexity_api_key
        if not api_key:
            log.debug("PERPLEXITY_API_KEY not set — Sonar search skipped")
            return SonarResult(content="", sources=[])
        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key, base_url="https://api.perplexity.ai")
            resp = client.chat.completions.create(
                model=cfg.sonar.model,
                messages=[
                    {"role": "system", "content": _SONAR_SYSTEM},
                    {"role": "user", "content": query},
                ],
                temperature=0.0,
            )
            content = (resp.choices[0].message.content or "").strip()
            urls = getattr(resp, "citations", None) or []
            sources = [SourceRef(title=u, url=u, snippet="") for u in urls]
            return SonarResult(content=content, sources=sources)
        except Exception as e:  # noqa: BLE001
            log.warning("Sonar search failed for %r: %s", query[:80], e)
            return SonarResult(content="", sources=[])


class FakeSonarClient(SonarClient):
    """Deterministic test double. Register substring → SonarResult."""

    def __init__(self, default: SonarResult | None = None):
        self._by_substr: list[tuple[str, SonarResult]] = []
        self._default = default
        self.call_count = 0
        self.queries: list[str] = []

    def register(self, substring: str, result: SonarResult) -> None:
        self._by_substr.append((substring.lower(), result))

    def search(self, query: str) -> SonarResult:
        self.call_count += 1
        self.queries.append(query)
        ql = query.lower()
        for sub, res in self._by_substr:
            if sub in ql:
                return res
        if self._default is not None:
            return self._default
        return SonarResult(content="", sources=[])
```

**Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_deep_research_sonar_client.py -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add src/castelino/agents/research/deep/sonar_client.py tests/test_deep_research_sonar_client.py
git commit -m "feat(deep-research): Sonar client interface + fake"
```

---

## Task 5: Clarifier agent

Rewords the raw query and produces ≤`clarify_max_questions` clarifying questions. Subclasses `StructuredAgent` so it inherits tier resolution and the `FakeLLMClient` test path.

**Files:**
- Create: `src/castelino/agents/research/deep/clarifier.py`
- Test: `tests/test_deep_research_clarifier.py`

**Step 1: Write the failing test**

```python
# tests/test_deep_research_clarifier.py
from castelino.agents.base import FakeLLMClient, set_llm_client
from castelino.agents.research.deep.clarifier import ClarifierAgent
from castelino.agents.research.deep.models import (
    ClarificationQuestion, ClarifierResult,
)


def test_clarifier_rewords_and_asks(monkeypatch):
    fake = FakeLLMClient()
    fake.register("ClarifierResult", lambda s, u: ClarifierResult(
        reworded_query="What is the probability the Fed cuts rates in 2026?",
        clarifying_questions=[
            ClarificationQuestion(question="Which meeting?", why="timing matters"),
        ],
    ))
    set_llm_client(fake)
    out = ClarifierAgent()(query="will the fed cut")
    assert "Fed" in out.reworded_query
    assert len(out.clarifying_questions) == 1
    set_llm_client(None)  # reset singleton
```

**Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_deep_research_clarifier.py -v`
Expected: FAIL — module not found.

**Step 3: Implement**

```python
# src/castelino/agents/research/deep/clarifier.py
from __future__ import annotations

from castelino.agents.base import StructuredAgent
from castelino.agents.research.deep.models import ClarifierResult
from castelino.config import get_settings

SYSTEM = """\
You are the Clarifier in a deep-research system. Given a user's raw research
query you do TWO things:
1. Reword it into a single precise, self-contained research question.
2. Produce a SHORT list of clarifying questions (each with a one-line `why`)
   whose answers would most sharpen the research. Ask only what materially
   changes the research — scope, timeframe, geography, the user's intent.
If the query is already fully specified, return an empty question list and put
any reasonable assumptions in `assumptions`.
"""


class ClarifierAgent(StructuredAgent[ClarifierResult]):
    name = "deep_clarifier"
    output_schema = ClarifierResult

    @property
    def tier(self) -> str:  # resolved from config, not hardcoded
        return get_settings().deep_research.reasoning_tier

    def system_prompt(self) -> str:
        return SYSTEM

    def user_prompt(self, *, query: str) -> str:
        cap = get_settings().deep_research.clarify_max_questions
        return (
            f"Raw query: {query}\n\n"
            f"Return at most {cap} clarifying questions."
        )
```

> Note: `StructuredAgent.tier` is a class attribute in `base.py`. Overriding it as a `property` works because `__call__` reads `self.tier`. If the linter objects, set `tier = "reasoning"` as a class attr and instead read the configured tier inside `__call__` — but the property is cleaner and keeps config authority.

**Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_deep_research_clarifier.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/castelino/agents/research/deep/clarifier.py tests/test_deep_research_clarifier.py
git commit -m "feat(deep-research): clarifier agent"
```

---

## Task 6: Lead (decomposer) agent

Breaks the enriched query into ≤`max_sub_questions` sub-questions. On reflection rounds it decomposes only the gaps.

**Files:**
- Create: `src/castelino/agents/research/deep/lead.py`
- Test: `tests/test_deep_research_lead.py`

**Step 1: Write the failing test**

```python
# tests/test_deep_research_lead.py
from castelino.agents.base import FakeLLMClient, set_llm_client
from castelino.agents.research.deep.lead import LeadAgent
from castelino.agents.research.deep.models import DecompositionResult, SubQuestion


def test_lead_decomposes_and_caps(monkeypatch):
    fake = FakeLLMClient()
    # LLM tries to return 8; agent must cap to config max (6)
    fake.register("DecompositionResult", lambda s, u: DecompositionResult(
        sub_questions=[SubQuestion(id=f"q{i}", text=f"sub {i}") for i in range(8)]
    ))
    set_llm_client(fake)
    out = LeadAgent().decompose(
        reworded_query="Will the Fed cut in 2026?",
        answers={"Which meeting?": "all of 2026"},
        round_num=1,
    )
    assert len(out) <= 6
    assert all(isinstance(q, SubQuestion) for q in out)
    set_llm_client(None)
```

**Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_deep_research_lead.py -v`
Expected: FAIL — module not found.

**Step 3: Implement**

```python
# src/castelino/agents/research/deep/lead.py
from __future__ import annotations

from castelino.agents.base import StructuredAgent
from castelino.agents.research.deep.models import DecompositionResult, SubQuestion
from castelino.config import get_settings

SYSTEM = """\
You are the Lead Researcher. Decompose a research question into a small set of
INDEPENDENT sub-questions that can each be researched in isolation and whose
answers together fully cover the main question. Each sub-question gets a short
rationale. Prefer fewer, higher-leverage sub-questions over many shallow ones.
Do not overlap sub-questions.
"""


class LeadAgent(StructuredAgent[DecompositionResult]):
    name = "deep_lead"
    output_schema = DecompositionResult

    @property
    def tier(self) -> str:
        return get_settings().deep_research.reasoning_tier

    def system_prompt(self) -> str:
        return SYSTEM

    def user_prompt(self, *, reworded_query, answers, round_num, gaps=None) -> str:
        ans = "\n".join(f"- {k}: {v}" for k, v in (answers or {}).items()) or "- (none)"
        cap = get_settings().deep_research.max_sub_questions
        base = (
            f"Main question: {reworded_query}\n\n"
            f"Analyst clarifications:\n{ans}\n\n"
        )
        if gaps:
            g = "\n".join(f"- {x}" for x in gaps)
            base += f"This is round {round_num}. Cover ONLY these gaps:\n{g}\n\n"
        return base + f"Return at most {cap} sub-questions."

    def decompose(self, *, reworded_query, answers, round_num, gaps=None):
        cap = get_settings().deep_research.max_sub_questions
        result = self(
            reworded_query=reworded_query, answers=answers,
            round_num=round_num, gaps=gaps,
        )
        # Hard cap regardless of what the LLM returned; stamp the round.
        out: list[SubQuestion] = []
        for i, q in enumerate(result.sub_questions[:cap]):
            out.append(q.model_copy(update={"round": round_num, "id": q.id or f"r{round_num}q{i}"}))
        return out
```

**Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_deep_research_lead.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/castelino/agents/research/deep/lead.py tests/test_deep_research_lead.py
git commit -m "feat(deep-research): lead/decomposer agent with hard cap"
```

---

## Task 7: Sub-agent (research one sub-question)

Calls Sonar for one sub-question, then uses the LLM to distill the Sonar text into a structured `SubFinding`. Sonar failures degrade gracefully to a flagged finding.

**Files:**
- Create: `src/castelino/agents/research/deep/sub_agent.py`
- Test: `tests/test_deep_research_sub_agent.py`

**Step 1: Write the failing test**

```python
# tests/test_deep_research_sub_agent.py
from castelino.agents.base import FakeLLMClient
from castelino.agents.research.deep.models import SourceRef, SubFinding, SubQuestion
from castelino.agents.research.deep.sonar_client import FakeSonarClient, SonarResult
from castelino.agents.research.deep.sub_agent import SubAgent


def _fake_llm():
    fake = FakeLLMClient()
    fake.register("SubFinding", lambda s, u: SubFinding(
        sub_question_id="q1", summary="distilled", key_points=["a", "b"],
        confidence=0.8,
    ))
    return fake


def test_sub_agent_happy_path():
    sonar = FakeSonarClient()
    sonar.register("cpi", SonarResult(
        content="CPI was 3.1%", sources=[SourceRef(title="BLS", url="https://bls.gov")],
    ))
    sa = SubAgent(llm=_fake_llm(), sonar=sonar)
    finding = sa.run(SubQuestion(id="q1", text="What is current CPI?"))
    assert finding.sub_question_id == "q1"
    assert finding.summary == "distilled"
    # citations come from Sonar, merged onto the finding
    assert any(c.url == "https://bls.gov" for c in finding.citations)
    assert finding.error is None


def test_sub_agent_sonar_empty_flags_error():
    sonar = FakeSonarClient(default=SonarResult(content="", sources=[]))
    sa = SubAgent(llm=_fake_llm(), sonar=sonar)
    finding = sa.run(SubQuestion(id="q9", text="obscure thing"))
    assert finding.error is not None
    assert finding.sub_question_id == "q9"
    assert finding.confidence == 0.0
```

**Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_deep_research_sub_agent.py -v`
Expected: FAIL — module not found.

**Step 3: Implement**

```python
# src/castelino/agents/research/deep/sub_agent.py
from __future__ import annotations

from castelino.agents.base import LLMClient, get_llm_client
from castelino.agents.research.deep.models import SubFinding, SubQuestion
from castelino.agents.research.deep.sonar_client import SonarClient
from castelino.config import get_settings

SYSTEM = """\
You distill raw web-research text into a structured finding for ONE
sub-question. Use ONLY the provided research text — do not add outside facts.
Summarize faithfully, extract the key points, and rate your confidence (0-1)
in how well the text answers the sub-question.
"""


class SubAgent:
    """One parallel researcher. Not a StructuredAgent subclass because it
    composes a Sonar call + an LLM distillation; it takes injectable clients
    so tests stay deterministic."""

    def __init__(self, *, llm: LLMClient | None = None, sonar: SonarClient):
        self._llm = llm or get_llm_client()
        self._sonar = sonar

    def run(self, sub_q: SubQuestion) -> SubFinding:
        cfg = get_settings()
        res = self._sonar.search(sub_q.text)
        if not res.content.strip():
            return SubFinding(
                sub_question_id=sub_q.id,
                summary="",
                error="no research content returned (Sonar empty or unavailable)",
                confidence=0.0,
            )
        tier = cfg.deep_research.fast_tier
        model_id = getattr(cfg.models, tier)
        finding = self._llm.parse(
            model=model_id,
            system=SYSTEM,
            user=(
                f"Sub-question: {sub_q.text}\n\n"
                f"Research text:\n{res.content}\n\n"
                "Produce a SubFinding. Set sub_question_id exactly to: "
                f"{sub_q.id}"
            ),
            schema=SubFinding,
        )
        # Force the id (LLMs drift) and merge Sonar's real source URLs.
        merged = list(finding.citations) + list(res.sources)
        return finding.model_copy(update={
            "sub_question_id": sub_q.id,
            "citations": merged,
        })
```

> Note: this resolves the model id directly from `cfg.models.<fast_tier>` rather than through `_resolve_model_id`, because in backtest mode deep-research isn't used. If you later want backtest support, import and call `castelino.agents.base._resolve_model_id`.

**Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_deep_research_sub_agent.py -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add src/castelino/agents/research/deep/sub_agent.py tests/test_deep_research_sub_agent.py
git commit -m "feat(deep-research): parallel sub-agent (Sonar + distill)"
```

---

## Task 8: Synthesizer agent (draft + reflect)

Two LLM calls: (a) merge findings into a `DeepResearchReport`; (b) reflect — is it sufficient, what are the gaps, what new sub-questions.

**Files:**
- Create: `src/castelino/agents/research/deep/synthesizer.py`
- Test: `tests/test_deep_research_synthesizer.py`

**Step 1: Write the failing test**

```python
# tests/test_deep_research_synthesizer.py
from castelino.agents.base import FakeLLMClient
from castelino.agents.research.deep.models import (
    DeepResearchReport, ReflectionResult, SourceRef, SubFinding,
)
from castelino.agents.research.deep.synthesizer import Synthesizer


def _llm():
    fake = FakeLLMClient()
    fake.register("DeepResearchReport", lambda s, u: DeepResearchReport(
        exec_summary="The Fed is likely to hold.", confidence=0.6,
        sources=[SourceRef(title="t", url="u")],
    ))
    fake.register("ReflectionResult", lambda s, u: ReflectionResult(
        is_sufficient=True, gaps=[],
    ))
    return fake


def test_synthesize_builds_report():
    syn = Synthesizer(llm=_llm())
    findings = [SubFinding(sub_question_id="q1", summary="held last time")]
    report = syn.synthesize(reworded_query="Will the Fed hold?", findings=findings)
    assert "Fed" in report.exec_summary
    # findings are attached to the report by the synthesizer
    assert report.findings == findings


def test_reflect_returns_sufficiency():
    syn = Synthesizer(llm=_llm())
    refl = syn.reflect(
        reworded_query="Will the Fed hold?",
        report=DeepResearchReport(exec_summary="x"),
        round_num=1,
    )
    assert refl.is_sufficient is True
```

**Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_deep_research_synthesizer.py -v`
Expected: FAIL — module not found.

**Step 3: Implement**

```python
# src/castelino/agents/research/deep/synthesizer.py
from __future__ import annotations

from castelino.agents.base import LLMClient, get_llm_client
from castelino.agents.research.deep.models import (
    DeepResearchReport, ReflectionResult, SubFinding,
)
from castelino.config import get_settings

SYNTH_SYSTEM = """\
You are the Synthesizer. You receive findings (each answering a sub-question,
with citations) and the main research question. Write a single coherent report:
- exec_summary: a clear, well-structured explanation for the analyst that
  directly answers the main question, integrating the findings. This is the
  human-facing answer; make it genuinely explanatory, not a list.
- sources: the deduplicated union of all citations across findings.
- confidence: your overall confidence (0-1).
- caveats: important limitations.
Only use the supplied findings. Do not invent facts or sources.
"""

REFLECT_SYSTEM = """\
You are a research critic. Given the main question and the draft report,
decide whether the research SUFFICIENTLY answers the question. If not, list
the specific gaps and propose new, targeted sub-questions to fill them. Be
strict but not perfectionist — only flag gaps that materially affect the
answer.
"""


def _dedup_sources(findings):
    seen, out = set(), []
    for f in findings:
        for c in f.citations:
            key = (c.url or c.title).strip().lower()
            if key and key not in seen:
                seen.add(key)
                out.append(c)
    return out


class Synthesizer:
    def __init__(self, *, llm: LLMClient | None = None):
        self._llm = llm or get_llm_client()

    def _model(self) -> str:
        cfg = get_settings()
        return getattr(cfg.models, cfg.deep_research.reasoning_tier)

    def synthesize(self, *, reworded_query: str, findings: list[SubFinding]) -> DeepResearchReport:
        joined = "\n\n".join(
            f"[{f.sub_question_id}] (conf={f.confidence})\n{f.summary}\n"
            + "\n".join(f"  • {p}" for p in f.key_points)
            for f in findings
        ) or "(no findings)"
        report = self._llm.parse(
            model=self._model(),
            system=SYNTH_SYSTEM,
            user=f"Main question: {reworded_query}\n\nFindings:\n{joined}",
            schema=DeepResearchReport,
            max_tokens=2500,
        )
        # Attach findings + ensure deduped sources even if the LLM skipped some.
        return report.model_copy(update={
            "findings": findings,
            "sources": report.sources or _dedup_sources(findings),
        })

    def reflect(self, *, reworded_query: str, report: DeepResearchReport, round_num: int) -> ReflectionResult:
        return self._llm.parse(
            model=self._model(),
            system=REFLECT_SYSTEM,
            user=(
                f"Main question: {reworded_query}\n\n"
                f"Round {round_num} draft summary:\n{report.exec_summary}\n\n"
                f"Caveats: {report.caveats}\n\n"
                "Is this sufficient? If not, list gaps and new sub-questions."
            ),
            schema=ReflectionResult,
            max_tokens=1200,
        )
```

**Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_deep_research_synthesizer.py -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add src/castelino/agents/research/deep/synthesizer.py tests/test_deep_research_synthesizer.py
git commit -m "feat(deep-research): synthesizer + reflection"
```

---

## Task 9: Session store (atomic disk persistence)

**Files:**
- Create: `src/castelino/agents/research/deep/store.py`
- Test: `tests/test_deep_research_store.py`

**Step 1: Write the failing test**

```python
# tests/test_deep_research_store.py
from datetime import UTC, datetime

from castelino.agents.research.deep.models import ResearchSession, ResearchStatus
from castelino.agents.research.deep.store import ResearchStore


def _sess(id_="s1"):
    return ResearchSession(
        id=id_, original_query="q",
        created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
    )


def test_store_roundtrip(tmp_path):
    store = ResearchStore(root=tmp_path)
    sess = _sess()
    store.save(sess)
    loaded = store.load("s1")
    assert loaded.id == "s1"
    assert loaded.status == ResearchStatus.CREATED


def test_store_list_and_missing(tmp_path):
    store = ResearchStore(root=tmp_path)
    store.save(_sess("a"))
    store.save(_sess("b"))
    ids = {s.id for s in store.list()}
    assert ids == {"a", "b"}
    assert store.load("nope") is None
```

**Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_deep_research_store.py -v`
Expected: FAIL — module not found.

**Step 3: Implement**

```python
# src/castelino/agents/research/deep/store.py
from __future__ import annotations

import logging
import os
from pathlib import Path

from castelino.agents.research.deep.models import ResearchSession
from castelino.config import get_settings

log = logging.getLogger(__name__)


class ResearchStore:
    """Atomic JSON store for research sessions (one file per session)."""

    def __init__(self, root: Path | None = None):
        if root is None:
            cfg = get_settings()
            root = cfg.root / cfg.deep_research.reports_dir
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        return self.root / f"{session_id}.json"

    def save(self, session: ResearchSession) -> None:
        path = self._path(session.id)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(session.model_dump_json(indent=2))
        os.replace(tmp, path)  # atomic — avoids partial-write corruption

    def load(self, session_id: str) -> ResearchSession | None:
        path = self._path(session_id)
        if not path.exists():
            return None
        try:
            return ResearchSession.model_validate_json(path.read_text())
        except Exception as e:  # noqa: BLE001
            log.warning("research session %s corrupt: %s", session_id, e)
            return None

    def list(self) -> list[ResearchSession]:
        out = []
        for p in sorted(self.root.glob("*.json")):
            try:
                out.append(ResearchSession.model_validate_json(p.read_text()))
            except Exception:  # noqa: BLE001
                continue
        return out
```

**Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_deep_research_store.py -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add src/castelino/agents/research/deep/store.py tests/test_deep_research_store.py
git commit -m "feat(deep-research): atomic session store"
```

---

## Task 10: Orchestrator — start & clarify (→ AWAITING_ANSWERS)

The orchestrator owns the state machine. Split across Tasks 10–13 so each is testable.

**Files:**
- Create: `src/castelino/agents/research/deep/orchestrator.py`
- Test: `tests/test_deep_research_orchestrator_start.py`

**Step 1: Write the failing test**

```python
# tests/test_deep_research_orchestrator_start.py
from castelino.agents.base import FakeLLMClient
from castelino.agents.research.deep.models import (
    ClarificationQuestion, ClarifierResult, ResearchStatus,
)
from castelino.agents.research.deep.orchestrator import DeepResearchOrchestrator
from castelino.agents.research.deep.sonar_client import FakeSonarClient
from castelino.agents.research.deep.store import ResearchStore


def _orch(tmp_path, llm, sonar=None):
    return DeepResearchOrchestrator(
        llm=llm, sonar=sonar or FakeSonarClient(),
        store=ResearchStore(root=tmp_path),
    )


def test_start_rewords_and_pauses(tmp_path):
    llm = FakeLLMClient()
    llm.register("ClarifierResult", lambda s, u: ClarifierResult(
        reworded_query="Precise Q?",
        clarifying_questions=[ClarificationQuestion(question="Scope?")],
    ))
    orch = _orch(tmp_path, llm)
    sess = orch.start("raw query")
    assert sess.status == ResearchStatus.AWAITING_ANSWERS
    assert sess.reworded_query == "Precise Q?"
    assert len(sess.clarifying_questions) == 1
    # persisted
    assert orch.store.load(sess.id).status == ResearchStatus.AWAITING_ANSWERS


def test_start_no_questions_skips_to_ready(tmp_path):
    llm = FakeLLMClient()
    llm.register("ClarifierResult", lambda s, u: ClarifierResult(
        reworded_query="Precise Q?", clarifying_questions=[],
    ))
    orch = _orch(tmp_path, llm)
    sess = orch.start("raw query")
    # No questions → still AWAITING_ANSWERS but answerable with empty dict;
    # the caller (CLI/API) decides to proceed immediately.
    assert sess.status == ResearchStatus.AWAITING_ANSWERS
    assert sess.clarifying_questions == []
```

**Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_deep_research_orchestrator_start.py -v`
Expected: FAIL — module not found.

**Step 3: Implement (partial — start only; more methods added in 11–13)**

```python
# src/castelino/agents/research/deep/orchestrator.py
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from castelino.agents.base import LLMClient, get_llm_client
from castelino.agents.research.deep.clarifier import ClarifierAgent
from castelino.agents.research.deep.models import (
    ResearchSession, ResearchStatus,
)
from castelino.agents.research.deep.sonar_client import (
    PerplexitySonarClient, SonarClient,
)
from castelino.agents.research.deep.store import ResearchStore

log = logging.getLogger(__name__)


class DeepResearchOrchestrator:
    def __init__(
        self, *,
        llm: LLMClient | None = None,
        sonar: SonarClient | None = None,
        store: ResearchStore | None = None,
    ):
        self.llm = llm or get_llm_client()
        self.sonar = sonar or PerplexitySonarClient()
        self.store = store or ResearchStore()

    def _new_id(self) -> str:
        return uuid.uuid4().hex[:12]

    def start(self, query: str) -> ResearchSession:
        now = datetime.now(UTC)
        sess = ResearchSession(
            id=self._new_id(), original_query=query,
            created_at=now, updated_at=now,
        )
        clar = ClarifierAgent()(query=query)  # uses global llm client
        sess.reworded_query = clar.reworded_query
        sess.clarifying_questions = clar.clarifying_questions
        sess.status = ResearchStatus.AWAITING_ANSWERS
        sess.updated_at = datetime.now(UTC)
        self.store.save(sess)
        return sess
```

> Note: `ClarifierAgent` reads the global LLM client via `get_llm_client()`. In tests, pass the fake to the orchestrator AND it will be used because the orchestrator's agents go through the same global singleton. To be safe, the test sets the orchestrator's `llm` and the ClarifierAgent path uses the global — so in Task 10's test, also call `set_llm_client(llm)`. **Adjust the test to call `set_llm_client(llm)` in `_orch`, and reset to `None` after.** (Simpler than threading the client through every agent.)

**Revised `_orch` helper for the test:**

```python
from castelino.agents.base import set_llm_client

def _orch(tmp_path, llm, sonar=None):
    set_llm_client(llm)
    return DeepResearchOrchestrator(
        llm=llm, sonar=sonar or FakeSonarClient(),
        store=ResearchStore(root=tmp_path),
    )
```

(Add `set_llm_client(None)` teardown via a fixture or at test end.)

**Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_deep_research_orchestrator_start.py -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add src/castelino/agents/research/deep/orchestrator.py tests/test_deep_research_orchestrator_start.py
git commit -m "feat(deep-research): orchestrator start + clarify"
```

---

## Task 11: Orchestrator — research fan-out (semaphore + budget)

Adds `answer()` which resumes from AWAITING_ANSWERS, runs the Lead decomposition, then fans out sub-agents concurrently under a semaphore, respecting the global Sonar budget. This method runs the FIRST round only; Task 12 adds synthesis + the reflection loop.

**Files:**
- Modify: `src/castelino/agents/research/deep/orchestrator.py`
- Test: `tests/test_deep_research_orchestrator_research.py`

**Step 1: Write the failing test**

```python
# tests/test_deep_research_orchestrator_research.py
import pytest

from castelino.agents.base import FakeLLMClient, set_llm_client
from castelino.agents.research.deep.models import (
    DecompositionResult, ResearchStatus, SubFinding, SubQuestion,
)
from castelino.agents.research.deep.orchestrator import DeepResearchOrchestrator
from castelino.agents.research.deep.sonar_client import FakeSonarClient, SonarResult
from castelino.agents.research.deep.store import ResearchStore


@pytest.fixture(autouse=True)
def _reset_llm():
    yield
    set_llm_client(None)


def _llm_with(n_subs):
    llm = FakeLLMClient()
    llm.register("DecompositionResult", lambda s, u: DecompositionResult(
        sub_questions=[SubQuestion(id=f"q{i}", text=f"sub {i}") for i in range(n_subs)]
    ))
    llm.register("SubFinding", lambda s, u: SubFinding(
        sub_question_id="x", summary="found", key_points=["k"], confidence=0.7,
    ))
    return llm


def test_research_fans_out_and_caps_budget(tmp_path):
    llm = _llm_with(n_subs=10)        # tries 10
    set_llm_client(llm)
    sonar = FakeSonarClient(default=SonarResult(content="data", sources=[]))
    orch = DeepResearchOrchestrator(llm=llm, sonar=sonar, store=ResearchStore(root=tmp_path))
    sess = orch.start("q")
    sess = orch.run_first_round(sess.id, answers={})
    # capped to max_sub_questions (6) → 6 sonar calls, not 10
    assert sonar.call_count == 6
    assert len(sess.rounds[0].findings) == 6
    assert sess.status == ResearchStatus.SYNTHESIZING
```

**Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_deep_research_orchestrator_research.py -v`
Expected: FAIL — `run_first_round` not defined.

**Step 3: Implement (add to orchestrator)**

```python
# add imports at top of orchestrator.py
import asyncio
from castelino.agents.research.deep.lead import LeadAgent
from castelino.agents.research.deep.sub_agent import SubAgent
from castelino.agents.research.deep.models import ResearchRound, SubQuestion
from castelino.config import get_settings


# add methods inside DeepResearchOrchestrator:

    async def _research_subquestions(self, sub_qs, remaining_budget):
        """Fan out sub-agents under a concurrency semaphore. Caps at budget."""
        cfg = get_settings().deep_research
        to_run = sub_qs[: max(0, remaining_budget)]
        sem = asyncio.Semaphore(cfg.concurrency)
        sub_agent = SubAgent(llm=self.llm, sonar=self.sonar)

        async def _one(sub_q):
            async with sem:
                # SubAgent.run is sync (Sonar SDK + LLM are sync) — offload.
                return await asyncio.to_thread(sub_agent.run, sub_q)

        return list(await asyncio.gather(*[_one(q) for q in to_run]))

    def run_first_round(self, session_id: str, *, answers: dict) -> ResearchSession:
        sess = self.store.load(session_id)
        if sess is None:
            raise ValueError(f"unknown session {session_id}")
        sess.answers = answers or {}
        sess.status = ResearchStatus.RESEARCHING
        self.store.save(sess)

        cfg = get_settings().deep_research
        lead = LeadAgent()
        sub_qs = lead.decompose(
            reworded_query=sess.reworded_query,
            answers=sess.answers, round_num=1,
        )
        remaining = cfg.max_sonar_calls - sess.sonar_calls_used
        findings = asyncio.run(self._research_subquestions(sub_qs, remaining))
        sess.sonar_calls_used += len(findings)
        sess.rounds.append(ResearchRound(round=1, sub_questions=sub_qs, findings=findings))
        sess.status = ResearchStatus.SYNTHESIZING
        sess.updated_at = datetime.now(UTC)
        self.store.save(sess)
        return sess
```

**Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_deep_research_orchestrator_research.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/castelino/agents/research/deep/orchestrator.py tests/test_deep_research_orchestrator_research.py
git commit -m "feat(deep-research): research fan-out with semaphore + budget cap"
```

---

## Task 12: Orchestrator — synthesize + reflection loop (→ COMPLETE)

Adds `finish()` which synthesizes, reflects, optionally runs bounded extra rounds (gap sub-questions only, respecting `max_rounds` and budget), then completes and persists the report.

**Files:**
- Modify: `src/castelino/agents/research/deep/orchestrator.py`
- Test: `tests/test_deep_research_orchestrator_finish.py`

**Step 1: Write the failing test**

```python
# tests/test_deep_research_orchestrator_finish.py
import pytest

from castelino.agents.base import FakeLLMClient, set_llm_client
from castelino.agents.research.deep.models import (
    DecompositionResult, DeepResearchReport, ReflectionResult, ResearchStatus,
    SubFinding, SubQuestion,
)
from castelino.agents.research.deep.orchestrator import DeepResearchOrchestrator
from castelino.agents.research.deep.sonar_client import FakeSonarClient, SonarResult
from castelino.agents.research.deep.store import ResearchStore


@pytest.fixture(autouse=True)
def _reset_llm():
    yield
    set_llm_client(None)


def _base_llm():
    llm = FakeLLMClient()
    llm.register("DecompositionResult", lambda s, u: DecompositionResult(
        sub_questions=[SubQuestion(id="q0", text="sub 0")]))
    llm.register("SubFinding", lambda s, u: SubFinding(
        sub_question_id="q0", summary="f", confidence=0.7))
    llm.register("DeepResearchReport", lambda s, u: DeepResearchReport(
        exec_summary="answer", confidence=0.7))
    return llm


def test_finish_sufficient_completes(tmp_path):
    llm = _base_llm()
    llm.register("ReflectionResult", lambda s, u: ReflectionResult(is_sufficient=True))
    set_llm_client(llm)
    sonar = FakeSonarClient(default=SonarResult(content="data", sources=[]))
    orch = DeepResearchOrchestrator(llm=llm, sonar=sonar, store=ResearchStore(root=tmp_path))
    sess = orch.start("q")
    sess = orch.run_first_round(sess.id, answers={})
    sess = orch.finish(sess.id)
    assert sess.status == ResearchStatus.COMPLETE
    assert sess.report.exec_summary == "answer"
    assert len(sess.rounds) == 1  # no extra round needed


def test_finish_insufficient_runs_second_round_then_stops(tmp_path):
    llm = _base_llm()
    # First reflection says insufficient with a gap; the loop is capped at max_rounds=2
    calls = {"n": 0}
    def _reflect(s, u):
        calls["n"] += 1
        if calls["n"] == 1:
            return ReflectionResult(
                is_sufficient=False, gaps=["missing X"],
                new_sub_questions=[SubQuestion(id="q1", text="X?")])
        return ReflectionResult(is_sufficient=True)
    llm.register("ReflectionResult", _reflect)
    set_llm_client(llm)
    sonar = FakeSonarClient(default=SonarResult(content="data", sources=[]))
    orch = DeepResearchOrchestrator(llm=llm, sonar=sonar, store=ResearchStore(root=tmp_path))
    sess = orch.start("q")
    sess = orch.run_first_round(sess.id, answers={})
    sess = orch.finish(sess.id)
    assert sess.status == ResearchStatus.COMPLETE
    assert len(sess.rounds) == 2  # one reflection-driven extra round, then capped
```

**Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_deep_research_orchestrator_finish.py -v`
Expected: FAIL — `finish` not defined.

**Step 3: Implement (add to orchestrator)**

```python
# add import
from castelino.agents.research.deep.synthesizer import Synthesizer


# add method inside DeepResearchOrchestrator:

    def finish(self, session_id: str) -> ResearchSession:
        sess = self.store.load(session_id)
        if sess is None:
            raise ValueError(f"unknown session {session_id}")
        cfg = get_settings().deep_research
        syn = Synthesizer(llm=self.llm)

        all_findings = [f for r in sess.rounds for f in r.findings]
        report = syn.synthesize(reworded_query=sess.reworded_query, findings=all_findings)

        round_num = len(sess.rounds)
        while round_num < cfg.max_rounds and sess.sonar_calls_used < cfg.max_sonar_calls:
            refl = syn.reflect(
                reworded_query=sess.reworded_query, report=report, round_num=round_num,
            )
            sess.rounds[-1].reflection = refl
            self.store.save(sess)
            if refl.is_sufficient or not refl.new_sub_questions:
                break
            # bounded extra round over the gap sub-questions
            round_num += 1
            gap_qs = [q.model_copy(update={"round": round_num}) for q in refl.new_sub_questions]
            remaining = cfg.max_sonar_calls - sess.sonar_calls_used
            findings = asyncio.run(self._research_subquestions(gap_qs, remaining))
            sess.sonar_calls_used += len(findings)
            sess.rounds.append(ResearchRound(round=round_num, sub_questions=gap_qs, findings=findings))
            self.store.save(sess)
            all_findings = [f for r in sess.rounds for f in r.findings]
            report = syn.synthesize(reworded_query=sess.reworded_query, findings=all_findings)

        # note any unfilled gaps from the last reflection
        last_refl = sess.rounds[-1].reflection
        if last_refl and not last_refl.is_sufficient:
            report = report.model_copy(update={"gaps_remaining": last_refl.gaps})

        sess.report = report
        sess.status = ResearchStatus.COMPLETE
        sess.updated_at = datetime.now(UTC)
        self.store.save(sess)
        return sess
```

**Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_deep_research_orchestrator_finish.py -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add src/castelino/agents/research/deep/orchestrator.py tests/test_deep_research_orchestrator_finish.py
git commit -m "feat(deep-research): synthesis + bounded reflection loop"
```

---

## Task 13: Orchestrator — failure path (all sub-agents fail → FAILED)

**Files:**
- Modify: `src/castelino/agents/research/deep/orchestrator.py` (in `run_first_round`, detect all-error findings)
- Test: `tests/test_deep_research_orchestrator_failure.py`

**Step 1: Write the failing test**

```python
# tests/test_deep_research_orchestrator_failure.py
import pytest

from castelino.agents.base import FakeLLMClient, set_llm_client
from castelino.agents.research.deep.models import (
    DecompositionResult, ResearchStatus, SubQuestion,
)
from castelino.agents.research.deep.orchestrator import DeepResearchOrchestrator
from castelino.agents.research.deep.sonar_client import FakeSonarClient, SonarResult
from castelino.agents.research.deep.store import ResearchStore


@pytest.fixture(autouse=True)
def _reset_llm():
    yield
    set_llm_client(None)


def test_all_subagents_fail_marks_failed(tmp_path):
    llm = FakeLLMClient()
    llm.register("DecompositionResult", lambda s, u: DecompositionResult(
        sub_questions=[SubQuestion(id="q0", text="a"), SubQuestion(id="q1", text="b")]))
    # SubFinding handler never invoked because Sonar returns empty (→ error finding)
    set_llm_client(llm)
    sonar = FakeSonarClient(default=SonarResult(content="", sources=[]))  # always empty
    orch = DeepResearchOrchestrator(llm=llm, sonar=sonar, store=ResearchStore(root=tmp_path))
    sess = orch.start("q")
    sess = orch.run_first_round(sess.id, answers={})
    assert sess.status == ResearchStatus.FAILED
    assert sess.error is not None
```

**Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_deep_research_orchestrator_failure.py -v`
Expected: FAIL — status is SYNTHESIZING, not FAILED.

**Step 3: Implement (modify the tail of `run_first_round`)**

Replace the status-setting tail of `run_first_round` with:

```python
        sess.rounds.append(ResearchRound(round=1, sub_questions=sub_qs, findings=findings))
        if findings and all(f.error for f in findings):
            sess.status = ResearchStatus.FAILED
            sess.error = "all sub-agents failed to gather research (Sonar unavailable?)"
        else:
            sess.status = ResearchStatus.SYNTHESIZING
        sess.updated_at = datetime.now(UTC)
        self.store.save(sess)
        return sess
```

**Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_deep_research_orchestrator_failure.py -v`
Then re-run the whole feature suite: `uv run pytest tests/ -k deep_research -v`
Expected: all PASS.

**Step 5: Commit**

```bash
git add src/castelino/agents/research/deep/orchestrator.py tests/test_deep_research_orchestrator_failure.py
git commit -m "feat(deep-research): fail fast when all sub-agents fail"
```

---

## Task 14: A convenience `run_sync` helper

A single entry point the CLI and a `--no-clarify` flow can call: start → (optionally) auto-answer → research → finish.

**Files:**
- Modify: `src/castelino/agents/research/deep/orchestrator.py`
- Test: `tests/test_deep_research_run_sync.py`

**Step 1: Write the failing test**

```python
# tests/test_deep_research_run_sync.py
import pytest
from castelino.agents.base import FakeLLMClient, set_llm_client
from castelino.agents.research.deep.models import (
    ClarifierResult, DecompositionResult, DeepResearchReport, ReflectionResult,
    ResearchStatus, SubFinding, SubQuestion,
)
from castelino.agents.research.deep.orchestrator import DeepResearchOrchestrator
from castelino.agents.research.deep.sonar_client import FakeSonarClient, SonarResult
from castelino.agents.research.deep.store import ResearchStore


@pytest.fixture(autouse=True)
def _reset_llm():
    yield
    set_llm_client(None)


def test_run_sync_end_to_end(tmp_path):
    llm = FakeLLMClient()
    llm.register("ClarifierResult", lambda s, u: ClarifierResult(reworded_query="Q?", clarifying_questions=[]))
    llm.register("DecompositionResult", lambda s, u: DecompositionResult(
        sub_questions=[SubQuestion(id="q0", text="a")]))
    llm.register("SubFinding", lambda s, u: SubFinding(sub_question_id="q0", summary="f", confidence=0.8))
    llm.register("DeepResearchReport", lambda s, u: DeepResearchReport(exec_summary="done", confidence=0.8))
    llm.register("ReflectionResult", lambda s, u: ReflectionResult(is_sufficient=True))
    set_llm_client(llm)
    orch = DeepResearchOrchestrator(
        llm=llm, sonar=FakeSonarClient(default=SonarResult(content="x", sources=[])),
        store=ResearchStore(root=tmp_path))
    sess = orch.run_sync("research question", answers={})
    assert sess.status == ResearchStatus.COMPLETE
    assert sess.report.exec_summary == "done"
```

**Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_deep_research_run_sync.py -v`
Expected: FAIL — `run_sync` not defined.

**Step 3: Implement (add to orchestrator)**

```python
    def run_sync(self, query: str, *, answers: dict | None = None) -> ResearchSession:
        """Full pipeline without an interactive pause (CLI / --no-clarify)."""
        sess = self.start(query)
        sess = self.run_first_round(sess.id, answers=answers or {})
        if sess.status == ResearchStatus.FAILED:
            return sess
        return self.finish(sess.id)
```

**Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_deep_research_run_sync.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/castelino/agents/research/deep/orchestrator.py tests/test_deep_research_run_sync.py
git commit -m "feat(deep-research): run_sync convenience entry point"
```

---

## Task 15: CLI command `castelino research`

**Files:**
- Modify: `src/castelino/orchestrator/cli.py` (add a new `@app.command()`)
- Test: `tests/test_deep_research_cli.py` (use Typer's `CliRunner`, mock the orchestrator)

**Step 1: Write the failing test**

```python
# tests/test_deep_research_cli.py
from typer.testing import CliRunner

from castelino.orchestrator.cli import app
from castelino.agents.research.deep.models import (
    DeepResearchReport, ResearchSession, ResearchStatus, SourceRef,
)
import castelino.orchestrator.cli as cli_mod


def test_research_command_no_clarify(monkeypatch):
    from datetime import UTC, datetime

    def fake_run_sync(self, query, *, answers=None):
        return ResearchSession(
            id="x", original_query=query, reworded_query="Q?",
            status=ResearchStatus.COMPLETE,
            report=DeepResearchReport(
                exec_summary="THE ANSWER", confidence=0.8,
                sources=[SourceRef(title="t", url="https://u")],
            ),
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )

    monkeypatch.setattr(
        "castelino.agents.research.deep.orchestrator.DeepResearchOrchestrator.run_sync",
        fake_run_sync,
    )
    result = CliRunner().invoke(app, ["research", "will the fed cut", "--no-clarify"])
    assert result.exit_code == 0
    assert "THE ANSWER" in result.stdout
    assert "https://u" in result.stdout
```

**Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_deep_research_cli.py -v`
Expected: FAIL — no `research` command.

**Step 3: Implement**

Add to `src/castelino/orchestrator/cli.py` (follow the existing `@app.command()` style; import inside the function to keep CLI startup light):

```python
@app.command()
def research(
    query: str = typer.Argument(..., help="Your research question."),
    no_clarify: bool = typer.Option(False, "--no-clarify", help="Skip clarifying questions; auto-assume context."),
):
    """Run the deep-research engine on a query and print a cited report."""
    from rich import print as rprint
    from castelino.agents.research.deep.orchestrator import DeepResearchOrchestrator

    orch = DeepResearchOrchestrator()

    if no_clarify:
        sess = orch.run_sync(query)
    else:
        sess = orch.start(query)
        if sess.clarifying_questions:
            rprint(f"[bold]Reworded:[/bold] {sess.reworded_query}\n")
            answers = {}
            for q in sess.clarifying_questions:
                ans = typer.prompt(f"❓ {q.question}")
                answers[q.question] = ans
            sess = orch.run_first_round(sess.id, answers=answers)
        else:
            sess = orch.run_first_round(sess.id, answers={})
        if sess.status.value != "failed":
            sess = orch.finish(sess.id)

    if sess.status.value == "failed":
        rprint(f"[red]Research failed:[/red] {sess.error}")
        raise typer.Exit(code=1)

    rep = sess.report
    rprint(f"\n[bold green]Answer[/bold green] (confidence {rep.confidence}):\n")
    rprint(rep.exec_summary)
    if rep.caveats:
        rprint("\n[bold]Caveats:[/bold]")
        for c in rep.caveats:
            rprint(f"  • {c}")
    rprint("\n[bold]Sources:[/bold]")
    for s in rep.sources:
        rprint(f"  • {s.title or s.url} — {s.url}")
    rprint(f"\n[dim]Session {sess.id} saved.[/dim]")
```

**Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_deep_research_cli.py -v`
Then smoke-test help: `uv run castelino research --help`
Expected: test PASS; help shows the command.

**Step 5: Commit**

```bash
git add src/castelino/orchestrator/cli.py tests/test_deep_research_cli.py
git commit -m "feat(deep-research): castelino research CLI command"
```

---

## Task 16: Dashboard endpoints

A new router module (don't overload the existing `research.py`, which serves OpenBB charts). Research runs in a FastAPI `BackgroundTasks` job; the client polls.

**Files:**
- Create: `src/castelino/dashboard/endpoints/deep_research.py`
- Modify: `src/castelino/dashboard/main.py:51-62` (import + `include_router`)
- Test: `tests/test_deep_research_endpoints.py` (FastAPI `TestClient`)

**Step 1: Write the failing test**

```python
# tests/test_deep_research_endpoints.py
import pytest
from fastapi.testclient import TestClient

from castelino.dashboard.main import app
from castelino.agents.base import FakeLLMClient, set_llm_client
from castelino.agents.research.deep.models import ClarifierResult, ClarificationQuestion
import castelino.dashboard.endpoints.deep_research as dr


@pytest.fixture(autouse=True)
def _reset_llm(tmp_path, monkeypatch):
    # point the store at a temp dir so tests don't write into data/research
    monkeypatch.setattr(dr, "_store_root", tmp_path, raising=False)
    yield
    set_llm_client(None)


def test_start_returns_questions():
    llm = FakeLLMClient()
    llm.register("ClarifierResult", lambda s, u: ClarifierResult(
        reworded_query="Q?", clarifying_questions=[ClarificationQuestion(question="Scope?")]))
    set_llm_client(llm)
    client = TestClient(app)
    r = client.post("/research/start", json={"query": "will the fed cut"})
    assert r.status_code == 200
    body = r.json()
    assert body["reworded_query"] == "Q?"
    assert body["clarifying_questions"][0]["question"] == "Scope?"
    assert "session_id" in body
```

**Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_deep_research_endpoints.py -v`
Expected: FAIL — 404 (route not registered).

**Step 3: Implement the router**

```python
# src/castelino/dashboard/endpoints/deep_research.py
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from castelino.agents.research.deep.orchestrator import DeepResearchOrchestrator
from castelino.agents.research.deep.store import ResearchStore

router = APIRouter()

# Overridable in tests.
_store_root = None


def _orch() -> DeepResearchOrchestrator:
    store = ResearchStore(root=_store_root) if _store_root else ResearchStore()
    return DeepResearchOrchestrator(store=store)


class StartRequest(BaseModel):
    query: str


class AnswersRequest(BaseModel):
    answers: dict[str, str] = {}


@router.post("/research/start")
def research_start(req: StartRequest):
    sess = _orch().start(req.query)
    return {
        "session_id": sess.id,
        "reworded_query": sess.reworded_query,
        "clarifying_questions": [q.model_dump() for q in sess.clarifying_questions],
        "status": sess.status.value,
    }


def _run_research_job(session_id: str, answers: dict):
    orch = _orch()
    sess = orch.run_first_round(session_id, answers=answers)
    if sess.status.value != "failed":
        orch.finish(session_id)


@router.post("/research/{session_id}/answers")
def research_answers(session_id: str, req: AnswersRequest, bg: BackgroundTasks):
    orch = _orch()
    sess = orch.store.load(session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="unknown session")
    bg.add_task(_run_research_job, session_id, req.answers)
    return {"session_id": session_id, "status": "researching"}


@router.get("/research/{session_id}")
def research_get(session_id: str):
    sess = _orch().store.load(session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="unknown session")
    return sess.model_dump(mode="json")


@router.get("/research")
def research_list():
    return [
        {"id": s.id, "original_query": s.original_query, "status": s.status.value,
         "updated_at": s.updated_at.isoformat()}
        for s in _orch().store.list()
    ]
```

**Step 4: Register the router** in `src/castelino/dashboard/main.py`:

Change the import line (~51):
```python
from castelino.dashboard.endpoints import agents, approvals, deep_research, macro, portfolio, research, risk  # noqa: E402
```
Add after the other `include_router` calls (~62):
```python
app.include_router(deep_research.router)
```

> ⚠️ Route-ordering check: the existing `research.py` router defines `/ta_chart`, `/screener`, etc. — no collision with `/research/*`. But confirm no other router defines a bare `/research` GET. If FastAPI warns about duplicate paths, rename this router's prefix to `/deep_research` and update the frontend calls accordingly.

**Step 5: Run to verify it passes & commit**

Run: `uv run pytest tests/test_deep_research_endpoints.py -v`
Expected: PASS

```bash
git add src/castelino/dashboard/endpoints/deep_research.py src/castelino/dashboard/main.py tests/test_deep_research_endpoints.py
git commit -m "feat(deep-research): dashboard endpoints (start/answers/get/list)"
```

---

## Task 17: Frontend — Deep Research page

A React page that drives the session: submit query → render clarifying questions → submit answers → poll until COMPLETE → render report. Follows the existing page/`@/api` conventions (TanStack Query is already a dep).

**Files:**
- Create: `frontend/src/pages/DeepResearchPage.tsx`
- Modify: `frontend/src/App.tsx` (add a `<Route>`)
- Modify: `frontend/src/components/layout/AppShell.tsx` (add a nav link — inspect the file first for the exact nav structure)

**Step 1: Implement the page** (no unit test — verified by manual smoke test; keep logic thin)

```tsx
// frontend/src/pages/DeepResearchPage.tsx
import { useState } from "react";

type ClarQ = { question: string; why?: string };
type Source = { title: string; url: string; snippet?: string };
type Report = {
  exec_summary: string; confidence: number;
  caveats: string[]; sources: Source[]; gaps_remaining: string[];
};

export default function DeepResearchPage() {
  const [query, setQuery] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [reworded, setReworded] = useState("");
  const [questions, setQuestions] = useState<ClarQ[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<string>("");
  const [report, setReport] = useState<Report | null>(null);

  async function start() {
    setStatus("clarifying");
    const r = await fetch("/api/research/start", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    const b = await r.json();
    setSessionId(b.session_id); setReworded(b.reworded_query);
    setQuestions(b.clarifying_questions); setStatus("awaiting_answers");
  }

  async function submitAnswers() {
    if (!sessionId) return;
    setStatus("researching");
    await fetch(`/api/research/${sessionId}/answers`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answers }),
    });
    poll(sessionId);
  }

  function poll(id: string) {
    const iv = setInterval(async () => {
      const r = await fetch(`/api/research/${id}`);
      const s = await r.json();
      setStatus(s.status);
      if (s.status === "complete") { setReport(s.report); clearInterval(iv); }
      if (s.status === "failed") { clearInterval(iv); }
    }, 2000);
  }

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-4">
      <h1 className="text-2xl font-semibold">Deep Research</h1>
      <textarea className="w-full border rounded p-2" rows={3}
        value={query} onChange={(e) => setQuery(e.target.value)}
        placeholder="Ask a research question…" />
      <button className="px-4 py-2 rounded bg-blue-600 text-white" onClick={start}>
        Start
      </button>

      {reworded && <p className="text-sm text-gray-500">Reworded: {reworded}</p>}

      {status === "awaiting_answers" && (
        <div className="space-y-3">
          {questions.map((q) => (
            <div key={q.question}>
              <label className="block text-sm font-medium">{q.question}</label>
              {q.why && <p className="text-xs text-gray-400">{q.why}</p>}
              <input className="w-full border rounded p-1"
                onChange={(e) => setAnswers({ ...answers, [q.question]: e.target.value })} />
            </div>
          ))}
          <button className="px-4 py-2 rounded bg-green-600 text-white" onClick={submitAnswers}>
            Research
          </button>
        </div>
      )}

      {(status === "researching" || status === "synthesizing") &&
        <p className="animate-pulse">Researching… ({status})</p>}

      {report && (
        <div className="space-y-3">
          <h2 className="text-xl font-semibold">Answer</h2>
          <p className="whitespace-pre-wrap">{report.exec_summary}</p>
          {report.caveats?.length > 0 && (
            <div><h3 className="font-medium">Caveats</h3>
              <ul className="list-disc ml-5">{report.caveats.map((c) => <li key={c}>{c}</li>)}</ul></div>
          )}
          <div><h3 className="font-medium">Sources</h3>
            <ul className="list-disc ml-5">
              {report.sources.map((s) => (
                <li key={s.url}><a className="text-blue-600 underline" href={s.url} target="_blank" rel="noreferrer">{s.title || s.url}</a></li>
              ))}
            </ul></div>
        </div>
      )}
    </div>
  );
}
```

**Step 2: Wire the route** in `frontend/src/App.tsx`:
```tsx
import DeepResearchPage from "./pages/DeepResearchPage";
// inside <Routes>:
<Route path="/research" element={<DeepResearchPage />} />
```
Add a nav link in `AppShell.tsx` (match the existing link pattern — read the file first).

**Step 3: Verify build**

Run: `cd frontend && npm run build`
Expected: build succeeds (TypeScript clean).

**Step 4: Manual smoke test** (requires `OPENAI_API_KEY` + `PERPLEXITY_API_KEY` in `.env`)
- `uv run castelino serve` (backend :7779)
- `cd frontend && npm run dev -- --port 3000`
- Open http://localhost:3000/research, run a query end-to-end.

**Step 5: Commit**

```bash
git add frontend/src/pages/DeepResearchPage.tsx frontend/src/App.tsx frontend/src/components/layout/AppShell.tsx
git commit -m "feat(deep-research): dashboard Deep Research page"
```

---

## Task 18: Full-suite green + docs + completion summary

**Step 1: Run the entire backend suite**

Run: `uv run pytest tests/ -q 2>&1 | tail -15`
Expected: all green (or only pre-existing unrelated failures noted in Task 0).

**Step 2: Lint**

Run: `uv run ruff check src/castelino/agents/research/deep/ src/castelino/dashboard/endpoints/deep_research.py`
Fix any findings, re-run.

**Step 3: Update project docs**

Append a `## Completed Work` entry to `CLAUDE.md` summarizing: what was built (deep-research engine), key decisions (asyncio orchestrator, Sonar backend, tiered models, hard caps), and the new CLI/endpoints. Append the gotchas to `learnings.md`.

**Step 4: Commit**

```bash
git add CLAUDE.md learnings.md short_term_memory.md
git commit -m "docs(deep-research): completion summary + learnings"
```

**Step 5: Finish the branch**
Use the superpowers:finishing-a-development-branch skill to decide merge/PR. Any push MUST go through the `/gitpush` skill (HARD RULE — secret scan).

---

## Verification checklist (whole feature)

- [ ] `uv run pytest tests/ -k deep_research -v` → all green
- [ ] `uv run castelino research "..." --no-clarify` prints a cited answer (with keys set)
- [ ] Interactive `uv run castelino research "..."` asks questions, then answers
- [ ] `POST /research/start` → questions; `POST /research/{id}/answers` → backgrounds; `GET /research/{id}` polls to `complete`
- [ ] Sub-question count never exceeds `max_sub_questions`; Sonar calls never exceed `max_sonar_calls`
- [ ] Reflection can trigger exactly one extra round (capped at `max_rounds`)
- [ ] All-sub-agents-fail → session `FAILED`, no crash
- [ ] Reports land in `data/research/<id>.json` (atomic write)
- [ ] No real network in unit tests (FakeLLMClient + FakeSonarClient); live tests marked `@pytest.mark.live`

## Risks & notes

- **Model IDs:** live tiers (`gpt-5.5`/`gpt-5.4-mini`) aren't real OpenAI IDs — runs will fail against the live API until fixed. Test with real IDs (e.g. `gpt-4o`/`gpt-4o-mini`) via a local `config.yaml` override before demoing.
- **Perplexity `citations` field:** verify the SDK surfaces `resp.citations`. If a newer Perplexity API nests citations differently, adjust `PerplexitySonarClient.search`. The unit tests don't depend on this (FakeSonarClient), so it's a live-path concern only.
- **`StructuredAgent.tier` as property:** if mypy/ruff complains about overriding a class attribute with a property, fall back to `tier = "reasoning"` and read the configured tier inside `__call__`.
- **Background job durability:** FastAPI `BackgroundTasks` dies if the server restarts mid-run. Acceptable for v1 (analyst tool); a future version could use a task queue.
