"""Single source of truth for runtime configuration.

Loads `config.yaml` once and exposes a typed `Settings` object. Reads OpenAI
key from the environment (preferring a project-local `.env`).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")  # noop if missing


class ModelsCfg(BaseModel):
    reasoning: str
    fast: str
    significance: str


class OpenAICfg(BaseModel):
    request_timeout_s: int = 60
    max_retries: int = 3
    max_output_tokens: int = 2048


class PathsCfg(BaseModel):
    data_dir: str
    reports_dir: str
    cache_dir: str

    def resolve(self, root: Path) -> ResolvedPaths:
        return ResolvedPaths(
            data=root / self.data_dir,
            reports=root / self.reports_dir,
            cache=root / self.cache_dir,
        )


class ResolvedPaths(BaseModel):
    data: Path
    reports: Path
    cache: Path

    model_config = {"arbitrary_types_allowed": True}


class FredReleaseCfg(BaseModel):
    name: str
    impact: str
    asset_classes: list[str]


class FredCfg(BaseModel):
    releases: dict[int, FredReleaseCfg]
    cache_ttl_hours: int = 24


class WebSearchCfg(BaseModel):
    """OpenAI Responses-API web search (data/web_search.py)."""

    cache_ttl_hours: int = 12
    model: str = "gpt-5.4-mini"
    regions: list[str] = Field(
        default_factory=lambda: ["EU", "UK", "JP", "CN", "GLOBAL"],
    )


class OpenBBCfg(BaseModel):
    preferred_provider: str = "yfinance"
    fallback_enabled: bool = True
    cache_ttl_minutes: int = 15


class UpdateAgentCfg(BaseModel):
    enabled: bool = True
    orchestrator_model: str = "gpt-6-sol"
    editor_model: str = "gpt-6-sol"
    agent_model: str = "gpt-6-luna"  # Macro / News / Alt pickers
    search_model: str = "gpt-6-luna"  # web_search calls by News / Alt
    # ponytail: no separate search-call cap; max_rounds bounds it at 2 * (1 + max_rounds) = 6
    max_rounds: int = 2  # orchestrator follow-up rounds
    max_findings_per_agent: int = 6
    items: int = 5
    max_guard_retries: int = 1
    max_output_tokens: int = 16000  # reasoning tokens share this budget
    short_term_notes: int = 5
    long_term_notes: int = 20
    long_term_refresh_days: int = 7
    data_dir: str = "data/update_agent"
    updates_dir: str = "data/updates"


class ThemesCfg(BaseModel):
    """Theme Charts (agents/themes.py): the #1 macro theme, charted at 08:00 ET on weekdays."""

    picker_model: str = "gpt-6-sol"
    search_model: str = "gpt-6-luna"
    explainer_model: str = "gpt-6-luna"  # the X thread's line + the Substack commentary per chart
    max_charts: int = 6
    min_charts: int = 5  # fewer on try 1 → one retry told why; the retry publishes what passed
    memory_runs: int = 6  # recent themes the picker sees, so it can say "still #1"
    max_output_tokens: int = 16000  # reasoning tokens share this budget
    data_dir: str = "data/themes"


class XScoutCfg(BaseModel):
    """X Scout (x_scout.py): one macro or AI finding a run, posted to X with a chart."""

    search_model: str = "gpt-6-luna"
    scout_model: str = "gpt-6-sol"  # judging "worth a post" is the hard part
    writer_model: str = "gpt-6-luna"


class CoverCfg(BaseModel):
    """Cover art for the Morning Note and Weekly Deep Dive drafts (cover.py)."""

    model: str = "gpt-image-2"  # takes any size divisible by 16, so 16:9 is drawn, not cropped
    size: str = "1536x864"
    quality: str = "high"


class ModelRefitCfg(BaseModel):
    gate_tolerance: float = 0.02  # max Brier worsening a refit may show and still be promoted


class SectorSentimentCfg(BaseModel):
    """Sector sentiment indicator (signals/sector_sentiment.py)."""

    enabled: bool = True
    euphoric_threshold: float = 0.3
    fearful_threshold: float = -0.3
    # Per-sector explainer verdict rule (signals/sector_sentiment.py::explain_concentration)
    stock_specific_top_share: float = 0.5  # top contributor >= this share -> stock_specific
    sector_wide_min_agree: int = 7  # >= this many of 10 share the sign -> sector_wide
    universe_cache_hours: int = 24
    fundamentals_cache_hours: int = 24
    top_n_per_sector: int = 10
    min_history_for_zscore: int = 20
    # A full refresh is ~110 yfinance lookups; refresh() self-throttles to this interval.
    refresh_interval_hours: int = 24


