"""General Deep Research models: the session JSON (data/research/<id>.json) and the LLM outputs.

LLM-output models are closed (no defaults) for structured outputs. ChartSpec and ResolvedChart only read
reports written before point charts (2026-10-19); new charts are PointChart, on each point."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from castelino.agents.update.models import Fact
from castelino.agents.weekly.models import BoardPost


class StepError(RuntimeError):
    """A step that can't finish; its message is shown beside a Retry button."""


class Busy(RuntimeError):  # noqa: N818 - the API answers 409
    pass


# ── charts (unchanged) ───────────────────────────────────────────────────────
class ChartType(StrEnum):
    PRICE_HISTORY = "price_history"
    YIELD_CURVE = "yield_curve"
    ECON_INDICATOR = "econ_indicator"
    COMPARISON = "comparison"


class ChartSpec(BaseModel):
    """A chart the writer requests (no data, just the request)."""

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
    """A report-level chart from before point charts (the removed ChartResolver drew it)."""

    type: ChartType
    title: str
    rationale: str = ""
    series: list[ChartSeries] = Field(default_factory=list)
    y_label: str = ""
    source: str = "OpenBB"


# ── LLM outputs (closed) ─────────────────────────────────────────────────────
class ClarifyQuestion(BaseModel):
    question: str
    why: str


class Clarification(BaseModel):
    question: str  # the topic reworded as one research question
    questions: list[ClarifyQuestion]


class Brief(BaseModel):
    name: str
    angle: str
    brief: str


class Plan(BaseModel):
    briefs: list[Brief]


class Critique(BaseModel):
    done: bool
    gaps: list[str]


class FindingDraft(BaseModel):
    claim: str
    fact_ids: list[str]


class FindingDrafts(BaseModel):
    findings: list[FindingDraft]


class PointDraft(BaseModel):
    agent: str
    headline: str
    body: str
    fact_ids: list[str]


class ReportDraft(BaseModel):
    title: str
    subtitle: str
    points: list[PointDraft]
    caveats: list[str]


class MorePoints(BaseModel):
    """The writer's new points for an addition: only the new researchers' findings."""

    points: list[PointDraft]


class AnswerDraft(BaseModel):
    answer: str
    change: bool
    finding: str
    fact_ids: list[str]


class RevisedPoint(BaseModel):
    headline: str
    body: str
    fact_ids: list[str]


class Summary(BaseModel):
    text: str


ChartForm = Literal["bars", "line", "dumbbell", "stat"]
ChartUnit = Literal["%", "$", "bp", "pp", "level", ""]


class ChartValue(BaseModel):
    fact_id: str  # one of the point's cited facts; the guard checks value is one of its numbers
    label: str
    value: float


class PointChartDraft(BaseModel):
    point_id: str
    form: ChartForm
    title: str
    unit: ChartUnit
    values: list[ChartValue]


class ChartSet(BaseModel):
    charts: list[PointChartDraft]


# ── the session ──────────────────────────────────────────────────────────────
class Finding(BaseModel):
    id: str
    claim: str
    fact_ids: list[str]


class AgentRun(BaseModel):
    letter: str  # "A".."H", the gap round continues; also the agent's fact-id prefix
    round: int = 1
    brief: Brief
    model: str = ""
    tool_calls: int = 0
    x_posts: int = 0
    facts: list[Fact] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    transcript: list[dict] | None = None  # None after compaction
    summary: str | None = None  # set by compaction
    error: str | None = None


class PointChart(BaseModel):
    """A point's chart: data only, drawn by the Research tab. Every value comes from a cited fact."""

    form: ChartForm
    title: str
    unit: ChartUnit = ""
    values: list[ChartValue]
    fallback: bool = (
        False  # True: the chart agent's chart failed twice, so code made a big-number tile
    )


class Point(BaseModel):
    id: str
    agent: str  # owner letter
    headline: str  # the Key findings list is every point's headline, in order
    body: str
    fact_ids: list[str]
    version: int = 1
    chart: PointChart | None = None
    added: int | None = None  # the Addition that wrote it; None for the original report
    older: str = (
        ""  # its newest cited figure's year ("2025") or "undated", when older than guard.fresh_year
    )


class ResearchReport(BaseModel):
    title: str
    subtitle: str
    points: list[Point]
    caveats: list[str] = Field(default_factory=list)
    gaps_remaining: list[str] = Field(default_factory=list)
    chart_specs: list[ChartSpec] = Field(default_factory=list)  # reports from before point charts
    charts: list[ResolvedChart] = Field(default_factory=list)


class Proposal(BaseModel):
    n: int
    point_id: str
    agent: str
    text: str  # what you typed: a question or an edit, one box
    answer: str = ""
    base_version: int
    before: Point | None = None
    after: Point | None = None
    new_facts: list[Fact] = Field(default_factory=list)
    status: Literal["running", "pending", "answered", "approved", "rejected", "failed"] = "running"
    error: str = ""
    trail: list[str] = Field(default_factory=list)
    created_at: str
    decided_at: str | None = None


class Addition(BaseModel):
    """Angles you asked to add to a finished report: new agents research them in round 2 + n, the writer adds
    points from their findings only, and every existing point stays as it is."""

    n: int
    text: str
    round: int
    status: Literal["running", "done", "failed"] = "running"
    error: str = ""
    created_at: str


class SubstackDraft(BaseModel):
    """The report's Substack draft (publish.py): `sha` hashes the text last pushed, so a draft you edited on
    Substack is never overwritten; `note` says why the last push didn't update it."""

    draft_id: int | None = None
    url: str = ""
    sha: str = ""
    at: str = ""
    note: str = ""


class Job(BaseModel):
    step: str
    state: Literal["queued", "running", "done", "failed", "interrupted"]
    message: str = ""
    at: str


class ResearchSession(BaseModel):
    id: str
    topic: str
    question: str = ""
    clarifying_questions: list[ClarifyQuestion] = Field(default_factory=list)
    answers: dict[str, str] = Field(default_factory=dict)  # question text → answer; blanks dropped
    status: Literal["awaiting_answers", "researching", "writing", "complete"] = "awaiting_answers"
    job: Job | None = None
    agents: list[AgentRun] = Field(default_factory=list)
    board: list[BoardPost] = Field(default_factory=list)
    board_facts: dict[str, Fact] = Field(default_factory=dict)
    report: ResearchReport | None = None
    proposals: list[Proposal] = Field(default_factory=list)
    additions: list[Addition] = Field(default_factory=list)
    substack: SubstackDraft | None = None
    cost_usd: float = 0.0
    fallbacks: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str
    compacted_at: str | None = None

    def fact_map(self) -> dict[str, Fact]:
        out = dict(self.board_facts)
        for a in self.agents:
            out.update({f.id: f for f in a.facts})
        return out

    def agent(self, letter: str) -> AgentRun:
        for a in self.agents:
            if a.letter == letter:
                return a
        raise KeyError(f"agent {letter}")

    def point(self, point_id: str) -> Point:
        for p in self.report.points if self.report else []:
            if p.id == point_id:
                return p
        raise KeyError(f"point {point_id}")

    def proposal(self, n: int) -> Proposal:
        if 1 <= n <= len(self.proposals):
            return self.proposals[n - 1]
        raise KeyError(f"proposal {n}")
