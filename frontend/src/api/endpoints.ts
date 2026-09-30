/** One function per backend endpoint. Hooks call these. */

import { api } from "./client";
import type {
  ApprovalActionResponse,
  ApprovalDetail,
  ApprovalHistoryItem,
  ApprovalQueueItem,
  Fill,
  GuardDecisionRow,
  KpiTile,
  MacroIndicatorRow,
  PlotlyChart,
  Position,
} from "./types";

// ── Portfolio ──────────────────────────────────────────────────────────
export const fetchPortfolioMetrics = () => api.get<KpiTile[]>("/portfolio_metrics");
export const fetchPositions = () => api.get<Position[]>("/positions");
export const fetchEquityCurveChart = () => api.get<PlotlyChart>("/equity_curve_chart");
export const fetchRecentFills = () => api.get<Fill[]>("/recent_fills");

// ── Models ─────────────────────────────────────────────────────────────
export interface ModelCard {
  id: string;
  name: string;
  kind: string;
  status: "fresh" | "stale" | "missing";
  trained_at?: string;
  prob?: number;
  up?: boolean;
  prob_label?: string;
  feature_month?: string; // YYYY-MM, last month of input data
  target_month?: string;
  accuracy?: number | null;
  brier?: number | null;
  n_test?: number | null;
  features?: string[];
  model_version?: string | null;
}
export const fetchModels = () => api.get<ModelCard[]>("/models");

// ── Macro ──────────────────────────────────────────────────────────────
export interface RegimeForecastRow { running: boolean; asof: string | null; growth_up: boolean | null; inflation_up: boolean | null; growth_prob: number | null; inflation_prob: number | null; }
export const fetchRegimeForecast = () => api.get<RegimeForecastRow>("/regime_forecast");
export const fetchMacroIndicators = () => api.get<MacroIndicatorRow[]>("/macro_indicators");
export const fetchYieldCurveChart = () => api.get<PlotlyChart>("/yield_curve_chart");
export const fetchTriggers = () => api.get<unknown[]>("/triggers_table");
export const fetchHypotheses = () => api.get<unknown[]>("/hypotheses_table");
export const fetchNewsFeed = () => api.get<unknown[]>("/news_feed");
export const fetchEconCalendar = () => api.get<unknown[]>("/econ_calendar");

// ── Research ───────────────────────────────────────────────────────────
export const fetchTaChart = () => api.get<PlotlyChart>("/ta_chart");
export const fetchScreener = () => api.get<unknown[]>("/screener");
export const fetchCorrelationHeatmap = () => api.get<PlotlyChart>("/correlation_heatmap");
export const fetchSectorPerf = () => api.get<unknown[]>("/sector_perf");

// ── Risk ───────────────────────────────────────────────────────────────
export const fetchExposureClassChart = () => api.get<PlotlyChart>("/exposure_class_chart");
export const fetchExposureInstrumentChart = () => api.get<PlotlyChart>("/exposure_instrument_chart");
export const fetchWarnings = () => api.get<unknown[]>("/warnings_table");

// ── Agents ─────────────────────────────────────────────────────────────
export const fetchVerdicts = () => api.get<unknown[]>("/verdicts_table");
export const fetchGuardDecisions = () => api.get<GuardDecisionRow[]>("/guard_decisions");

// Detailed per-agent feeds
export const fetchAgentSummary = () => api.get<{ agent: string; count: number }[]>("/agent_summary");
export const fetchAgentTriggers = () => api.get<AgentTriggerRow[]>("/agent_triggers");
export const fetchAgentWorldState = () => api.get<AgentWorldStateRow[]>("/agent_world_state");
export const fetchAgentHypotheses = () => api.get<AgentHypothesisRow[]>("/agent_hypotheses");
export const fetchAgentExpressions = () => api.get<AgentExpressionRow[]>("/agent_expressions");
export const fetchAgentResearch = () => api.get<AgentResearchRow[]>("/agent_research");
export const fetchAgentBull = () => api.get<AgentDebateRow[]>("/agent_bull");
export const fetchAgentBear = () => api.get<AgentDebateRow[]>("/agent_bear");
export const fetchAgentVerdicts = () => api.get<AgentVerdictRow[]>("/agent_verdicts");
export const fetchAgentGuard = () => api.get<AgentGuardRow[]>("/agent_guard");
export const fetchAgentWarnings = () => api.get<AgentWarningRow[]>("/agent_warnings");
export const fetchAgentCurator = () => api.get<AgentLessonRow[]>("/agent_curator");