class DeepResearchCfg(BaseModel):
    """General Deep Research (agents/research/deep/, /admin → Research): any topic, up to 8 tool-using
    research agents, Claude writes the points, the editor desk revises one point at a time."""

    enabled: bool = True
    data_dir: str = "data/research"
    clarifier_model: str = "gpt-6-sol"
    lead_model: str = "gpt-6-sol"
    critic_model: str = "gpt-6-sol"
    agent_model: str = "deepseek/deepseek-v4.1-flash-1017"  # OpenRouter; trade/loop.py
    agent_fallback_model: str = "gpt-6-luna"
    search_model: str = "gpt-6-luna"  # web_search inside the tool
    writer_model: str = "claude-opus-5-5"
    writer_effort: str = "high"
    writer_max_tokens: int = 32000
    revise_model: str = "anthropic/claude-haiku-5.5"
    revise_fallback_model: str = "anthropic/claude-sonnet-5.5"
    revise_openai_model: str = "gpt-6-sol"  # runs when OPENROUTER_API_KEY is unset
    compact_model: str = "gpt-6-luna"
    clarify_max_questions: int = 3
    max_agents: int = 8
    max_gap_agents: int = 4
    max_tool_calls: int = 12
    gap_rounds: int = 1
    agent_concurrency: int = 4
    session_concurrency: int = 2
    answer_tool_calls: int = 4
    x_posts_per_call: int = 10
    x_posts_per_report: int = 100
    keep_full_days: int = 14
    cost_cap_usd: float = 8.0
    max_charts: int = 4  # chart_resolver.py
    chart_lookback_days_default: int = 365


class DeepDiveCfg(BaseModel):
    """Weekly Deep Dive (agents/weekly/): Lead + tool-using sub-agents + Claude Deep Editor."""

    enabled: bool = True
    lead_model: str = "gpt-6-sol"
    agent_model: str = "gpt-6-luna"  # sub-agent tool loops
    search_model: str = "gpt-6-luna"  # their web_search calls
    editor_model: str = "claude-opus-5-5"
    editor_effort: str = "high"  # Opus 5.5 defaults to medium; the grill needs high
    editor_max_tokens: int = 64000  # 10-12 trend sections in one structured reply
    min_trends: int = 10  # a weekly covers the whole week: 10-12 trends, 2-3 per desk
    max_trends: int = 12
    max_agents: int = 5
    max_tool_calls: int = 16  # per sub-agent research run (a desk covers 2-3 trends)
    max_answer_tool_calls: int = 4  # extra calls per grill answer
    max_findings_per_agent: int = 6
    max_grill_rounds: int = 2
    max_guard_retries: int = 1
    min_notes: int = 3  # Morning Notes a week needs before a deep dive runs
    max_output_tokens: int = 16000  # OpenAI calls; reasoning tokens share this budget
    data_dir: str = "data/deep"


class TradeLabCfg(BaseModel):
    """Trade Lab (agents/trade/): idea → bull/bear debate → talks → desks → charts → editor → Substack draft."""

    data_dir: str = "data/trades"
    # OpenRouter ids contain a "/". V4.1 Flash 1017 replaced V4 Pro on 2026-10-17: it framed the India idea
    # well and finished the debate, where V4 Pro failed a rebuttal on the number check
    framer_model: str = "deepseek/deepseek-v4.1-flash-1017"
    debate_model: str = "deepseek/deepseek-v4.1-flash-1017"  # bull, bear, moderator
    # talk answers, Talk 2 edits, "another idea": Haiku passed 4 of 4 test edits on the India report, DeepSeek
    # V4 Pro 2 of 4 (2026-10-16); V4.1 Flash 1017 passed 4 of 4 but ran 4x slower and cut text it was told to
    # keep (2026-10-17). Edits that fail the number check twice go to fallback_talk_model
    talk_model: str = "anthropic/claude-haiku-5.5"
    orchestrator_model: str = "gpt-6-sol"
    desk_model: str = "gpt-6-luna"
    chart_model: str = "gpt-6-luna"
    search_model: str = "gpt-6-luna"
    decide_model: str = "gpt-6-luna"  # OpenAI Decisions API
    editor_model: str = "claude-opus-5-5"
    editor_effort: str = "high"
    editor_max_tokens: int = 32000
    fallback_debate_model: str = "gpt-6-sol"  # used when OpenRouter is unset or failing
    fallback_talk_model: str = "anthropic/claude-sonnet-5.5"
    opening_calls: int = 8
    rebuttal_calls: int = 2
    news_calls: int = 12
    technical_calls: int = 16
    talk_research_calls: int = 4  # a Talk 2 question that needs new facts
    breadth_min_domains: int = 6
    breadth_extra_calls: int = 3
    cost_cap_usd: float = 5.0
    concurrency: int = 2
    decide_threshold: float = 0.5
    max_output_tokens: int = 16000
    openrouter_provider: dict = {
        "data_collection": "deny",
        "require_parameters": True,
        "sort": "price",
    }


