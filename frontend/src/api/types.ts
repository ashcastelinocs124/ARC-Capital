/** Types mirroring the FastAPI backend response shapes. */

export interface MacroIndicatorRow {
  date: string;
  [series: string]: string | number;
}

// Plotly-shaped charts the backend produces
export interface PlotlyChart {
  data: Array<Record<string, unknown>>;
  layout: Record<string, unknown>;
}

// Approval workflow

// Hypothesis payload (post_hypothesis gate)

// Debate verdict payload (post_debate gate)

// ── Sector Sentiment ───────────────────────────────────────────────────

export interface StockContribution {
  symbol: string;
  divergence: number;
  contribution: number; // cap share × divergence; sums to SectorScore.divergence
}

export interface SectorExplanation {
  verdict: "stock_specific" | "sector_wide" | "mixed";
  n_agree: number;
  n_total: number;
  top_symbol: string;
  top_share: number;
  equal_weight_divergence: number;
  contributions: StockContribution[]; // sorted by |contribution| desc
  drivers: string[];
  prose: string | null;
  generated_at: string | null;
}

export interface SectorScore {
  sector: string;
  etf: string;
  divergence: number;
  tech_score: number;
  fund_score: number;
  label: "euphoric" | "fair" | "fearful";
  explanation: SectorExplanation | null;
  avg_divergence: number | null;
  avg_tech: number | null;
  avg_fund: number | null;
  zscore: number | null;
  delta_since_prev: number | null;
  part_of?: string | null; // overlay rows only (Semiconductors): the GICS sector whose stocks it shares
}

export interface SectorStockRow {
  symbol: string;
  name: string;
  sector: string;
  market_cap: number;
  rsi14: number | null;
  macd_hist: number | null;
  vs_sma50: number | null;
  vs_sma200: number | null;
  ret_3m: number | null;
  rev_yoy: number | null;
  earnings_growth: number | null;
  pe_rel: number | null;
  fwd_pe_rel?: number | null; // forward P/E ÷ the row's median
  eps_rev_90d?: number | null; // next-year EPS estimate now ÷ 90 days ago − 1
  tech_score: number | null;
  fund_score: number | null;
  divergence: number | null;
  fundamentals_missing: boolean;
}

export interface SectorSentimentSnapshot {
  as_of: string;
  sectors: SectorScore[];
  stocks: SectorStockRow[];
  narrative: string | null;
  narrative_generated_at: string | null;
}

// ── Cross-Asset Drivers (GET /cross_asset) ─────────────────────────────
export interface CrossAssetContribution {
  factor: string;
  label: string;
  group: string;
  move: number;
  unit: string;
  beta: number;
  contribution: number;
}
export interface CrossAssetGroup {
  group: string;
  label: string;
  contribution: number;
  members: CrossAssetContribution[];
  max_pairwise_corr: number | null;
}
export interface CrossAssetWindow {
  move: number;
  unexplained: number;
  contributions: CrossAssetContribution[];
  groups: CrossAssetGroup[];
}
export interface CrossAssetBlock {
  name: string;
  ticker: string;
  alpha: number;
  oos_r2: number | null;
  summary: string;
  windows: Record<"1w" | "1m" | "3m", CrossAssetWindow>;
}
export interface CrossAssetSurprise {
  series: string;
  label: string;
  release_date: string;
  actual: number;
  consensus: number;
  z: number;
  group: "inflation" | "growth";
  unit: string;
  url: string;
}
export interface CrossAssetSnapshot {
  generated_at: string;
  week_end: string;
  assets: Record<"spx" | "ief", CrossAssetBlock>;
  surprises: CrossAssetSurprise[];
  releases_checked: { ok: number; total: number };
  data_gaps: string[];
}

// ── Week Ahead (GET /week_ahead) ─────────────────────────────────────────
export type WeekKind = "inflation" | "jobs" | "other" | "earnings" | "ai";
export interface WeekEvent {
  date: string | null;
  time_et: string | null;
  kind: WeekKind;
  name: string;
  country?: "US" | "CN" | "DE" | "JP" | "IN";
  measure?: "y/y" | "m/m" | null;
  consensus?: number | null;
  previous?: number | null;
  actual?: number | null;
  unit?: string;
  ticker?: string;
  company?: string;
  group?: "sp500" | "ai_extra";
  market_cap?: number | null;
  eps_est?: number | null;
  eps_year_ago?: number | null;
  session?: "pre" | "post" | null;
  lab?: string;
  status?: "launched" | "reported";
  when?: string | null;
  source_url?: string;
}
export interface OpenRouterShare { week: [string, string]; basis: string; labs: { lab: string; share: number; tokens: number }[] }
export interface WeekAhead {
  week_start: string;
  week_end: string;
  generated_at: string;
  events: WeekEvent[];
  spend: { ramp: Record<string, [string, number][]>; openrouter: OpenRouterShare | null };
  gaps: { lane: string; error: string }[];
  sectors?: SectorRow[];
}
export interface SectorRow { sector: string; etf: string; ytd: number; pe: number | null; earnings_growth: number | null }

// ── AI Model Sentiment (GET /ai_sentiment) ─────────────────────────────────
export interface SentimentPost { url: string; author: string; text: string; score: number; hits: string[] }
export interface SentimentProvider {
  level: number;
  delta: number | null;
  n7: number;
  series: [string, number][];
  samples: SentimentPost[];
}
export interface AiSentiment {
  generated_at: string;
  accounts: number;
  providers: Record<string, SentimentProvider>;
  gaps: { day: string; error: string }[];
}
