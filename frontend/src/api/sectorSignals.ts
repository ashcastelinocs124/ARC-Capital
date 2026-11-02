/** The Sector Signal Significance dashboard (GET /dashboards/sector-signals), mirroring
 * dashboards/sector_signals/run.py. Returns are simple returns as fractions (0.012 = 1.2%). */

import { api } from "./client";

export type Verdict = "signal" | "weak" | "noise" | "few";

export interface CatalogSignal { id: string; label: string; expected: 1 | -1; family: string; description: string }

export interface RegimeStat { n: number; mean: number | null; base_mean: number | null; edge: number | null; hit: number | null; p: number | null }

export interface SignalTest {
  sector: string; etf: string; signal: string; h: number;
  n: number; mean: number | null; base_mean: number; base_hit: number; hit: number | null;
  null_mean: number | null; null_sd: number | null; edge: number | null; z: number | null; p: number | null; q: number | null;
  verdict: Verdict; textbook: boolean | null;
  is: { n: number; p: number | null; edge: number | null; verdict: Verdict };
  oos: { n: number; edge: number | null; held: boolean | null };
  regimes: { vix: { calm: RegimeStat; stressed: RegimeStat }; trend: { up: RegimeStat; down: RegimeStat } };
}

export interface LiveEvent {
  sector: string; etf: string; signal: string; date: string; sessions_ago: number; close: number;
  best_h: number; verdict: Verdict;
}

export interface EventPath { n: number; mean: (number | null)[]; null_lo: (number | null)[]; null_mid: (number | null)[]; null_hi: (number | null)[] }

export interface PastEvent { date: string; close: number; [k: `r${number}`]: number | null }

export interface SectorInfo {
  sector: string; etf: string; start: string; rows: number; oos_from: string;
  regime_now: { vix: string; trend: string };
}

export interface PriceChart { dates: string[]; close: (number | null)[]; events: Record<string, string[]> }

export interface HoldRate { n: number; rate: number | null }

export interface SectorSignals {
  as_of: string;
  generated_at: string;
  source: string;
  params: {
    horizons: number[]; bootstrap: number; fdr: number; p_weak: number; min_events: number; cooldown: number;
    vix_stressed: number; oos_split: number; vol_window: number; live_lookback_days: number; path_days: number;
  };
  regime_now: { vix: number | null; vix_state: string; trend_state: string };
  catalog: CatalogSignal[];
  sectors: SectorInfo[];
  summary: { tests: number; counts: Record<string, Record<Verdict, number>>; oos: { signal: HoldRate; weak: HoldRate; noise: HoldRate } };
  live: LiveEvent[];
  tests: SignalTest[];
  paths: Record<string, EventPath>;
  recent: Record<string, PastEvent[]>;
  charts: Record<string, PriceChart>;
  gaps: { etf: string; reason: string }[];
}

export const fetchSectorSignals = async (): Promise<SectorSignals | null> => {
  const d = await api.get<SectorSignals | Record<string, never>>("/dashboards/sector-signals");
  return d && "tests" in d ? (d as SectorSignals) : null;
};
