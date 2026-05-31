"""Single source of truth for runtime configuration.

Loads `config.yaml` once and exposes a typed `Settings` object. Reads OpenAI
key from the environment (preferring a project-local `.env`).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")  # noop if missing


class FundCfg(BaseModel):
    name: str
    initial_nav: float
    base_currency: str = "USD"


class ModelsCfg(BaseModel):
    reasoning: str
    fast: str
    significance: str


class OpenAICfg(BaseModel):
    request_timeout_s: int = 60
    max_retries: int = 3
    max_output_tokens: int = 2048


class TriggersCfg(BaseModel):
    cron_fallback_hours: int = 24
    news_significance_min: float = 0.7
    news_log_min: float = 0.4
    rss_feeds: list[str] = Field(default_factory=list)


class RiskCfg(BaseModel):
    position_max_pct_nav: float
    asset_class_max_pct_gross: float
    drawdown_freeze_pct: float
    vix_circuit_breaker: float
    five_day_pnl_freeze_pct: float
    liquidity_min_adv_usd: float
    liquidity_max_pct_adv: float


class ResearchCfg(BaseModel):
    ta_lookback_days: int
    backtest_lookback_years: int
    risk_correlation_window: int


class CuratorCfg(BaseModel):
    cadence: str
    st_max_closed_trades: int
    st_max_hypothesis_days: int
    st_max_trigger_days: int
    st_max_warning_days: int


class ExecutionCfg(BaseModel):
    slippage_bps: dict[str, float]
    commission: dict[str, float]


class PathsCfg(BaseModel):
    data_dir: str
    reports_dir: str
    cache_dir: str

    def resolve(self, root: Path) -> "ResolvedPaths":
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


class SonarCfg(BaseModel):
    cache_ttl_hours: int = 12
    model: str = "sonar"
    regions: list[str] = Field(
        default_factory=lambda: ["EU", "UK", "JP", "CN", "GLOBAL"],
    )


class EnrichmentCfg(BaseModel):
    borderline_min: float = 0.4
    borderline_max: float = 0.8
    polymarket_enabled: bool = True
    x_sentiment_enabled: bool = True
    cache_ttl_minutes: int = 60


class RiskGateCfg(BaseModel):
    caution_min: float = 0.3
    caution_size_mult: float = 0.5
    danger_min: float = 0.6
    capitulation_min: float = 0.85
    capitulation_amplify: float = 1.3


class ConvictionCfg(BaseModel):
    half_life_hours: float = 12.0
    fire_threshold: float = 2.5
    spread_threshold: float = 2.0
    cooldown_hours: float = 4.0
    black_swan_min: float = 0.9
    ledger_ttl_hours: float = 72.0


class OpenBBCfg(BaseModel):
    preferred_provider: str = "yfinance"
    fallback_enabled: bool = True
    cache_ttl_minutes: int = 15


class SpeechSpeakerCfg(BaseModel):
    id: str
    full_name: str
    role: str


class SpeechCfg(BaseModel):
    enabled: bool = True
    stt_provider: str = "deepgram"
    deepgram_model: str = "nova-2-finance"
    lexicon_version: str = "hawkish_dovish_v1"
    window_size: int = 5
    deviation_threshold_sigma: float = 1.5
    half_life_months: float = 6.0
    baseline_window_days: int = 365
    llm_model: str = "gpt-4o-mini"
    speakers: list[SpeechSpeakerCfg] = Field(default_factory=list)


class PersonaCfg(BaseModel):
    enabled: bool = True
    chat_model: str = "gpt-4o-mini"
    synthesis_model: str = "gpt-4o"
    embedding_model: str = "text-embedding-3-small"
    retrieval_top_k: int = 6
    chunk_max_tokens: int = 400
    chunk_overlap_tokens: int = 50
    chroma_path: str = "data/personas/chroma"
    active_roster: list[str] = Field(default_factory=list)


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


# ────────────────────────── figure_deviation (Wave 1) ────────────────────────
# Generalises `speech.speakers` into a multi-source, multi-lexicon engine.
# Existing Fed speakers are ported here in Wave 1. Trump (X API) lands in
# Wave 5. The legacy `speech` config above is retained while the migration
# happens — the two coexist until Wave 2.


class LexiconCfg(BaseModel):
    """One lexicon configuration on a tracked figure. A figure may have N
    lexicons that fire independently in parallel (see Trump → trade /
    fed-pressure / regulatory)."""

    name: str
    threshold_sigma: float = 1.5
    window_size: int = 5
    directional_tags_positive: list[str] = Field(default_factory=list)
    directional_tags_negative: list[str] = Field(default_factory=list)
    sub_axes: dict[str, list[str]] | None = None  # only for multi-axis lexicons


class TrackedFigureSourceCfg(BaseModel):
    """Source for a tracked figure's posts. `audio` for Fed speakers (existing
    Deepgram path), `x_api` for Trump (Wave 5), `sonar_tweet` reserved for
    figures without an X presence."""

    type: Literal["audio", "x_api", "sonar_tweet"]
    # audio path:
    provider: str | None = None
    stream_resolver: str | None = None
    # x_api / sonar_tweet path:
    username: str | None = None
    handles: list[str] | None = None
    poll_interval_min: int | None = None


class TrackedFigureBaselineCfg(BaseModel):
    """Per-figure baseline window + decay. Refreshed on the cadence below."""

    window_days: int = 365
    time_decay_half_life_days: int = 90
    refresh_cadence_days: int = 7


class TrackedFigureCfg(BaseModel):
    """One figure being tracked. Holds its sources, lexicons, baseline params,
    and presentational metadata."""

    id: str
    display_name: str
    sources: list[TrackedFigureSourceCfg]
    lexicons: list[LexiconCfg]
    baseline: TrackedFigureBaselineCfg = TrackedFigureBaselineCfg()


class FigureDeviationCfg(BaseModel):
    """Top-level figure-deviation engine config. Wave 2 will connect this to
    the orchestrator; Wave 1 just establishes the schema."""

    enabled: bool = True
    poll_interval_min: int = 30
    figures: list[TrackedFigureCfg] = Field(default_factory=list)


class XApiCfg(BaseModel):
    """X (Twitter) API v2 settings. Bearer token is read from env at runtime
    via the `x_api_bearer_token` property on `Settings`, NOT stored in YAML."""

    base_url: str = "https://api.twitter.com/2"
    request_timeout_sec: int = 10


class BacktestCfg(BaseModel):
    """Historical backtest harness — gpt-4o, Oct 2023 onwards.

    `enabled` is informational; the actual switch is the `BACKTEST_AS_OF`
    env var, set per-tick by the runner. Kept here so the report writer
    and CLI can read the canonical model overrides.
    """

    enabled: bool = False
    reasoning_model: str = "gpt-4o"
    fast_model: str = "gpt-4o-mini"
    auto_approve_post_hypothesis: bool = True
    auto_approve_post_debate: bool = True
    bench_instruments: list[str] = Field(default_factory=lambda: ["SPY", "AGG", "TLT"])
    initial_nav: float = 1_000_000.0
    universe: list[str] = Field(default_factory=list)
    nyt_topics: list[str] = Field(
        default_factory=lambda: [
            "federal reserve", "inflation", "ecb", "fomc", "cpi",
            "interest rates", "recession", "gdp",
        ],
    )
    sonar_trump_enabled: bool = True
    sonar_trump_max_per_month: int = 25
    runs_dir: str = "data/backtest_runs"


class Settings(BaseModel):
    fund: FundCfg
    models: ModelsCfg
    openai: OpenAICfg
    triggers: TriggersCfg
    risk: RiskCfg
    research: ResearchCfg
    curator: CuratorCfg
    execution: ExecutionCfg
    fred: FredCfg
    enrichment: EnrichmentCfg = EnrichmentCfg()
    risk_gate: RiskGateCfg = RiskGateCfg()
    conviction: ConvictionCfg = ConvictionCfg()
    openbb: OpenBBCfg = OpenBBCfg()
    sonar: SonarCfg = SonarCfg()
    speech: SpeechCfg = SpeechCfg()
    figure_deviation: FigureDeviationCfg = FigureDeviationCfg()
    x_api: XApiCfg = XApiCfg()
    personas: PersonaCfg = PersonaCfg()
    deep_research: DeepResearchCfg = DeepResearchCfg()
    backtest: BacktestCfg = BacktestCfg()
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
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Add it to .env or export it."
            )
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

    @property
    def perplexity_api_key(self) -> str | None:
        """Perplexity Sonar API key. Optional — falls back to static calendar."""
        key = os.environ.get("PERPLEXITY_API_KEY", "").strip()
        return key or None

    @property
    def x_api_bearer_token(self) -> str | None:
        """X (Twitter) API v2 bearer token. Required when any figure declares
        a `type: x_api` source; optional otherwise."""
        key = os.environ.get("X_API_BEARER_TOKEN", "").strip()
        return key or None

    @property
    def nyt_api_key(self) -> str | None:
        """NYT Article Search API key. Required to build the historical
        news archive for backtest. Optional otherwise."""
        key = os.environ.get("NYT_API_KEY", "").strip()
        return key or None


@lru_cache(maxsize=1)
def load_settings(config_path: Path | None = None) -> Settings:
    cfg_path = config_path or (ROOT / "config.yaml")
    with cfg_path.open("r") as f:
        raw = yaml.safe_load(f)
    raw["root"] = ROOT
    return Settings.model_validate(raw)


def get_settings() -> Settings:
    """Convenience accessor used across modules."""
    return load_settings()
