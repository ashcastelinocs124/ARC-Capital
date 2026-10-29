/** The AI Demand & Capex dashboard (GET /dashboards/ai-capex), mirroring dashboards/ai_capex/run.py. */

import { api } from "./client";

export interface Source { title: string; url: string; line?: string }

export interface CapexQuarter { q: string; end: string | null; capex: number | null; revenue: number | null; ocf: number | null }

export interface Mix { own_cash: number; debt: number; convertible: number; shares: number; cash_on_hand: number }

export interface CapexCompany {
  ticker: string;
  name: string;
  kind: "hyperscaler" | "neocloud";
  quarters: CapexQuarter[];
  ttm: { capex?: number | null; ocf?: number | null; revenue?: number | null };
  mix: Mix | null;
  cents_per_dollar: number | null;
  cents_year_ago: number | null;
  ocf_share: number | null;
  avg_rate: number | null;
  yoy_pct: number | null;
  as_of: string | null;
  cloud: { name: string; growth_pct: number | null; revenue: number | null } | null;
  backlog: { label: string; value: number; year_ago: number | null } | null;
  power: { online_gw: number | null; contracted_gw: number | null } | null;
  guidance: {
    low: number | null; high: number | null; label: string;
    actual: number | null; actual_label: string | null; line: string | null; source: Source;
  } | null;
  borrowing: { label: string; rate_pct: number; date: string; source: Source }[];
  off_balance: { label: string; value: number; source: Source }[];
  events?: { date: string; text: string | null; source: Source }[]; // text: the company's quoted words only
  sources: { xbrl: Source; release: Source | null };
}

export interface CapexTotals {
  quarters: { q: string; capex: number; reported: number; of: number }[];
  yoy_pct?: number;
  ttm_capex?: number;
  ttm_yoy_pct?: number;
  backlog?: number;
  backlog_growth_pct?: number;
  neocloud_capex_q?: number;
}

export interface AdoptionBucket {
  n: number;
  with_claim: number;
  pct: number | null;
  depth: [number, number, number];
  sectors: { sector: string; n: number; pct: number; thin: boolean }[];
  quotes: { name: string; ticker: string; quote: string }[];
}

export interface AiCapex {
  generated_at: string;
  as_of: string;
  companies: CapexCompany[];
  private: { name: string; online_gw: number | null; contracted_gw: number | null; source: Source }[];
  totals: CapexTotals;
  nvidia: { quarters: { q: string; value: number | null }[]; growth_pct: number | null; source: Source | null } | null;
  rates: { treasury_10y: { value: number; date: string }; high_yield: { value: number; date: string } } | null;
  gpu: { as_of: string; rows: { gpu: string; price: number; change_7d_pct: number }[]; history: { date: string; gpu: string; price: number }[]; source: Source } | null;
  ramp: {
    month: string;
    sizes: { size: "large" | "mid" | "small"; label: string; pct: number }[];
    vendors: { vendor: string; pct: number }[];
    industries: { industry: string; pct: number }[];
  } | null;
  openrouter: { week: [string, string]; basis: string; labs: { lab: string; share: number; tokens: number }[] } | null;
  census: {
    smpdt: string; ref_end: string | null; overall_pct: number | null;
    by_class: { code: string; label: string; pct: number; bucket: "small" | "mid" | "large" }[]; source: Source;
  } | null;
  adoption: {
    period: string; product_claims: { named: number; total: number };
    buckets: Record<"all" | "large" | "mid" | "small", AdoptionBucket>; source: Source;
  } | null;
  sentences: Partial<Record<"spending" | "funding" | "demand" | "compute", string>>;
  gaps: { lane: string; error: string }[];
}

export const fetchAiCapex = async (): Promise<AiCapex | null> => {
  const data = await api.get<AiCapex | Record<string, never> | []>("/dashboards/ai-capex");
  // the client maps a 404 to [] and an empty file is {}: only a real payload has companies
  return data && !Array.isArray(data) && "companies" in data ? (data as AiCapex) : null;
};

/** $bn as the page prints it: $1.82tn, $181bn, $8.4bn. */
export const usd = (v: number) => (v >= 1000 ? `$${(v / 1000).toFixed(2)}tn` : v < 10 ? `$${v.toFixed(1)}bn` : `$${Math.round(v)}bn`);
/** "2026Q2" -> "Q2 2026" */
export const qName = (q: string) => `Q${q[5]} ${q.slice(0, 4)}`;
/** "2026Q2" -> "Q2 '26" */
export const qShort = (q: string) => `Q${q[5]} '${q.slice(2, 4)}`;
