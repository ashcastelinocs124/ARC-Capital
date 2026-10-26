import { useEffect, useRef, useState } from "react";
import { PenLine, ArrowUp } from "lucide-react";
import { cn } from "@/lib/cn";
import { btn } from "@/components/admin/shell";
import { call, Rate, type Detail, type Job, type Msg } from "@/components/admin/deskApi";

// The Daily desk's Editor tab, right side: a conversation with the Editor. Edit sends a request to the Edit Router
// (POST /{day}/edit): its reply is a live work log of the job's steps, then a summary and a link to the draft that
// NotePane shows on the left. Ask is Desk Chat on the note (POST /{day}/editor/chat), answered with fact ids.

const SUGGEST: [string, "edit" | "ask", string][] = [
  ["Tighten an item", "edit", "Shorten item 3 to two paragraphs and keep its key figures"],
  ["Add a point", "edit", "Add a point on "],
  ["Why is an item here?", "ask", "Why is item 5 in today's note?"],
];
const ANALYST = /(Macro analyst|News analyst|Alt data analyst|AI analyst)/;
const hhmm = (iso?: string) => (iso ? iso.slice(11, 16) : new Date().toTimeString().slice(0, 5));

// an analyst named in a step shows as a chip, so the hand-off reads at a glance
function Step({ text }: { text: string }) {
  return (
    <>
      {text.split(ANALYST).map((part, i) =>
        ANALYST.test(part) ? (
          <span key={i} className="rounded-full border border-border-strong bg-surface-3 px-1.5 text-[11px] font-semibold text-text">{part}</span>
        ) : part,
      )}
    </>
  );
}

function WorkLog({ job, onShowDraft, hasDraft }: { job: Job; onShowDraft: () => void; hasDraft: boolean }) {
  const r = job.result;
  const kind = job.state === "failed" ? "Failed" : !r ? "Working…" : r.kind === "new" ? "New point" : r.kind === "none" ? "Nothing found" : "Change";
  const steps = job.steps ?? [];
  return (
    <>
      <div className="mb-1.5 rounded-xl border border-border bg-surface-2 px-3 py-2.5 text-[12.5px]">
        <div className={cn("text-[10.5px] font-bold uppercase tracking-wider",
          kind === "New point" ? "text-accent" : kind === "Change" ? "text-warning" : kind === "Working…" ? "text-muted" : "text-danger")}>
          {kind}
        </div>
        <ol className="mt-2">
          {steps.map((s, i) => {
            const now = job.state === "running" && i === steps.length - 1;
            return (
              <li key={i} className="relative pb-2 pl-5 text-text-2 last:pb-0">
                <i aria-hidden="true" className={cn("absolute left-[3px] top-[5px] h-2 w-2 rounded-full",
                  now ? "bg-warning motion-safe:animate-pulse" : job.state === "failed" && i === steps.length - 1 ? "bg-danger" : "bg-accent")} />
                {i < steps.length - 1 && <i aria-hidden="true" className="absolute bottom-0 left-[6.5px] top-[15px] w-px bg-border-strong" />}
                <span className={cn(now && "font-semibold text-text")}><Step text={s} /></span>
              </li>
            );
          })}
          {steps.length === 0 && <li className="text-muted">Starting…</li>}
        </ol>
      </div>
      {job.state !== "running" && (
        <div className="rounded-[4px_12px_12px_12px] bg-surface-3 px-3 py-2.5 leading-relaxed">
          {job.state === "failed" ? `That didn't work: ${job.message}` : r?.kind === "none" ? r.message
            : `I've drafted it on the left. ${r?.message ?? ""} Approve it there, or tell me what to change.`}
        </div>
      )}
      {job.state === "done" && r && r.kind !== "none" && hasDraft && (
        <button type="button" className={cn(btn.secondary, "mt-2 h-7 text-xs")} onClick={onShowDraft}>Review the draft on the left</button>
      )}
    </>
  );
}

