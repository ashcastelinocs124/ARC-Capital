import { STATIC } from "@/api/client";
import { BASE } from "@/components/admin/DailyDesk";
import type { Fact, Job } from "@/components/admin/trade/api";

// General Deep Research's API (/admin/desk/research on Fly, forwarded from /api/admin/live/research behind the
// admin password).
export type { Fact, Job };
export type Brief = { name: string; angle: string; brief: string };
export type Finding = { id: string; claim: string; fact_ids: string[] };
export type AgentRun = {
  letter: string; round: number; brief: Brief; model: string; tool_calls: number; x_posts: number;
  facts: Fact[]; findings: Finding[]; summary: string | null; error: string | null;
};
export type ChartValue = { fact_id: string; label: string; value: number };
// A point's chart, drawn from its cited facts (charts.py); fallback = the code-made big-number tile.
export type PointChart = {
  form: "bars" | "line" | "dumbbell" | "stat"; title: string; unit: "%" | "$" | "bp" | "pp" | "level" | "";
  values: ChartValue[]; fallback: boolean;
};
// A point's diagram (diagrams.py): how its ideas relate, when that explains it better than a chart (visuals.py)
export type DiagramBox = { title: string; lines: string[]; note: string };
export type PointDiagram = {
  point_id: string; layout: "branches" | "flow"; title: string; root: string; root_note: string;
  boxes: DiagramBox[]; caption: string;
};
export type Point = {
  id: string; agent: string; headline: string; body: string; fact_ids: string[]; version: number; chart: PointChart | null;
  diagram?: PointDiagram | null; // a chart or a diagram, never both
  added: number | null; // the Addition that wrote it; null for the original report
  older: string; // its newest cited figure's year ("2025") or "undated" when older than this year; "" if current
};
export type Proposal = {
  n: number; point_id: string; agent: string; text: string; answer: string; base_version: number;
  before: Point | null; after: Point | null; new_facts: Fact[];
  status: "running" | "pending" | "answered" | "approved" | "rejected" | "failed";
  error: string; trail: string[]; created_at: string; decided_at: string | null;
};
// Angles added to a finished report: new agents (round 2 + n) research them; Claude writes new points only.
export type Addition = {
  n: number; text: string; round: number; status: "running" | "done" | "failed"; error: string; created_at: string;
};
// The report's Substack draft (publish.py); note says why the last push didn't update it.
export type SubstackDraft = { draft_id: number | null; url: string; sha: string; at: string; note: string };
export type Report = { title: string; subtitle: string; points: Point[]; caveats: string[]; gaps_remaining: string[] };
export type Status = "awaiting_answers" | "researching" | "writing" | "complete";
export type Session = {
  id: string; topic: string; question: string; clarifying_questions: { question: string; why: string }[];
  answers: Record<string, string>; status: Status; job: Job | null; agents: AgentRun[];
  board: { agent: string; note: string; fact_ids: string[] }[]; board_facts: Record<string, Fact>;
  report: Report | null; proposals: Proposal[]; additions: Addition[]; substack: SubstackDraft | null; cost_usd: number; cost_cap_usd: number; fallbacks: string[];
  created_at: string; updated_at: string; compacted_at: string | null;
};
export type Row = {
  id: string; topic: string; status: Status; job: Job | null; pending: number; cost_usd: number;
  created_at: string; compacted: boolean;
};

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${BASE}/research${path}`, {
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

export const research = {
  list: () => req<{ sessions: Row[] }>("GET", ""),
  create: (topic: string) => req<Session>("POST", "", { topic }),
  get: (id: string) => req<Session>("GET", `/${id}`),
  answers: (id: string, answers: Record<string, string>) => req<Session>("POST", `/${id}/answers`, { answers }),
  retry: (id: string) => req<Session>("POST", `/${id}/retry`),
  ask: (id: string, pid: string, text: string) => req<Session>("POST", `/${id}/points/${pid}/ask`, { text }),
  addAngles: (id: string, text: string) => req<Session>("POST", `/${id}/angles`, { text }),
  draft: (id: string) => req<Session>("POST", `/${id}/substack`),
  approve: (id: string, n: number) => req<Session>("POST", `/${id}/proposals/${n}/approve`),
  reject: (id: string, n: number) => req<Session>("POST", `/${id}/proposals/${n}/reject`),
};
