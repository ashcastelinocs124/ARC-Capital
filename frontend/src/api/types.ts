/** Types mirroring the FastAPI backend response shapes. */

export interface KpiTile {
  label: string;
  value: string;
  delta?: string;
  subvalue?: string;
}

export interface Position {
  instrument_id: string;
  side: "LONG" | "SHORT";
  asset_class: string;
  quantity: number;
  entry_price: number;
  mark_price: number;
  market_value: number;
  pct_nav: number;
  unrealized_pnl: number;
  unrealized_pct: number;
}

export interface Fill {
  timestamp: string;
  type: "open" | "close" | "trim" | "stop_loss";
  instrument_id: string;
  quantity: number;
  fill_price: number;
  slippage: number;
  commission: number;
  realized_pnl: number;
}

export interface MacroIndicatorRow {
  date: string;
  [series: string]: string | number;
}

export interface GuardDecisionRow {
  timestamp: string;
  decision: "approved" | "hard_veto" | "soft_warning" | "amended";
  triggered_rules: number;
  rationale: string;
}

// Plotly-shaped charts the backend produces
export interface PlotlyChart {
  data: Array<Record<string, unknown>>;
  layout: Record<string, unknown>;
}

// Approval workflow
export type ApprovalGate = "post_hypothesis" | "post_debate";
export type ApprovalStatus = "pending" | "approved" | "rejected";

export interface ApprovalQueueItem {
  entry_id: string;
  gate: ApprovalGate;
  submitted_at: string;
  summary?: string;
  payload?: Record<string, unknown>;
}

export interface ApprovalHistoryItem {
  entry_id: string;
  gate: ApprovalGate;
  status: ApprovalStatus;
  resolved_at: string;
  notes: string;
  rejection_reason: string;
}

export interface ApprovalDetail {
  entry_id: string;
  gate: ApprovalGate;
  status: ApprovalStatus;
  submitted_at: string;
  resolved_at: string | null;
  payload: Record<string, unknown>;
  notes: string;
  rejection_reason: string | null;
}

export interface ApprovalActionResponse {
  entry_id: string;
  status: ApprovalStatus;
  notes: string;
  resolved_at: string;
  rejection_reason?: string;
}

// Hypothesis payload (post_hypothesis gate)
export interface HypothesisPayload {
  thesis: string;
  regime: string;
  conviction: "low" | "medium" | "high";
  horizon_days: number;
  kill_criteria: string[];
}

// Debate verdict payload (post_debate gate)
export interface VerdictPayload {
  instrument: string;
  direction: "long" | "short";
  decision: "proceed" | "reject" | "modify";
  size_multiplier: number;
  decisive_factor: string;
  dissent: string;
}

export interface Citation { source: string; snippet: string; score: number; }

export interface PersonaMessage {
  role: "user" | "assistant";
  text: string;
  timestamp: string;
  citations: Citation[];
}

export interface PersonaConversation {
  entry_id: string;
  persona_id: string;
  started_at: string;
  messages: PersonaMessage[];
}

export interface FamousCall { date: string; description: string; }

export interface PersonaCard {
  persona_id: string;
  full_name: string;
  role: string;
  tenure: string;
  image_url?: string;
  belief_summary: string;
  decision_framework: string[];
  signature_phrases: string[];
  famous_calls: FamousCall[];
  voice_notes: string;
}

export interface PanelResponse { persona_id: string; text: string; citations: Citation[]; }

export interface Disagreement { axis: string; positions: Record<string, string>; }

export interface PanelSynthesis {
  consensus: string[];
  disagreements: Disagreement[];
  strongest_objection: string;
  recommended_modifications: string[];
}

export interface PanelDiscussion {
  entry_id: string;
  question: string;
  responses: PanelResponse[];
  synthesis: PanelSynthesis;
  created_at: string;
}


export interface PersonaStandaloneThread {
  persona_id: string;
  started_at: string;
  last_active_at: string;
  messages: PersonaMessage[];
}

export interface RoomMessage {
  speaker: string;       // "user" or persona_id
  text: string;
  timestamp: string;
  turn: number;
  citations: Citation[];
}

export interface RoomSummary {
  room_id: string;
  name: string;
  member_persona_ids: string[];
  last_active_at: string;
  message_count: number;
}

export interface PersonaRoom {
  room_id: string;
  name: string;
  member_persona_ids: string[];
  context: string;
  created_at: string;
  last_active_at: string;
  messages: RoomMessage[];
}
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
