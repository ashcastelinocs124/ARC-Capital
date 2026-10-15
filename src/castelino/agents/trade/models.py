"""Trade Lab's saved shapes. LLM outputs are closed schemas (no defaults) so strict structured output works;
records the app builds (TradeIdea, Round, Job, ChartOption) carry defaults."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from castelino.agents.update.models import Fact

SECTIONS = ("intro", "bull", "bear", "question", "technical", "read", "watch")
BODY = (
    "bull",
    "bear",
    "question",
    "technical",
    "read",
)  # the report's five body sections, in order
Section = Literal["intro", "bull", "bear", "question", "technical", "read", "watch"]
Status = Literal[
    "framing",
    "debating",
    "awaiting_view",
    "researching",
    "awaiting_charts",
    "writing",
    "draft_ready",
]


class StepError(RuntimeError):
    """A step that can't finish; its message is shown to the user beside a Retry button."""


# ── LLM outputs (closed) ─────────────────────────────────────────────────────
class StandIn(BaseModel):
    ticker: str
    role: Literal["subject", "benchmark"]
    label: str


class Frame(BaseModel):
    title: str
    thesis: str
    stand_ins: list[StandIn]
    horizon_months: int
    prove_wrong: list[str]
    why_now_query: str


class TurnDraft(BaseModel):
    text: str
    fact_ids: list[str]


class Settled(BaseModel):
    point: str
    fact_ids: list[str]


class OpenQ(BaseModel):
    question: str
    why: str


class Moderation(BaseModel):
    settled: list[Settled]
    open: list[OpenQ]


class Brief(BaseModel):
    desk: Literal["news_1", "news_2", "technical"]
    title: str
    brief: str
    must_answer: list[str]
    item_ids: list[str]  # research-list items this desk answers
    tickers: list[str]  # technical desk only; [] for news desks


class Briefs(BaseModel):
    briefs: list[Brief]


class DeskFinding(BaseModel):
    claim: str
    fact_ids: list[str]


class DeskReport(BaseModel):
    findings: list[DeskFinding]
    summary: str
    unanswered: list[str]


class ChartSpec(BaseModel):
    section: Section
    form: str
    series: list[str]  # "yahoo:INDA" / "fred:DGS10"; the first is the subject
    window_days: int
    threshold: float | None
    title: str
    why: str
    agent_pick: bool


class SpecList(BaseModel):
    specs: list[ChartSpec]


class ReportSection(BaseModel):
    key: Literal["bull", "bear", "question", "technical", "read"]
    heading: str
    paragraphs: list[str]
    fact_ids: list[str]


class Report(BaseModel):
    title: str
    subtitle: str
    introduction: list[str]  # exactly 2 paragraphs
    takeaways: list[str]  # exactly 3
    sections: list[ReportSection]  # BODY order
    what_to_watch: str
    changes: list[str]  # round 2+: what the rewrite changed from the Substack draft; [] in round 1


# ── records the app builds ───────────────────────────────────────────────────
class Turn(BaseModel):
    side: Literal["bull", "bear"]
    round: int  # 0 opening, 1 and 2 rebuttals
    text: str
    fact_ids: list[str]


class ResearchItem(BaseModel):
    id: str
    kind: Literal["claim", "question", "moderator"]
    text: str
    round: int
    removed: bool = False


class TalkMessage(BaseModel):
    talk: Literal[1, 2]
    role: Literal["user", "agent"]
    to: str = "ARC"
    text: str
    fact_ids: list[str] = Field(default_factory=list)
    decision: dict[str, float] | None = None  # e.g. {"research": 0.93}
    action: str = ""  # "research", "edit:bear", or ""
    at: str


class DeskRun(BaseModel):
    desk: str
    brief: Brief
    report: DeskReport | None = None
    calls: int = 0
    domains: list[str] = Field(default_factory=list)
    error: str | None = None


class ChartOption(BaseModel):
    id: str
    spec: ChartSpec
    file: str | None = None  # PNG name in charts/; None when it failed to draw
    error: str | None = None
    fact_ids: list[str] = Field(default_factory=list)  # the C facts computed for this chart
    chosen: bool = False


class Round(BaseModel):
    n: int
    briefs: list[Brief] = Field(default_factory=list)
    desks: list[DeskRun] = Field(default_factory=list)
    options: list[ChartOption] = Field(default_factory=list)


class Job(BaseModel):
    step: str
    state: Literal["queued", "running", "done", "failed", "interrupted"]
    message: str = ""
    at: str


class TradeIdea(BaseModel):
    id: str
    idea: str
    created_at: str
    updated_at: str
    status: Status = "framing"
    round: int = 1
    frame: Frame | None = None
    debate_attempt: int = 1
    turns: list[Turn] = Field(default_factory=list)
    turns_history: list[list[Turn]] = Field(
        default_factory=list
    )  # earlier debates, kept on a re-run
    moderation: Moderation | None = None
    talk: list[TalkMessage] = Field(default_factory=list)
    research: list[ResearchItem] = Field(default_factory=list)
    rounds: list[Round] = Field(default_factory=list)
    report: Report | None = None
    facts: list[Fact] = Field(default_factory=list)
    cost_usd: float = 0.0
    job: Job | None = None
    substack: dict | None = None  # {"draft_id": int, "url": str}
    fallbacks: list[str] = Field(default_factory=list)

    def current(self) -> Round:
        """This round's record, created on first use."""
        for r in self.rounds:
            if r.n == self.round:
                return r
        r = Round(n=self.round)
        self.rounds.append(r)
        return r

    def fact_map(self) -> dict[str, Fact]:
        return {f.id: f for f in self.facts}
