import { useState } from "react";
import { cn } from "@/lib/cn";
import { STATIC } from "@/api/client";

// Shared by the admin desks: where the admin API lives, one fetch helper, and the 👍 / 👎 on an answer.
// Locally it talks to `ckm serve`; on the public site /api/admin/live/* is forwarded to the Fly machine
// (frontend/vercel.json), behind the same admin password.
export const BASE = STATIC ? "/api/admin/live" : "/api/admin/desk";

export async function call<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (r.status === 401 && STATIC) {
    location.href = "/admin/login?expired=1&next=/admin"; // the 12-hour session ended while the page was open
  }
  if (!r.ok) {
    const j = await r.json().catch(() => null);
    throw new Error((j && typeof j.detail === "string" && j.detail) || `${r.status} ${r.statusText}`);
  }
  return r.json();
}

// A chat line. On the Editor tab a line can also be your edit request (tag), a step-by-step work log bound to the
// day's edit job by its start time (work), or an event such as "You approved the draft" (sys).
export type Msg = {
  role: "user" | "agent"; text: string; call_id?: string | null; rating?: "up" | "down"; saved?: boolean;
  tag?: "edit" | "ask"; sys?: boolean; work?: { at: string; snap?: Job }; at?: string;
};

// One background job per day (endpoints/admin_desk.py): an edit also reports its steps and what it did.
export type EditResult = {
  kind: "change" | "new" | "none"; reason: string; agent: string | null; added: string[]; message: string;
  summary?: Summary;
};
export type Job = {
  kind: string; state: "running" | "done" | "failed"; message: string; at: string; steps?: string[]; result?: EditResult;
};
export type Summary = { added: number[]; dropped: string[]; changed: number[]; takeaways: number; headline: boolean; text: string };

export type NoteView = { consultant: string; text: string; topic?: string };
export type NoteItem = { rank: number; title: string; body: string; finding_ids: string[]; chart?: string | null; view?: NoteView | null };
export type Note = { headline: string; takeaways: string[]; items: NoteItem[] };
export type Exhibit = { n: number; finding_id: string; item: number | null; title: string; file: string; at?: number | null; after?: number | null };
export type Proposal = {
  day: string; ask: string; kind: "change" | "new"; agent: string | null; added: string[]; summary: Summary;
  created_at: string; note: Note; exhibits: Exhibit[]; calendar: string[];
};
export type Draft = { id: number; url: string | null } | null;
export type Finding = { id: string; agent: string; claim: string; fact_ids: string[]; source_title: string; source_url: string };
export type Detail = {
  date: string; generated_at: string; note: Note; findings: Finding[]; exhibits: Exhibit[]; calendar: string[];
  hand_edited_at: string | null; proposal: Proposal | null; draft: Draft; job: Job | null;
};
// What Save sends: the text from the preview (bold as **…**) and where each chart sits.
export type HandEdit = {
  headline: string; takeaways: string[];
  items: { rank: number; title: string; body: string; view: string | null }[];
  charts: { file: string; at: number; after: number | null }[];
};

// 👍 saves at once; 👎 opens an optional "right answer" box. Both go to the benchmark (POST /rate).
export function Rate({ m, onChange }: { m: Msg; onChange: (u: Partial<Msg>) => void }) {
  const [better, setBetter] = useState("");
  const [err, setErr] = useState("");
  const send = (rating: "up" | "down", text = "") =>
    call("/rate", { call_id: m.call_id, rating, better: text })
      .then(() => { setErr(""); onChange({ rating, saved: true }); })
      .catch((e) => setErr(String(e.message ?? e)));
  const btn = (on: boolean, down: boolean) =>
    cn("rounded-full border px-2 py-0.5 text-xs", on ? (down ? "border-danger text-danger" : "border-accent bg-accent-soft text-accent") : "border-border text-text-2 hover:border-border-strong");
  return (
    <div className="mt-1 text-[11.5px] text-muted">
      <div className="flex items-center gap-1.5">
        <button className={btn(m.rating === "up", false)} onClick={() => send("up")}>👍</button>
        <button className={btn(m.rating === "down", true)} onClick={() => onChange({ rating: "down", saved: false })}>👎</button>
        <span className={cn(m.saved && "text-accent")}>
          {m.saved ? (m.rating === "up" ? "rated 👍 · saved" : "rated 👎 · saved") : m.rating === "down" ? "add the right answer (optional), then Save" : "rate this answer"}
        </span>
      </div>
      {m.rating === "down" && !m.saved && (
        <div className="mt-1.5 rounded-lg border border-border bg-surface-2 p-2">
          <textarea value={better} onChange={(e) => setBetter(e.target.value)} maxLength={4000}
            placeholder="What should the answer have been? Saved as the right answer for testing new models."
            className="h-16 w-full resize-none rounded-md border border-border bg-surface p-1.5 text-[13px] text-text" />
          <div className="mt-1 flex justify-end">
            <button onClick={() => send("down", better)} className="rounded-md border border-border px-3 py-1 text-xs font-medium text-text">Save</button>
          </div>
        </div>
      )}
      {err && <div className="mt-1 text-danger">{err}</div>}
    </div>
  );
}
