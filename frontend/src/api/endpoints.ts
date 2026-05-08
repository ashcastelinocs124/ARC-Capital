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

// ── Macro ──────────────────────────────────────────────────────────────
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