// Row types for the per-agent feeds
export interface AgentTriggerRow { timestamp: string; source: string; headline: string; significance: number; asset_classes: string; reason: string; }
export interface AgentWorldStateRow { timestamp: string; summary: string; headline_count: number; indicator_reads: number; surprises: number; }
export interface AgentHypothesisRow { timestamp: string; thesis: string; regime: string; conviction: string; horizon_days: number; kill_criteria_count: number; rationale: string; }
export interface AgentExpressionRow { timestamp: string; instrument: string; direction: string; target_pct_nav: number; stop_pct: number; rationale: string; }
export interface AgentResearchRow { timestamp: string; instrument: string; sentiment: string; trend: string; rsi_14: number; hit_rate: number; samples: number; vol_60d: number; summary: string; }
export interface AgentDebateRow { timestamp: string; confidence: string; argument_count: number; strongest: string; }
export interface AgentVerdictRow { timestamp: string; decision: string; size_multiplier: number; decisive_factor: string; dissent: string; }
export interface AgentGuardRow { timestamp: string; decision: string; triggered_rules: string; amended_size: number; rationale: string; }
export interface AgentWarningRow { timestamp: string; rule_id: string; severity: string; description: string; }
export interface AgentLessonRow { timestamp: string; category: string; title: string; body: string; statistical_backing: string; }

// ── Approvals ──────────────────────────────────────────────────────────
export const fetchApprovalMetrics = () => api.get<KpiTile[]>("/approval_metrics");
export const fetchApprovalQueue = () => api.get<ApprovalQueueItem[]>("/approval_queue");
export const fetchApprovalQueueFull = () => api.get<ApprovalQueueItem[]>("/approval_queue_full");
export const fetchApprovalHistory = () => api.get<ApprovalHistoryItem[]>("/approval_history");
export const fetchApprovalDetail = (entryId: string) =>
  api.get<ApprovalDetail>(`/approval_detail/${entryId}`);

export const approveItem = (entryId: string, notes: string) =>
  api.post<ApprovalActionResponse>(`/approvals/${entryId}/approve`, { notes });

export const rejectItem = (entryId: string, notes: string) =>
  api.post<ApprovalActionResponse>(`/approvals/${entryId}/reject`, { notes, reason: notes });

export interface UpdateStatus { stage: string; date?: string; error?: string | null; has_today?: boolean; }
export interface SectorTrendRow {
  sector: string; r1w: number | null; r1m: number | null; r3m: number | null; r6m: number | null;
  r12m: number | null; rel1m: number | null; rel12m: number | null; short_label: string; long_label: string;
}
export interface ReleaseRow { series: string; name: string; latest: number; prior: number | null; change: number | null; }
export interface PredictionDeltaRow { old: number | null; new: number; gate: string; }
export interface DailyRecord {
  date: string; generated_at: string;
  snapshot: {
    date: string; releases: ReleaseRow[]; sectors: SectorTrendRow[];
    prediction: Record<string, PredictionDeltaRow>; data_gaps: string[]; model_note: string | null;
    // asset class -> instrument -> window ("1d" | "1w" | "1m") -> % (bp for yields)
    asset_returns: Record<string, Record<string, Record<string, number | null>>>;
  };
  update: {
    headline: string; economy: string; asset_classes: string; predictions_changed: string;
    sector_reads: { sector: string; text: string }[];
    themes_touched: { title: string; text: string }[];
    new_themes: { title: string; text: string; importance: number }[];
  };
}
export const fetchUpdateStatus = () => api.get<UpdateStatus>("/update/status");
export const fetchLatestUpdate = () => api.get<DailyRecord>("/update/latest");
export const fetchUpdateHistory = () => api.get<{ dates: string[] }>("/update/history");
export const fetchUpdateByDate = (day: string) => api.get<DailyRecord>(`/update/${day}`);

export interface AgentTool { name: string; does: string; }
export interface AgentCatalogEntry {
  id: string; name: string; group: string; summary: string;
  tools: AgentTool[];
  memory: { reads: string[]; writes: string[]; persists: string };
  class_path: string | null; tier: string | null; model: string | null;
  prompt: string | null; prompt_source: string | null;
  output: { name: string; fields: { name: string; type: string; description: string }[] } | null;
  error: string | null;
}
export interface AgentCatalog {
  agents: AgentCatalogEntry[]; groups: string[];
  unregistered: { class_name: string; class_path: string; file: string }[];
}
export const fetchAgentCatalog = () => api.get<AgentCatalog>("/agents/catalog");
