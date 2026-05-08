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
