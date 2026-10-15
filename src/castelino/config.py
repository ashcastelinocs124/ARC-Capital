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
    max_charts: int = 6
    min_charts: int = 5  # fewer on try 1 → one retry told why; the retry publishes what passed
    memory_runs: int = 6  # recent themes the picker sees, so it can say "still #1"
    max_output_tokens: int = 16000  # reasoning tokens share this budget
    data_dir: str = "data/themes"


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
    enabled: bool = True
    max_sub_questions: int = 6  # hard cap on decomposition fan-out
    max_rounds: int = 2  # reflection rounds, incl. first
    max_sonar_calls: int = 15  # global web-search budget per report (name kept: stored in reports)
    concurrency: int = 3  # asyncio semaphore over sub-agents
    clarify_max_questions: int = 3  # cap on clarifying questions
    reasoning_tier: str = "reasoning"  # tier for clarifier/lead/synthesizer
    fast_tier: str = "fast"  # tier for parallel sub-agents
    reports_dir: str = "data/research"
    # Per-call output ceiling for deep-research LLM calls. MUST be generous:
    # the gpt-5.x reasoning models spend hidden reasoning tokens out of this
    # SAME budget, so a small cap (e.g. the global 2048) gets fully consumed by
    # reasoning and leaves nothing for the structured output → parse fails with
    # "length limit reached". Billing is per token actually used, so a high
    # ceiling costs nothing extra; it only prevents the truncation failure.
    max_output_tokens: int = 16000
    # Charts: hard cap on charts per report (bounds OpenBB calls) + default window.
    max_charts: int = 4
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
    update_agent: UpdateAgentCfg = UpdateAgentCfg()
    themes: ThemesCfg = ThemesCfg()
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
