import { STATIC } from "@/api/client";
import { BASE } from "@/components/admin/DailyDesk";
import type { Fact } from "@/components/admin/trade/api";

// Topic Consultants' API (/admin/desk/consultants on Fly, forwarded from /api/admin/live/consultants behind
// the admin password). Mirrors src/castelino/agents/consultants/models.py.
export type { Fact };
export type Company = { name: string; ticker: string };
export type Watchlist = { companies: Company[]; series: string[]; queries: string[]; links?: string[] }; // links: pasted web pages
export type Status = "building" | "active" | "paused" | "failed";
export type Consultant = {
  slug: string; code: string; topic: string; watchlist: Watchlist; status: Status; created: string; error: string | null;
  post_to_x: boolean; // the knob: Auto posts a notable point a day to X with a chart; Off posts nothing
};
export type Part = { text: string; fact_ids: string[] };
export type Thesis = {
  happening: Part; lean: Part; alternative: Part; change_mind: Part; reason: string; updated: string; version: number;
};
export type HistoryLine = {
  day: string; kind: "start" | "daily" | "weekly"; verdict: "started" | "updated" | "held" | "skipped" | "week";
  p_thesis: number | null; p_memory: number | null; reason: string; before: string | null; after: string | null;
  moved: string[]; deleted: string[];
  p_post: number | null; post: string | null; chart_form: string | null; // what went out on X, if anything
};
export type Ask = { at: string; asker: string; question: string; fact_ids: string[] };
export type Note = { title: string; text: string; importance: number; last_used: string; type: string };
export type Row = Pick<Consultant, "slug" | "code" | "topic" | "status" | "error" | "created" | "post_to_x"> & {
  last: HistoryLine | null; facts_today: number; asks_today: number;
};
export type Detail = {
  consultant: Consultant; thesis: Thesis | null; history: HistoryLine[]; // newest first
  today: { day: string; facts: Fact[]; asks: Ask[]; notes: string[] };
  memory: { short: Note[]; long: Note[] };
  log: { day: string; cost_usd: number; notes: string[] }; // today's own log: cost-cap skips, failures
};

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${BASE}/consultants${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (r.status === 401 && STATIC) location.href = "/admin/login?expired=1&next=/admin"; // the session ended
  if (!r.ok) {
    const j = await r.json().catch(() => null);
    throw new Error((j && typeof j.detail === "string" && j.detail) || `${r.status} ${r.statusText}`);
  }
  return r.json();
}

export const consultants = {
  list: () => req<{ consultants: Row[] }>("GET", ""),
  plan: (topic: string) => req<{ watchlist: Watchlist }>("POST", "/plan", { topic }),
  // a hand-added company (by ticker), "fred:ID" / "yahoo:TICKER" series or web page link, checked by the backend
  check: (kind: "company" | "series" | "link", value: string) =>
    req<{ company?: Company; series?: string; link?: string }>("POST", "/check", { kind, value }),
  create: (topic: string, watchlist: Watchlist) => req<Row>("POST", "", { topic, watchlist }),
  setWatchlist: (slug: string, watchlist: Watchlist) => req<{ watchlist: Watchlist }>("PUT", `/${slug}/watchlist`, watchlist),
  get: (slug: string) => req<Detail>("GET", `/${slug}`),
  pause: (slug: string) => req<Row>("POST", `/${slug}/pause`),
  resume: (slug: string) => req<Row>("POST", `/${slug}/resume`),
  build: (slug: string) => req<Row>("POST", `/${slug}/build`),
  setPostToX: (slug: string, on: boolean) => req<Row>("POST", `/${slug}/x`, { on }),
  remove: (slug: string) => req<{ deleted: string }>("DELETE", `/${slug}`),
};

// The chart that went out with a day's post (an <img> sends the admin cookie, so the password gate still applies).
export const postChart = (slug: string, day: string) => `${BASE}/consultants/${slug}/posts/${day}.png`;
