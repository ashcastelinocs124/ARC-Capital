"""Weekly Deep Dive data models. LLM-output schemas are closed (no defaults), as in update/models.py."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from castelino.agents.update.models import Fact, SeriesRef

ToolName = Literal["fred_series", "yahoo_prices", "bls_series", "polymarket_odds", "web_search"]


class Trend(BaseModel):
    title: str
    why: str


class SubAgentSpec(BaseModel):
    name: str
    description: str
    goal: str
    tools: list[ToolName]
    related: list[str]
    trends: list[str]  # titles of the Lead's trends this desk owns (2-3)


class DeepPlan(BaseModel):
    trends: list[Trend]
    agents: list[SubAgentSpec]


class FindingDraft(BaseModel):
    claim: str
    figure: float | None
    unit: Literal["%", "bp", "pp", "level", ""]
    fact_ids: list[str]


class FindingDrafts(BaseModel):
    findings: list[FindingDraft]


class AnswerDraft(BaseModel):
    answer: str
    fact_ids: list[str]


class WeeklyFinding(BaseModel):
    id: str
    agent: str  # the desk's name, e.g. "Rates desk"
    claim: str
    figure: float | None = None
    unit: str = ""
    provenance: Literal["data", "reported"]
    series: SeriesRef | None = None
    source_title: str
    source_url: str
    fact_ids: list[str]


class BoardPost(BaseModel):
    agent: str
    note: str
    fact_ids: list[str]


class AgentRun(BaseModel):
    agent: str
    facts: list[Fact]
    findings: list[WeeklyFinding]
    tool_calls: int


class GrillQuestion(BaseModel):
    agent: str
    finding_id: str
    question: str


class Grill(BaseModel):
    done: bool
    questions: list[GrillQuestion]


class GrillExchange(BaseModel):
    agent: str
    finding_id: str
    question: str
    answer: str
    fact_ids: list[str] = Field(default_factory=list)
    round: int = 1


class Challenge(BaseModel):
    question: str
    answer: str
    verdict: str


class ExhibitPick(BaseModel):
    fact_id: str
    window_days: int


class TrendSection(BaseModel):
    title: str
    agent: str
    paragraphs: list[str]
    fact_ids: list[str]
    exhibits: list[ExhibitPick]
    challenges: list[Challenge]


class Bullet(BaseModel):
    lead: str
    body: str
    fact_ids: list[str]


class WeeklyReport(BaseModel):
    title: str
    subtitle: str
    bullets: list[Bullet]
    watch: str
    sections: list[TrendSection]


class ScoreRow(BaseModel):
    asset: str
    level: float
    unit: Literal["%", "level", "$"]
    change_unit: Literal["%", "bp"]
    w1: float | None = None
    m1: float | None = None
    m3: float | None = None
    ytd: float | None = None


class RegimeRead(BaseModel):
    pulse: float | None = None  # P(expansion), percent
    pressure: float | None = None  # P(CPI accelerates), percent


class RunCounts(BaseModel):
    notes: int = 0
    agents: int = 0
    data_pulls: int = 0
    board_posts: int = 0
    grill_rounds: int = 0
    figures_checked: int = 0
    exhibits: int = 0


class WeeklyExhibit(BaseModel):
    n: int
    section: int  # index into report.sections
    fact_id: str
    title: str
    subtitle: str
    file: str


class WeeklyRecord(BaseModel):
    version: Literal[1] = 1
    week: str
    start: str
    end: str
    generated_at: str
    plan: DeepPlan
    findings: list[WeeklyFinding]
    facts: list[Fact]
    board: list[BoardPost]
    grill_log: list[GrillExchange]
    report: WeeklyReport
    exhibits: list[WeeklyExhibit]
    scorecard: list[ScoreRow]
    regime: RegimeRead
    counts: RunCounts
    data_gaps: list[str]
    models: dict[str, str] = Field(default_factory=dict)  # lead / agents / editor ids, for page 1
