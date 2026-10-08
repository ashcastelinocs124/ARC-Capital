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
