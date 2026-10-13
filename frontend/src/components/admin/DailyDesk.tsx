import { useCallback, useEffect, useState } from "react";
import { cn } from "@/lib/cn";
import { STATIC } from "@/api/client";

// Admin Daily desk: one day's Morning Note agents — read, question, re-run, rebuild, send to Substack.
// Locally it talks to `ckm serve`; on the public site /api/admin/live/* is forwarded to the Fly machine
// (frontend/vercel.json), behind the same admin password.
export const BASE = STATIC ? "/api/admin/live" : "/api/admin/desk";
const AGENTS = [
  ["macro", "Macro"],
  ["news", "News"],
  ["alt", "Alt data"],
  ["ai", "AI"],
  ["editor", "Editor"],
] as const;
type Agent = (typeof AGENTS)[number][0];

type Draft = { id: number; url: string | null } | null;
type Job = { kind: string; state: "running" | "done" | "failed"; message: string; at: string } | null;
type DayRow = { date: string; headline: string; draft: Draft };
type Finding = { id: string; agent: string; claim: string; fact_ids: string[]; source_title: string; source_url: string };
type Detail = {
  date: string;
  generated_at: string;
  note: { headline: string; takeaways: string[]; items: { rank: number; title: string; finding_ids: string[] }[] };
  findings: Finding[];
  draft: Draft;
  job: Job;
};
type Msg = { role: "user" | "agent"; text: string };

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

const weekday = (d: string) => new Date(`${d}T12:00:00`).toLocaleDateString("en-US", { weekday: "short" });

