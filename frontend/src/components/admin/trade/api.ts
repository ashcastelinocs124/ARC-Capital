import { STATIC } from "@/api/client";
import { BASE } from "@/components/admin/DailyDesk";

// Trade Lab's API (/admin/desk/trade on Fly, forwarded from /api/admin/live/trade behind the admin password).
export type Status = "framing" | "debating" | "awaiting_view" | "researching" | "awaiting_charts" | "writing" | "draft_ready";
export type Fact = { id: string; text: string; numbers: number[]; provenance: string; source_title: string; source_url: string };
export type Frame = {
  title: string; thesis: string; stand_ins: { ticker: string; role: string; label: string }[];
  horizon_months: number; prove_wrong: string[]; why_now_query: string;
};
export type Turn = { side: "bull" | "bear"; round: number; text: string; fact_ids: string[] };
export type Item = { id: string; kind: "claim" | "question" | "moderator"; text: string; round: number; removed: boolean };
export type Msg = {
  talk: 1 | 2; role: "user" | "agent"; to: string; text: string; fact_ids: string[];
  decision: Record<string, number> | null; action: string; at: string;
};
export type Spec = {
  section: string; form: string; series: string[]; window_days: number; threshold: number | null;
  title: string; why: string; agent_pick: boolean;
};
export type Option = { id: string; spec: Spec; file: string | null; error: string | null; fact_ids: string[]; chosen: boolean };
export type Brief = { desk: string; title: string; brief: string; must_answer: string[]; item_ids: string[]; tickers: string[] };
export type DeskRun = {
  desk: string; brief: Brief; calls: number; domains: string[]; error: string | null;
  report: { findings: { claim: string; fact_ids: string[] }[]; summary: string; unanswered: string[] } | null;
};
export type Round = { n: number; briefs: Brief[]; desks: DeskRun[]; options: Option[] };
export type Job = { step: string; state: "queued" | "running" | "done" | "failed" | "interrupted"; message: string; at: string };
export type Report = {
  title: string; subtitle: string; introduction: string[]; takeaways: string[]; what_to_watch: string; changes: string[];
  sections: { key: string; heading: string; paragraphs: string[]; fact_ids: string[] }[];
};
export type Idea = {
  id: string; idea: string; created_at: string; updated_at: string; status: Status; round: number; frame: Frame | null;
  turns: Turn[]; moderation: { settled: { point: string; fact_ids: string[] }[]; open: { question: string; why: string }[] } | null;
  talk: Msg[]; research: Item[]; rounds: Round[]; report: Report | null; facts: Fact[]; cost_usd: number; job: Job | null;
  substack: { draft_id: number; url: string } | null; fallbacks: string[];
};
export type Row = { id: string; title: string; idea: string; status: Status; round: number; cost_usd: number; job: Job | null; updated_at: string };

export const SECTIONS = ["intro", "bull", "bear", "question", "technical", "read", "watch"] as const;
export const SECTION_LABEL: Record<string, string> = {
  intro: "Introduction", bull: "1 · The bull case", bear: "2 · The bear case", question: "3 · Your question, tested",
  technical: "4 · The technical picture", read: "5 · Our read", watch: "What to watch",
};
export const PLAIN = new Set(["line", "compare", "bars"]);

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${BASE}/trade${path}`, {
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

export const trade = {
  list: () => req<{ ideas: Row[] }>("GET", ""),
  create: (idea: string) => req<Idea>("POST", "", { idea }),
  get: (id: string) => req<Idea>("GET", `/${id}`),
  talk: (id: string, talk: 1 | 2, to: string, message: string) =>
    req<{ messages: Msg[]; idea: Idea }>("POST", `/${id}/talk`, { talk, to, message }),
  removeItem: (id: string, item: string) => req<Idea>("DELETE", `/${id}/research/${item}`),
  research: (id: string) => req<Idea>("POST", `/${id}/research`),
  rerun: (id: string) => req<Idea>("POST", `/${id}/rerun-debate`),
  setFrame: (id: string, frame: Frame) => req<Idea>("PATCH", `/${id}/frame`, frame),
  round: (id: string) => req<Idea>("POST", `/${id}/round`),
  another: (id: string, section: string) => req<Option>("POST", `/${id}/charts/${section}/another`),
  choose: (id: string, picks: Record<string, string>) => req<Idea>("POST", `/${id}/charts`, { picks }),
  retry: (id: string) => req<Idea>("POST", `/${id}/retry`),
  hide: (id: string) => req<{ hidden: string }>("DELETE", `/${id}`),
  chartUrl: (id: string, file: string) => `${BASE}/trade/${id}/charts/${file}`,
};