class ChartDeskCfg(BaseModel):
    """Admin → Charts (agents/chart_desk.py): only for talking to the chart agent directly; never
    changes another workflow's model. OpenRouter ids contain a "/"."""

    data_dir: str = "data/chart_desk"
    chat_model: str = "gpt-6-luna"
    compare_models: list[str] = [
        "gpt-6-luna",  # Trade Lab's chart model, for reference
        "moonshotai/kimi-k3",
        "deepseek/deepseek-v4-pro",
        "qwen/qwen3.8-max-0902",
        "z-ai/glm-5.3",
        "mistralai/mistral-large-4-0",
        "deepseek/deepseek-v4.1-flash",
    ]
    compare_default: int = 5  # the first N of compare_models start ticked


# ────────────────────────── figure_deviation (Wave 1) ────────────────────────
# Generalises `speech.speakers` into a multi-source, multi-lexicon engine.
# Existing Fed speakers are ported here in Wave 1. Trump (X API) lands in
# Wave 5. The legacy `speech` config above is retained while the migration
# happens — the two coexist until Wave 2.


class AdoptionCfg(BaseModel):
    enabled: bool = True
    data_dir: str = "data/adoption"
    top_n: int = 100  # companies per size bucket
    sec_user_agent: str = ""  # SEC requires a contact string, e.g. "ARC Research you@example.com"
    hire_smoothing_periods: int = 7  # ~90 days of bi-weekly snapshots
    thin_cell_below: int = 5  # sector x bucket cells with fewer companies are flagged
    max_passages: int = 40  # AI passages sent to the extractor per filing
    passage_window_chars: int = 300  # context kept around each AI keyword hit
    request_interval_s: float = 0.12  # SEC allows 10 requests/second
    # Recipe Writer (adoption/recipe_agent.py): writes job-board recipes for custom careers sites.
    recipe_model: str = "gpt-6-astra"
    recipe_max_steps: int = 15  # model turns per company
    recipe_max_usd: float = 3.0  # hard spend cap per company


class Settings(BaseModel):
    models: ModelsCfg
    openai: OpenAICfg
    fred: FredCfg
    openbb: OpenBBCfg = OpenBBCfg()
    web_search: WebSearchCfg = WebSearchCfg()
    deep_research: DeepResearchCfg = DeepResearchCfg()
    deep_dive: DeepDiveCfg = DeepDiveCfg()
    trade_lab: TradeLabCfg = TradeLabCfg()
    chart_desk: ChartDeskCfg = ChartDeskCfg()
    update_agent: UpdateAgentCfg = UpdateAgentCfg()
    themes: ThemesCfg = ThemesCfg()
    x_scout: XScoutCfg = XScoutCfg()
    cover: CoverCfg = CoverCfg()
    model_refit: ModelRefitCfg = ModelRefitCfg()
    sector_sentiment: SectorSentimentCfg = SectorSentimentCfg()
    adoption: AdoptionCfg = AdoptionCfg()
    paths: PathsCfg
    root: Path

    model_config = {"arbitrary_types_allowed": True}

    @property
    def resolved_paths(self) -> ResolvedPaths:
        return self.paths.resolve(self.root)

    @property
    def openai_api_key(self) -> str:
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not key:
            raise RuntimeError("OPENAI_API_KEY is not set. Add it to .env or export it.")
        return key

    @property
    def anthropic_api_key(self) -> str:
        key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set. Add it to .env or export it.")
        return key

    @property
    def fred_api_key(self) -> str | None:
        """FRED API key. Optional — adapter falls back to keyless CSV if unset."""
        key = os.environ.get("FRED_API_KEY", "").strip()
        return key or None

    @property
    def openbb_pat(self) -> str | None:
        """OpenBB Personal Access Token. Optional — adapter disabled if unset."""
        key = os.environ.get("OPENBB_PAT", "").strip()
        return key or None


@lru_cache(maxsize=1)
def load_settings(config_path: Path | None = None) -> Settings:
    cfg_path = config_path or (ROOT / "config.yaml")
    with cfg_path.open("r") as f:
        raw = yaml.safe_load(f)
    raw["root"] = ROOT
    s = Settings.model_validate(raw)
    # lets the SEC contact email live in the environment instead of config.yaml
    if ua := os.environ.get("SEC_USER_AGENT", "").strip():
        s.adoption.sec_user_agent = ua
    return s


def get_settings() -> Settings:
    """Convenience accessor used across modules."""
    return load_settings()
