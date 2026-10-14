/** One function per backend endpoint. Hooks call these. */

import { api } from "./client";
import type { CrossAssetSnapshot, MacroIndicatorRow, PlotlyChart, SectorSentimentSnapshot, WeekAhead, AiSentiment } from "./types";

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
export interface Exhibit { n: number; finding_id: string; item?: number | null; title: string; subtitle: string; file: string; } // item = the note item's rank (older notes: match finding_id)
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
  // Everything below is admin-only: the public catalog (/agents/catalog) carries only the fields above.
  tools?: AgentTool[];
  memory?: { reads: string[]; writes: string[]; persists: string };
  class_path?: string | null; tier?: string | null; model?: string | null;
  prompt?: string | null; prompt_source?: string | null;
  output?: { name: string; fields: { name: string; type: string; description: string }[] } | null;
  error?: string | null;
  dependencies?: { key: string; required: boolean; why: string; set: boolean }[];
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
  unregistered?: { class_name: string; class_path: string; file: string }[]; // admin only
}
export const fetchAgentCatalog = (admin = false) =>
  api.get<AgentCatalog>(admin ? "/admin/agents/catalog" : "/agents/catalog");

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

// ── Weekly Deep Dive (/weekly/*) ───────────────────────────────────────────
export interface WeeklyFact { id: string; text: string; source_title: string; source_url: string; }
export interface WeeklyChallenge { question: string; answer: string; verdict: string; }
export interface WeeklySection {
  title: string; agent: string; fact_ids: string[]; challenges: WeeklyChallenge[];
  // High level (from our Morning Notes) then the desk's deep research. Reports before
  // 2026-10-11's two-tier change only have `paragraphs`.
  what_happened?: string[]; why?: string[]; under_the_surface?: string[]; market_impact?: string[]; watch?: string[];
  paragraphs?: string[];
}
export interface WeeklyScoreRow {
  asset: string; level: number; unit: "%" | "level" | "$"; change_unit: "%" | "bp";
  w1: number | null; m1: number | null; m3: number | null; ytd: number | null;
}
export interface WeeklyRecord {
  version: 1; week: string; start: string; end: string; generated_at: string;
  plan: {
    trends: { title: string; why: string }[];
    agents: { name: string; description: string; goal: string; tools: string[]; trends?: string[] }[]; // trends: older records lack it
  };
  facts: WeeklyFact[];
  findings: { id: string; agent: string }[];
  grill_log: { agent: string; finding_id: string; question: string; answer: string }[];
  report: {
    title: string; subtitle: string; watch: string;
    bullets: { lead: string; body: string; fact_ids: string[] }[]; sections: WeeklySection[];
  };
  exhibits: { n: number; section: number; fact_id: string; title: string; subtitle: string; file: string }[];
  scorecard: WeeklyScoreRow[];
  regime: { pulse: number | null; pressure: number | null };
  counts: { notes: number; agents: number; data_pulls: number; board_posts: number; grill_rounds: number; figures_checked: number; exhibits: number };
  data_gaps: string[];
  models: Record<string, string>;
}
export interface WeeklyHistory { items: { week: string; start: string; end: string; title: string }[] }
export const isWeekly = (x: unknown): x is WeeklyRecord =>
  !!x && !Array.isArray(x) && (x as WeeklyRecord).version === 1 && typeof (x as WeeklyRecord).week === "string";
export const fetchWeeklyHistory = () => api.get<WeeklyHistory>("/weekly/history");
export const fetchWeekly = (week: string | null) => api.get<WeeklyRecord>(week ? `/weekly/${week}` : "/weekly/latest");
// Published Weekly Deep Dive posts on Substack (newest first).
export interface WeeklyPost { week: string; start: string; end: string; title: string; takeaways: string[]; image: string | null; url: string }
export const fetchWeeklyPosts = async (): Promise<WeeklyPost[]> => {
  const data = await api.get<WeeklyPost[]>("/weekly_posts"); // the client maps a 404 to []
  return Array.isArray(data) ? data : [];
};
export const fetchWeeklyStatus = () =>
  api.get<{ stage: string; week?: string; error?: string | null; due?: string | null }>("/weekly/status");

// ── Theme Charts (/themes/*) ───────────────────────────────────────────────
export type ThemeSignalKind = "coverage" | "move" | "odds";
export interface ThemeRun {
  run_id: string; date: string; slot: "am" | "pm"; generated_at: string;
  theme: string; why: string; lead: ThemeSignalKind; streak: number;
  signals: { kind: ThemeSignalKind; headline: string; note: string }[];
  fact_ids: string[];
  exhibits: { n: number; kind: string; title: string; subtitle: string; file: string }[];
  facts: { id: string; text: string; source_title: string; source_url: string }[];
}
export interface ThemeHistory { items: { run_id: string; date: string; slot: "am" | "pm"; theme: string }[] }
export const isThemeRun = (x: unknown): x is ThemeRun =>
  !!x && !Array.isArray(x) && typeof (x as ThemeRun).run_id === "string";
export const fetchThemeHistory = () => api.get<ThemeHistory>("/themes/history");
export const fetchThemeRun = (run: string | null) => api.get<ThemeRun>(run ? `/themes/${run}` : "/themes/latest");

// ── Videos (Substack) ───────────────────────────────────────────────────
export interface Video {
  title: string;
  url: string; // post on archresearch.substack.com
  date: string; // YYYY-MM-DD
  summary: string;
  thumbnail: string | null;
  duration: number | null; // seconds
  video?: boolean; // false = an article (the Videos tab always sends videos)
}
export const fetchVideos = async (): Promise<Video[]> => {
  const data = await api.get<Video[]>("/videos"); // the client maps a 404 to []
  return Array.isArray(data) ? data : [];
};

// ── Daily Note posts (Substack) ──────────────────────────────────────────
export interface DailyPost {
  date: string; // the note's day, YYYY-MM-DD
  title: string;
  takeaways: string[];
  image: string | null;
  url: string; // post on archresearch.substack.com
}
export const fetchDailyPosts = async (): Promise<DailyPost[]> => {
  const data = await api.get<DailyPost[]>("/daily_posts"); // the client maps a 404 to []
  return Array.isArray(data) ? data : [];
};

// ── Substack sections shown on Daily Update ──────────────────────────────
export interface SectionPost extends Video {
  section: string; // Substack section slug
}
export const fetchSectionPosts = async (): Promise<SectionPost[]> => {
  const data = await api.get<SectionPost[]>("/section_posts"); // the client maps a 404 to []
  return Array.isArray(data) ? data : [];
};

// ── Week Ahead ───────────────────────────────────────────────────────────
export const fetchWeekAhead = async (): Promise<WeekAhead | null> => {
  const data = await api.get<WeekAhead | Record<string, never> | []>("/week_ahead");
  // the client maps a 404 (static build without the file) to []
  return data && !Array.isArray(data) && "events" in data ? (data as WeekAhead) : null;
};

// ── AI Model Sentiment ───────────────────────────────────────────────────
export const fetchAiSentiment = async (): Promise<AiSentiment | null> => {
  const data = await api.get<AiSentiment | Record<string, never> | []>("/ai_sentiment");
  return data && !Array.isArray(data) && "providers" in data ? (data as AiSentiment) : null;
};
