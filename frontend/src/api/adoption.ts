/** AI Adoption Index endpoints (kept out of endpoints.ts on purpose). */

import { api } from "./client";

export type Bucket = "large" | "small";

export interface AdoptionCell {
  sector: string;
  bucket: Bucket;
  n: number;
  ew: number | null;
  cw: number | null;
  thin: boolean;
}

export interface AdoptionHeadline {
  large_ew: number | null;
  small_ew: number | null;
  spread: number | null;
  large_concentration: number | null;
  small_concentration: number | null;
}

export interface AdoptionSummary {
  period: string | null;
  headline: Partial<AdoptionHeadline>;
  series: { period: string; large_ew: number | null; small_ew: number | null }[];
  cells: AdoptionCell[];
  stats?: {
    n_companies: number;
    n_scored: number;
    n_claims: number;
    pillar_coverage: { talk: number; hire: number; spend: number };
  };
}

export interface AdoptionCompany {
  ticker: string;
  name?: string; // empty/missing until universe.csv has names
  bucket: Bucket;
  sector: string;
  market_cap: number;
  score: number | null;
  s_talk: number | null;
  s_hire: number | null;
  s_spend: number | null;
  claims: { depth: number; quote: string }[];
}

export const fetchAdoptionSummary = () => api.get<AdoptionSummary>("/adoption/summary");
// No filters = every company in the latest period.
export const fetchAdoptionCompanies = (sector?: string, bucket?: Bucket) => {
  const q = new URLSearchParams();
  if (sector) q.set("sector", sector);
  if (bucket) q.set("bucket", bucket);
  const qs = q.toString();
  return api.get<AdoptionCompany[]>(`/adoption/companies${qs ? `?${qs}` : ""}`);
};