export default function DailyDesk() {
  const [days, setDays] = useState<DayRow[] | null>(null);
  const [day, setDay] = useState<string | null>(null);
  const [agent, setAgent] = useState<Agent>("macro");
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [chats, setChats] = useState<Record<string, Msg[]>>({});
  const [q, setQ] = useState("");
  const [asking, setAsking] = useState(false);

  useEffect(() => {
    call<{ days: DayRow[] }>("/days")
      .then((r) => { setDays(r.days); setDay((d) => d ?? r.days[0]?.date ?? null); })
      .catch((e) => setError(String(e.message ?? e)));
  }, []);

  const load = useCallback((d: string) => call<Detail>(`/${d}`).then(setDetail).catch((e) => setError(String(e.message ?? e))), []);
  useEffect(() => { if (day) { setDetail(null); load(day); } }, [day, load]);

  // while a job runs, poll the day until it finishes
  const running = detail?.job?.state === "running";
  useEffect(() => {
    if (!running || !day) return;
    const t = setInterval(() => load(day), 3000);
    return () => clearInterval(t);
  }, [running, day, load]);

  const start = (path: string, body: unknown = {}) => {
    if (!day) return;
    setError(null);
    call<Job>(`/${day}${path}`, body)
      .then((job) => setDetail((d) => (d ? { ...d, job } : d)))
      .catch((e) => setError(String(e.message ?? e)));
  };

  const key = `${day}:${agent}`;
  const msgs = chats[key] ?? [];
  const ask = () => {
    const text = q.trim();
    if (!text || !day || asking) return;
    const next = [...msgs, { role: "user" as const, text }];
    setChats((c) => ({ ...c, [key]: next }));
    setQ("");
    setAsking(true);
    call<{ answer: string }>(`/${day}/${agent}/chat`, { messages: next })
      .then((r) => setChats((c) => ({ ...c, [key]: [...next, { role: "agent", text: r.answer }] })))
      .catch((e) => setChats((c) => ({ ...c, [key]: [...next, { role: "agent", text: `⚠ ${e.message ?? e}` }] })))
      .finally(() => setAsking(false));
  };

  const mine = detail ? (agent === "editor" ? [] : detail.findings.filter((f) => f.agent === agent)) : [];
  const job = detail?.job;

  return (
    <div className="space-y-4 px-4 pb-8 md:px-8">
      {error && <div className="rounded-xl border border-danger bg-danger-soft px-4 py-2.5 text-sm text-danger">{error}</div>}

      <div className="flex flex-wrap gap-1.5">
        {days === null && <span className="text-sm text-muted">Loading days…</span>}
        {days?.length === 0 && <span className="text-sm text-muted">No Morning Notes yet.</span>}
        {days?.map((d) => (
          <button key={d.date} onClick={() => setDay(d.date)}
            className={cn("rounded-lg border bg-surface px-3 py-1.5 text-left text-xs",
              d.date === day ? "border-accent ring-1 ring-accent" : "border-border hover:border-border-strong")}>
            {weekday(d.date)} {d.date.slice(5)}
            <span className="block text-muted">{d.draft ? "Substack draft" : "no draft"}</span>
          </button>
        ))}
      </div>

      {job && (
        <div className={cn("rounded-xl px-4 py-2.5 text-sm",
          job.state === "running" ? "bg-warning-soft text-warning" : job.state === "done" ? "bg-accent-soft text-accent" : "bg-danger-soft text-danger")}>
          {job.state === "running" ? `${job.kind} running… (started ${job.at.slice(11, 16)})` : `${job.kind}: ${job.message}`}
        </div>
      )}

      {detail && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border bg-surface px-5 py-4">
            <div className="min-w-0">
              <div className="text-[11px] uppercase tracking-wider text-muted">Morning Note · {detail.date}</div>
              <h3 className="font-serif text-lg font-semibold leading-snug">{detail.note.headline}</h3>
              <div className="text-xs text-muted">
                Written {detail.generated_at.replace("T", " ").slice(0, 16)} ·{" "}
                {detail.draft ? (
                  detail.draft.url ? <a className="underline" href={detail.draft.url} target="_blank" rel="noreferrer">Substack draft ↗</a> : "Substack draft saved"
                ) : "not on Substack yet"}
              </div>
            </div>
            <div className="flex gap-2">
              <button disabled={running} onClick={() => start("/rebuild")}
                className="rounded-lg border border-border bg-surface px-3.5 py-2 text-sm font-medium hover:border-border-strong disabled:opacity-50">
                ↻ Rebuild note
              </button>
              <button disabled={running} onClick={() => start("/substack")}
                className="rounded-lg bg-accent px-3.5 py-2 text-sm font-medium text-on-accent hover:bg-accent-hover disabled:opacity-50">
                Send to Substack
              </button>
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-[180px_1fr_340px]">
            <div className="flex gap-1.5 overflow-x-auto lg:flex-col">
              {AGENTS.map(([id, name]) => (
                <button key={id} onClick={() => setAgent(id)}
                  className={cn("flex shrink-0 justify-between gap-3 rounded-lg border px-3 py-2 text-sm",
                    id === agent ? "border-accent/40 bg-accent-soft font-semibold text-accent" : "border-border bg-surface")}>
                  {name}
                  <span className="font-normal text-muted">{id === "editor" ? "note" : detail.findings.filter((f) => f.agent === id).length}</span>
                </button>
              ))}
            </div>

            <div className="rounded-2xl border border-border bg-surface p-4">
              <h4 className="mb-2 text-sm font-semibold">
                {agent === "editor" ? `The note for ${detail.date}` : `${AGENTS.find((a) => a[0] === agent)![1]} · what it found`}
              </h4>
              {agent === "editor" ? (
                <ol className="space-y-2 text-sm">
                  {detail.note.takeaways.map((t, i) => <li key={`t${i}`} className="text-text-2">• {t}</li>)}
                  {detail.note.items.map((it) => (
                    <li key={it.rank} className="border-t border-border pt-2">
                      <span className="font-medium">{it.rank}. {it.title}</span>
                      <span className="ml-2 font-mono text-[11px] text-muted">{it.finding_ids.join(", ")}</span>
                    </li>
                  ))}
                </ol>
              ) : mine.length === 0 ? (
                <p className="text-sm text-muted">No findings from this agent on this day.</p>
              ) : (
                <ul className="divide-y divide-border text-sm">
                  {mine.map((f) => (
                    <li key={f.id} className="py-2">
                      <span className="font-mono text-[11px] text-muted">{f.id} · {f.fact_ids.join(", ")}</span>
                      <div>{f.claim}</div>
                      {f.source_url.startsWith("http") && (
                        <a href={f.source_url} target="_blank" rel="noreferrer" className="text-xs text-muted underline">{f.source_title}</a>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="flex h-[460px] flex-col rounded-2xl border border-border bg-surface p-4">
              <h4 className="mb-2 text-sm font-semibold">Ask {AGENTS.find((a) => a[0] === agent)![1]} about {detail.date}</h4>
              <div className="flex flex-1 flex-col gap-2 overflow-y-auto pb-2 text-sm">
                {msgs.length === 0 && (
                  <div className="rounded-xl bg-surface-2 px-3 py-2 text-text-2">
                    I answer from this day's findings and facts only. Use Re-run to make me look for something new.
                  </div>
                )}
                {msgs.map((m, i) => (
                  <div key={i} className={cn("max-w-[90%] whitespace-pre-wrap rounded-xl px-3 py-2",
                    m.role === "user" ? "self-end bg-accent-soft" : "bg-surface-2")}>{m.text}</div>
                ))}
                {asking && <div className="rounded-xl bg-surface-2 px-3 py-2 text-muted">Thinking…</div>}
              </div>
              <textarea value={q} onChange={(e) => setQ(e.target.value)} maxLength={2000}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(); } }}
                placeholder="Ask about this day, or write a follow-up brief…"
                className="h-16 w-full resize-none rounded-lg border border-border bg-surface p-2 text-sm" />
              <div className="mt-2 flex gap-2">
                <button onClick={ask} disabled={asking || !q.trim()}
                  className="flex-1 rounded-lg border border-border px-3 py-2 text-sm font-medium disabled:opacity-50">Ask</button>
                <button onClick={() => { start(`/${agent}/rerun`, { ask: q.trim() }); setQ(""); }}
                  disabled={agent === "editor" || running || !q.trim()}
                  title={agent === "editor" ? "Use Rebuild note for the Editor" : "Runs the agent again with this ask; its new findings are added to the day"}
                  className="flex-1 rounded-lg border border-border px-3 py-2 text-sm font-medium disabled:opacity-50">Re-run with this ask</button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