export default function EditorChat({ detail, msgs, setMsgs, onShowDraft, onJob }: {
  detail: Detail;
  msgs: Msg[];
  setMsgs: (f: (m: Msg[]) => Msg[]) => void;
  onShowDraft: () => void;
  onJob: (job: Job) => void;
}) {
  const day = detail.date;
  const [mode, setMode] = useState<"edit" | "ask">("edit");
  const [text, setText] = useState("");
  const [asking, setAsking] = useState(false);
  const box = useRef<HTMLTextAreaElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const job = detail.job;
  const working = job?.kind === "edit" && job.state === "running";

  // keep a finished edit's log in the chat after the job slot moves on (another job, a reload)
  const unsaved = !!job && job.kind === "edit" && job.state !== "running" && msgs.some((x) => x.work?.at === job.at && !x.work.snap);
  useEffect(() => {
    if (!unsaved || !job) return;
    setMsgs((m) => m.map((x) => (x.work?.at === job.at && !x.work.snap ? { ...x, work: { at: job.at, snap: job } } : x)));
  }, [unsaved, job, setMsgs]);
  useEffect(() => { list.current?.scrollTo({ top: list.current.scrollHeight }); }, [msgs, job?.steps?.length, job?.state]);

  const patch = (i: number, u: Partial<Msg>) => setMsgs((m) => m.map((x, j) => (j === i ? { ...x, ...u } : x)));
  const send = () => {
    const q = text.trim();
    if (!q || asking || working) return;
    setText("");
    const mine: Msg = { role: "user", text: q, tag: mode, at: hhmm() };
    if (mode === "edit") {
      setMsgs((m) => [...m, mine]);
      call<Job>(`/${day}/edit`, { ask: q })
        .then((j) => { onJob(j); setMsgs((m) => [...m, { role: "agent", text: "", work: { at: j.at }, at: hhmm(j.at) }]); })
        .catch((e) => setMsgs((m) => [...m, { role: "agent", text: `That didn't start: ${e.message ?? e}`, at: hhmm() }]));
      return;
    }
    const history = [...msgs.filter((m) => !m.work && !m.sys && m.tag !== "edit"), mine];
    setMsgs((m) => [...m, mine]);
    setAsking(true);
    call<{ answer: string; call_id: string | null }>(`/${day}/editor/chat`, { messages: history.map(({ role, text }) => ({ role, text })) })
      .then((r) => setMsgs((m) => [...m, { role: "agent", text: r.answer, call_id: r.call_id, at: hhmm() }]))
      .catch((e) => setMsgs((m) => [...m, { role: "agent", text: `That didn't work: ${e.message ?? e}`, at: hhmm() }]))
      .finally(() => setAsking(false));
  };

  const status = working ? ["Working on your edit…", "bg-warning motion-safe:animate-pulse"] : asking ? ["Thinking…", "bg-warning motion-safe:animate-pulse"]
    : detail.proposal ? ["Draft ready", "bg-warning"] : ["Ready", "bg-accent"];
  const findings = detail.findings.length;

  return (
    <section aria-label="Editor agent" className="flex h-[min(78vh,760px)] min-h-[520px] flex-col overflow-hidden rounded-2xl border border-border bg-surface lg:sticky lg:top-4">
      <header className="flex items-center gap-2.5 border-b border-border px-3.5 py-3">
        <span aria-hidden="true" className="grid h-9 w-9 flex-none place-items-center rounded-[10px] border border-accent/35 bg-accent-soft text-accent"><PenLine size={18} /></span>
        <div className="min-w-0">
          <b className="block text-sm">Editor</b>
          <span className="text-[11.5px] text-muted">Daily Update · gpt-6-sol</span>
        </div>
        <span role="status" className="ml-auto flex items-center gap-1.5 whitespace-nowrap rounded-full border border-border px-2.5 py-0.5 text-[11.5px] text-text-2">
          <i aria-hidden="true" className={cn("h-[7px] w-[7px] rounded-full", status[1])} />{status[0]}
        </span>
      </header>
      <div aria-label="What the Editor is working on" className="flex flex-wrap gap-1.5 border-b border-border px-3.5 py-2 text-[11px] text-muted">
        {[new Date(`${day}T12:00:00`).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" }),
          `${detail.note.items.length} items`, `${findings} findings`,
          detail.draft ? "Substack draft saved" : "Not on Substack yet",
          ...(detail.hand_edited_at ? ["Edited by hand"] : [])].map((c) => (
          <span key={c} className="rounded-full border border-border px-2 py-px">{c}</span>
        ))}
      </div>

      <div ref={list} aria-live="polite" className="flex flex-1 flex-col gap-3.5 overflow-y-auto p-3.5 text-[13px]">
        <Line who="agent" at={hhmm(detail.generated_at)}>
          <div className="rounded-[4px_12px_12px_12px] bg-surface-3 px-3 py-2.5 leading-relaxed">
            I wrote this note from the desk's {findings} findings. Tell me what to change or add and I'll draft it on the left for you to approve, or ask me why I wrote something.
          </div>
          {msgs.length === 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {SUGGEST.map(([label, m, q]) => (
                <button key={label} type="button" onClick={() => { setMode(m); setText(q); box.current?.focus(); }}
                  className="rounded-full border border-border px-2.5 py-1 text-xs text-text-2 hover:border-border-strong hover:text-text">
                  {label}
                </button>
              ))}
            </div>
          )}
        </Line>
        {msgs.map((m, i) =>
          m.sys ? (
            <div key={i} className="self-center rounded-full border border-border px-2.5 py-0.5 text-[11px] text-muted">{m.text}</div>
          ) : m.work ? (
            <Line key={i} who="agent" at={m.at}>
              {m.work.snap || (job && job.at === m.work.at) ? (
                <WorkLog job={m.work.snap ?? job!} onShowDraft={onShowDraft} hasDraft={!!detail.proposal} />
              ) : <div className="text-muted">This edit's log is no longer here.</div>}
            </Line>
          ) : (
            <Line key={i} who={m.role} at={m.at} tag={m.tag}>
              <div className={cn("whitespace-pre-wrap px-3 py-2.5 leading-relaxed",
                m.role === "user" ? "rounded-[12px_4px_12px_12px] bg-accent-soft" : "rounded-[4px_12px_12px_12px] bg-surface-3")}>{m.text}</div>
              {m.role === "agent" && m.call_id && <Rate m={m} onChange={(u) => patch(i, u)} />}
            </Line>
          ),
        )}
        {asking && (
          <Line who="agent">
            <div role="img" aria-label="The Editor is typing" className="inline-flex gap-1 rounded-[4px_12px_12px_12px] bg-surface-3 px-3 py-3">
              {[0, 1, 2].map((d) => <i key={d} className="h-1.5 w-1.5 rounded-full bg-muted motion-safe:animate-pulse" style={{ animationDelay: `${d * 150}ms` }} />)}
            </div>
          </Line>
        )}
      </div>

      <div className="mx-3 rounded-xl border border-border bg-surface-2 p-2 focus-within:border-accent/70 focus-within:ring-2 focus-within:ring-accent/20">
        <label htmlFor={`editor-box-${day}`} className="sr-only">Message to the Editor</label>
        <textarea id={`editor-box-${day}`} ref={box} value={text} maxLength={2000} onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
          placeholder={mode === "edit" ? "Tell the Editor what to change or add…" : "Ask the Editor about this note…"}
          className="h-14 w-full resize-none bg-transparent px-1 text-[13px] text-text outline-none placeholder:text-muted" />
        <div className="flex items-center gap-2">
          <div role="group" aria-label="Message type" className="inline-flex overflow-hidden rounded-lg border border-border">
            {(["edit", "ask"] as const).map((m) => (
              <button key={m} type="button" aria-pressed={mode === m} onClick={() => setMode(m)}
                className={cn("px-3 py-1 text-xs", mode === m ? "bg-accent-soft font-semibold text-accent" : "text-text-2 hover:text-text")}>
                {m === "edit" ? "Edit" : "Ask"}
              </button>
            ))}
          </div>
          <span className="ml-auto text-[11px] text-muted">↵ send · ⇧↵ new line</span>
          <button type="button" onClick={send} disabled={!text.trim() || asking || working} aria-label="Send to the Editor"
            className="grid h-8 w-8 place-items-center rounded-[9px] bg-accent text-on-accent disabled:opacity-40">
            <ArrowUp size={16} />
          </button>
        </div>
      </div>
      <p className="px-3.5 pb-3 pt-2 text-[11px] text-muted">Edits come back as drafts for your approval. Substack changes only when you click Send to Substack.</p>
    </section>
  );
}

function Line({ who, at, tag, children }: { who: "user" | "agent"; at?: string; tag?: "edit" | "ask"; children: React.ReactNode }) {
  const me = who === "user";
  return (
    <div className={cn("flex items-start gap-2", me && "flex-row-reverse")}>
      <span aria-hidden="true" className={cn("grid h-[26px] w-[26px] flex-none place-items-center rounded-lg text-[10.5px] font-bold",
        me ? "bg-surface-3 text-text-2" : "bg-accent-soft text-accent")}>{me ? "AC" : "E"}</span>
      <div className={cn("min-w-0 max-w-[88%]", me && "flex flex-col items-end")}>
        <div className="mb-1 text-[11px] text-muted">
          {me ? "You" : <b className="text-text-2">Editor</b>}{at ? ` · ${at}` : ""}
          {tag && <span className="ml-1.5 rounded border border-border-strong px-1.5 text-[10px] font-bold uppercase tracking-wide text-text-2">{tag === "edit" ? "Edit request" : "Question"}</span>}
        </div>
        {children}
      </div>
    </div>
  );
}
