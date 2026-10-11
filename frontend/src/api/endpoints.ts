/** One function per backend endpoint. Hooks call these. */

import { api } from "./client";
import type { CrossAssetSnapshot, MacroIndicatorRow, PlotlyChart, SectorSentimentSnapshot } from "./types";

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
  predicts?: { question: string; output: string };
  parameters?: { name: string; value: string | number; note: string }[];
  sources?: { id: string; name: string; role: "target" | "indicator"; provider: string; ref: string; used: boolean }[];
  history?: { month: string; value: number }[]; // YYYY-MM; what the label is built from, for the tile chart
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

// Detailed per-agent feeds

// Row types for the per-agent feeds

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
export interface NoteFinding {
  id: string; agent: "macro" | "news" | "alt" | "ai"; claim: string;
  provenance: "data" | "reported"; source_title: string; source_url: string;
}
export interface NoteItem { rank: number; title: string; body: string; finding_ids: string[]; chart: string | null; }
export interface Exhibit { n: number; finding_id: string; title: string; subtitle: string; file: string; }
export interface DailyRecordV2 {
  version: 2; date: string; generated_at: string;
  findings: NoteFinding[]; exhibits: Exhibit[]; releases: ReleaseRow[]; rounds: number; data_gaps: string[];
  backfilled?: boolean; // rebuilt later, as of this date
  note: { headline: string; takeaways: string[]; items: NoteItem[] };
}
export type AnyDailyRecord = DailyRecord | DailyRecordV2;
export const isV2 = (r: AnyDailyRecord): r is DailyRecordV2 => (r as DailyRecordV2).version === 2;
export const fetchUpdateStatus = () => api.get<UpdateStatus>("/update/status");
export const fetchLatestUpdate = () => api.get<AnyDailyRecord>("/update/latest");
export interface UpdateHistory {
  dates: string[];
  items?: { date: string; headline: string }[]; // newest first; absent from older backends
}
export const fetchUpdateHistory = () => api.get<UpdateHistory>("/update/history");
export const fetchUpdateByDate = (day: string) => api.get<AnyDailyRecord>(`/update/${day}`);

export interface AgentTool { name: string; does: string; }
export interface AgentCatalogEntry {
  id: string; name: string; group: string; summary: string;
  family?: string | null; // main agent it belongs to, e.g. "Update Agent"
  tools: AgentTool[];
  memory: { reads: string[]; writes: string[]; persists: string };
  class_path: string | null; tier: string | null; model: string | null;
  prompt: string | null; prompt_source: string | null;
  output: { name: string; fields: { name: string; type: string; description: string }[] } | null;
  error: string | null;
  dependencies: { key: string; required: boolean; why: string; set: boolean }[];
}
export interface SystemLane {
  title: string;
  flow: string[][]; // steps left → right; each step's boxes stack. Box = "kind:text|caption"
  loops?: { from: number; to: number; label: string }[];
  regions?: { from: number; to: number; label: string }[];
}
export interface AgentSystem { group: string; trigger: string; output: string; blurb: string; lanes: SystemLane[] }
export interface AgentCatalog {
  agents: AgentCatalogEntry[]; groups: string[]; systems?: AgentSystem[];
  unregistered: { class_name: string; class_path: string; file: string }[];
}
export const fetchAgentCatalog = () => api.get<AgentCatalog>("/agents/catalog");

// ── Sector Sentiment ───────────────────────────────────────────────────
export const fetchSectorSentiment = async (): Promise<SectorSentimentSnapshot | null> => {
  const data = await api.get<SectorSentimentSnapshot | Record<string, never>>("/sector_sentiment");
  return data && "sectors" in data ? (data as SectorSentimentSnapshot) : null;
};

// ── Cross-Asset Drivers ─────────────────────────────────────────────────
export const fetchCrossAsset = async (): Promise<CrossAssetSnapshot | null> => {
  const data = await api.get<CrossAssetSnapshot | Record<string, never> | []>("/cross_asset");
  // the client maps a 404 (static build without the file) to []
  return data && !Array.isArray(data) && "assets" in data ? (data as CrossAssetSnapshot) : null;
};

// ── Videos (Substack) ───────────────────────────────────────────────────
export interface Video {
  title: string;
  url: string; // post on archresearch.substack.com
  date: string; // YYYY-MM-DD
  summary: string;
  thumbnail: string | null;
  duration: number | null; // seconds
}
export const fetchVideos = async (): Promise<Video[]> => {
  const data = await api.get<Video[]>("/videos"); // the client maps a 404 to []
  return Array.isArray(data) ? data : [];
};
