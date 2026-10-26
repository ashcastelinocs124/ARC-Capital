import { useCallback, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/cn";
import { call, Rate, type Detail, type Draft, type Job, type Msg } from "@/components/admin/deskApi";
import EditorChat from "@/components/admin/EditorChat";
import { NotePane, type PaneHandle } from "@/components/admin/NotePreview";

export { BASE, call } from "@/components/admin/deskApi"; // the other admin sections import these from here

// Admin Daily desk: one day's Daily Update agents — read, question, re-run, rebuild, send to Substack. The Editor tab
// shows the note as its Substack post (NotePane) beside a conversation with the Editor (EditorChat): ask it for an
// edit and approve the red/green draft, or edit the text and charts by hand.
const AGENTS = [
  ["macro", "Macro"],
  ["news", "News"],
  ["alt", "Alt data"],
  ["ai", "AI"],
  ["editor", "Editor"],
] as const;
type Agent = (typeof AGENTS)[number][0];
type DayRow = { date: string; headline: string; draft: Draft };

const weekday = (d: string) => new Date(`${d}T12:00:00`).toLocaleDateString("en-US", { weekday: "short" });
const clock = (iso: string) => iso.replace("T", " ").slice(0, 16);

export default function DailyDesk() {
  const [days, setDays] = useState<DayRow[] | null>(null);
  const [day, setDay] = useState<string | null>(null);
  const [agent, setAgent] = useState<Agent>("editor");
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [chats, setChats] = useState<Record<string, Msg[]>>({});
  const [q, setQ] = useState("");
  const [asking, setAsking] = useState(false);
  const [confirmRebuild, setConfirmRebuild] = useState(false);
  const pane = useRef<PaneHandle>(null);

  useEffect(() => {
    call<{ days: DayRow[] }>("/days")
      .then((r) => { setDays(r.days); setDay((d) => d ?? r.days[0]?.date ?? null); })
      .catch((e) => setError(String(e.message ?? e)));
  }, []);

  const load = useCallback((d: string) => call<Detail>(`/${d}`).then(setDetail).catch((e) => setError(String(e.message ?? e))), []);
  useEffect(() => { if (day) { setDetail(null); setConfirmRebuild(false); load(day); } }, [day, load]);

  // while a job runs, poll the day until it finishes (an edit's steps show up as they happen)
  const running = detail?.job?.state === "running";
  useEffect(() => {
    if (!running || !day) return;
    const t = setInterval(() => load(day), 2000);
    return () => clearInterval(t);
  }, [running, day, load]);

  const setJob = (job: Job) => setDetail((d) => (d ? { ...d, job } : d));
  const start = (path: string, body: unknown = {}) => {
    if (!day) return;
    setError(null);
    call<Job>(`/${day}${path}`, body).then(setJob).catch((e) => setError(String(e.message ?? e)));
  };

  const key = `${day}:${agent}`;
  const msgs = chats[key] ?? [];
  const setMsgs = useCallback((k: string) => (f: (m: Msg[]) => Msg[]) => setChats((c) => ({ ...c, [k]: f(c[k] ?? []) })), []);
  const patch = (i: number, u: Partial<Msg>) => setMsgs(key)((m) => m.map((x, j) => (j === i ? { ...x, ...u } : x)));
  const ask = () => {
    const text = q.trim();
    if (!text || !day || asking) return;
    const next = [...msgs, { role: "user" as const, text }];
    setChats((c) => ({ ...c, [key]: next }));
    setQ("");
    setAsking(true);
    call<{ answer: string; call_id: string | null }>(`/${day}/${agent}/chat`, { messages: next.map(({ role, text }) => ({ role, text })) })
      .then((r) => setChats((c) => ({ ...c, [key]: [...next, { role: "agent", text: r.answer, call_id: r.call_id }] })))
      .catch((e) => setChats((c) => ({ ...c, [key]: [...next, { role: "agent", text: `⚠ ${e.message ?? e}` }] })))
      .finally(() => setAsking(false));
  };
  const decided = (approved: boolean, message: string) => {
    const at = new Date().toTimeString().slice(0, 5);
    setMsgs(`${day}:editor`)((m) => [
      ...m,
      { role: "agent", sys: true, text: `You ${approved ? "approved" : "rejected"} the draft · ${at}` },
      { role: "agent", at, text: approved
        ? `Saved. ${message} It goes to Substack when you click Send to Substack.`
        : "Discarded. The note is as it was. Tell me what to do differently and I'll draft it again." },
    ]);
  };

  const mine = detail ? detail.findings.filter((f) => f.agent === agent) : [];
  const job = detail?.job;
  const banner = job && !(agent === "editor" && (job.kind === "edit" || job.kind === "save")); // those report in the tab

  return (
    <div className="space-y-4 p-5 md:p-8">
      {error && <div role="alert" className="rounded-xl border border-danger bg-danger-soft px-4 py-2.5 text-sm text-danger">{error}</div>}

      <div className="flex flex-wrap gap-1.5">
        {days === null && <span className="text-sm text-muted">Loading days…</span>}
        {days?.length === 0 && <span className="text-sm text-muted">No Daily Updates yet.</span>}
        {days?.map((d) => (
          <button key={d.date} type="button" onClick={() => setDay(d.date)} aria-pressed={d.date === day}
            className={cn("rounded-lg border bg-surface px-3 py-1.5 text-left text-xs",
              d.date === day ? "border-accent ring-1 ring-accent" : "border-border hover:border-border-strong")}>
            {weekday(d.date)} {d.date.slice(5)}
            <span className="block text-muted">{d.draft ? "Substack draft" : "no draft"}</span>
          </button>
        ))}
      </div>

      {banner && job && (
        <div role="status" className={cn("rounded-xl px-4 py-2.5 text-sm",
          job.state === "running" ? "bg-warning-soft text-warning" : job.state === "done" ? "bg-accent-soft text-accent" : "bg-danger-soft text-danger")}>
          {job.state === "running" ? `${job.kind} running… (started ${job.at.slice(11, 16)})` : `${job.kind}: ${job.message}`}
        </div>
      )}

      {detail && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border bg-surface px-5 py-4">
            <div className="min-w-0">
              <div className="text-[11px] uppercase tracking-wider text-muted">Daily Update · {detail.date}</div>
              <h3 className="text-lg font-semibold leading-snug">{detail.note.headline}</h3>
              <div className="text-xs text-muted">
                Written {clock(detail.generated_at)}
                {detail.hand_edited_at && <> · edited by hand {detail.hand_edited_at.slice(11, 16)}</>}
                {detail.proposal && <> · <span className="text-warning">a draft is waiting for you</span></>} ·{" "}
                {detail.draft ? (
                  detail.draft.url ? <a className="underline" href={detail.draft.url} target="_blank" rel="noreferrer">Substack draft ↗</a> : "Substack draft saved"
                ) : "not on Substack yet"}
              </div>
            </div>
            {confirmRebuild ? (
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span className="text-warning">Rebuild writes a fresh note and drops your hand edits (they stay in the backup).</span>
                <button type="button" onClick={() => setConfirmRebuild(false)} className="rounded-lg border border-border bg-surface px-3.5 py-2 font-medium">Cancel</button>
                <button type="button" onClick={() => { setConfirmRebuild(false); start("/rebuild"); }}
                  className="rounded-lg border border-danger px-3.5 py-2 font-medium text-danger">Rebuild anyway</button>
              </div>
            ) : (
              <div className="flex gap-2">
                <button type="button" disabled={running} onClick={() => (detail.hand_edited_at ? setConfirmRebuild(true) : start("/rebuild"))}
                  className="rounded-lg border border-border bg-surface px-3.5 py-2 text-sm font-medium hover:border-border-strong disabled:opacity-50">
                  ↻ Rebuild note
                </button>
                <button type="button" disabled={running} onClick={() => start("/substack")}
                  className="rounded-lg bg-accent px-3.5 py-2 text-sm font-medium text-on-accent hover:bg-accent-hover disabled:opacity-50">
                  Send to Substack
                </button>
              </div>
            )}
          </div>

          <div role="group" aria-label="Agent" className="no-scrollbar flex gap-1.5 overflow-x-auto">
            {AGENTS.map(([id, name]) => (
              <button key={id} type="button" onClick={() => setAgent(id)} aria-pressed={id === agent}
                className={cn("flex shrink-0 items-center gap-2 rounded-lg border px-3 py-1.5 text-sm",
                  id === agent ? "border-accent/40 bg-accent-soft font-semibold text-accent" : "border-border bg-surface hover:border-border-strong")}>
                {name}
                <span className="font-normal text-muted">{id === "editor" ? "note" : detail.findings.filter((f) => f.agent === id).length}</span>
              </button>
            ))}
          </div>

          {agent === "editor" ? (
            <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_380px]">
              <NotePane ref={pane} detail={detail} onReload={() => load(detail.date)} onDecided={decided} />
              <EditorChat key={detail.date} detail={detail} msgs={msgs} setMsgs={setMsgs(key)}
                onShowDraft={() => pane.current?.firstChange()} onJob={setJob} />
            </div>
          ) : (
            <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
              <div className="rounded-2xl border border-border bg-surface p-4">
                <h4 className="mb-2 text-sm font-semibold">{AGENTS.find((a) => a[0] === agent)![1]} · what it found</h4>
                {mine.length === 0 ? (
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
                <div className="flex flex-1 flex-col gap-2 overflow-y-auto pb-2 text-sm" aria-live="polite">
                  {msgs.length === 0 && (
                    <div className="rounded-xl bg-surface-2 px-3 py-2 text-text-2">
                      I answer from this day's findings and facts only. Use Re-run to make me look for something new.
                    </div>
                  )}
                  {msgs.map((m, i) => (
                    <div key={i} className={cn("flex max-w-[90%] flex-col", m.role === "user" && "self-end")}>
                      <div className={cn("whitespace-pre-wrap rounded-xl px-3 py-2", m.role === "user" ? "bg-accent-soft" : "bg-surface-2")}>{m.text}</div>
                      {m.role === "agent" && m.call_id && <Rate m={m} onChange={(u) => patch(i, u)} />}
                    </div>
                  ))}
                  {asking && <div className="rounded-xl bg-surface-2 px-3 py-2 text-muted">Thinking…</div>}
                </div>
                <label htmlFor="desk-ask" className="sr-only">Your question or follow-up brief</label>
                <textarea id="desk-ask" value={q} onChange={(e) => setQ(e.target.value)} maxLength={2000}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(); } }}
                  placeholder="Ask about this day, or write a follow-up brief…"
                  className="h-16 w-full resize-none rounded-lg border border-border bg-surface p-2 text-sm" />
                <div className="mt-2 flex gap-2">
                  <button type="button" onClick={ask} disabled={asking || !q.trim()}
                    className="flex-1 rounded-lg border border-border px-3 py-2 text-sm font-medium disabled:opacity-50">Ask</button>
                  <button type="button" onClick={() => { start(`/${agent}/rerun`, { ask: q.trim() }); setQ(""); }}
                    disabled={running || !q.trim()} title="Runs the agent again with this ask; its new findings are added to the day"
                    className="flex-1 rounded-lg border border-border px-3 py-2 text-sm font-medium disabled:opacity-50">Re-run with this ask</button>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
