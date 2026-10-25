import { useCallback, useEffect, useState } from "react";
import { cn } from "@/lib/cn";
import { trade, type Idea, type Row } from "./api";
import { ChartPicker, Checks, Debate, Draft, FrameStrip, Header, Research, Talk } from "./parts";

// /admin → Trade Lab: a trade idea through a bull/bear debate, two talks, research desks and charts to a
// Substack draft. The work runs on Fly; this page starts steps and polls the idea while one runs.
const GROUP = (r: Row) =>
  r.job?.state === "failed" || r.job?.state === "interrupted" || r.status === "awaiting_view" || r.status === "awaiting_charts"
    ? "Needs you" : r.status === "draft_ready" ? "Drafts" : "Running";
const DOT: Record<string, string> = { "Needs you": "bg-warning", Running: "bg-info animate-pulse", Drafts: "bg-accent" };
const LABEL: Record<string, string> = {
  framing: "Framing", debating: "Debating", awaiting_view: "Your view", researching: "Research",
  awaiting_charts: "Pick charts", writing: "Writing", draft_ready: "Draft ready",
};
const STEP_BOXES = [
  ["1 · Frame", "thesis, stand-ins, horizon"], ["2 · Debate", "bull vs bear, 3 turns each"], ["3 · Your view", "it waits for you"],
  ["4 · Research", "2 news desks + technical"], ["5 · Charts", "you pick one per section"], ["6 · Draft", "Substack, Special Topics"],
];

export default function TradeLab() {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [idea, setIdea] = useState<Idea | null>(null);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const fail = (e: unknown) => setError(String((e as Error).message ?? e));

  const refreshList = useCallback(() => { trade.list().then((r) => setRows(r.ideas)).catch(fail); }, []);
  useEffect(() => { refreshList(); }, [refreshList]);
  useEffect(() => {
    if (sel) { setIdea(null); trade.get(sel).then(setIdea).catch(fail); }
  }, [sel]);

  const running = idea?.job?.state === "running" || idea?.job?.state === "queued";
  useEffect(() => {
    if (!running || !sel) return;
    const t = setInterval(() => { trade.get(sel).then(setIdea).catch(fail); refreshList(); }, 3000);
    return () => clearInterval(t);
  }, [running, sel, refreshList]);

  const act = (p: Promise<Idea>) => { setError(null); p.then((i) => { setIdea(i); refreshList(); }).catch(fail); };
  const create = () => {
    const t = text.trim();
    if (t.length < 10) { setError("Write the idea in a sentence or two."); return; }
    setError(null);
    trade.create(t).then((i) => { setText(""); setSel(i.id); setIdea(i); refreshList(); }).catch(fail);
  };

  const groups = ["Needs you", "Running", "Drafts"].map((g) => [g, (rows ?? []).filter((r) => GROUP(r) === g)] as const);
  const job = idea?.job;

  return (
    <div className="grid items-start gap-4 p-5 md:grid-cols-[250px_1fr] md:p-8">
      <aside className="rounded-2xl border border-border bg-surface p-2.5">
        <button onClick={() => { setSel(null); setIdea(null); }} className="mb-2 w-full rounded-lg bg-accent py-2 text-[13px] font-semibold text-on-accent">+ New idea</button>
        {rows === null && <p className="p-2 text-xs text-muted">Loading…</p>}
        {rows?.length === 0 && <p className="p-2 text-xs text-muted">No ideas yet.</p>}
        {groups.map(([g, list]) => list.length > 0 && (
          <div key={g}>
            <div className="px-2 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wider text-muted-2">{g}</div>
            {list.map((r) => (
              <button key={r.id} onClick={() => setSel(r.id)}
                className={cn("grid w-full grid-cols-[10px_1fr] gap-2.5 rounded-xl px-2 py-2 text-left hover:bg-surface-3", sel === r.id && "bg-accent-soft ring-1 ring-accent/30")}>
                <span className={cn("mt-1.5 h-2 w-2 rounded-full", DOT[g])} />
                <span><b className="block text-[13px] font-semibold leading-tight">{r.title}</b>
                  <span className="text-[11.5px] text-muted">{r.job?.state === "failed" ? "Failed · retry" : LABEL[r.status]}</span></span>
              </button>
            ))}
          </div>
        ))}
      </aside>

      <main className="min-w-0 space-y-3.5">
        {error && <div className="rounded-xl border border-danger bg-danger-soft px-4 py-2.5 text-sm text-danger">{error}</div>}
        {!sel && (
          <div className="rounded-2xl border border-border bg-surface p-6">
            <div className="eyebrow">New trade idea</div>
            <h2 className="mt-1 text-2xl font-semibold">What's the trade?</h2>
            <p className="text-sm text-muted">One or two sentences. The framer turns it into a thesis you can test.</p>
            <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)}
              className="mt-3 w-full rounded-xl border border-border-strong bg-surface-2 px-4 py-3 text-[15px] outline-none focus:border-accent" />
            <div className="mt-4 grid grid-cols-2 gap-2 text-xs text-muted md:grid-cols-6">
              {STEP_BOXES.map(([a, b], i) => (
                <div key={a} className={cn("rounded-xl border bg-surface-2 p-2.5", i === 2 || i === 4 ? "border-warning/50" : "border-border")}>
                  <b className={cn("block text-[13px]", i === 2 || i === 4 ? "text-warning" : "text-text")}>{a}</b>{b}</div>
              ))}
            </div>
            <div className="mt-4 flex items-center justify-between gap-3">
              <span className="text-xs text-muted">Steps 1 and 2 take about 4 minutes. Up to $5 per idea.</span>
              <button onClick={create} className="rounded-lg bg-accent px-4 py-2 text-[13px] font-semibold text-on-accent">Run the debate →</button>
            </div>
          </div>
        )}
        {sel && !idea && <p className="text-sm text-muted">Loading the idea…</p>}
        {idea && (
          <>
            <Header idea={idea} />
            {job && (job.state === "failed" || job.state === "interrupted") && (
              <div className="flex items-center justify-between gap-3 rounded-xl border border-danger bg-danger-soft px-4 py-2.5 text-sm text-danger">
                <span>{job.step.replace("_", " ")} {job.state}: {job.message}</span>
                <button onClick={() => act(trade.retry(idea.id))} className="rounded-full border border-danger px-3 py-1 text-xs font-semibold">Retry</button>
              </div>
            )}
            {running && job?.step !== "talk" && (
              <div className="rounded-xl bg-warning-soft px-4 py-2.5 text-sm text-warning">
                {LABEL[idea.status]}… (started {job?.at.slice(11, 16)}). This page updates by itself.
              </div>
            )}
            {idea.frame && <FrameStrip key={idea.updated_at} idea={idea} onIdea={setIdea} />}
            {idea.turns.length > 0 && <Debate idea={idea} />}
            {idea.status === "awaiting_view" && (
              <>
                <Talk idea={idea} n={1} onIdea={setIdea} busy={running} sendLabel="Send to research" onSend={() => act(trade.research(idea.id))} />
                <button onClick={() => act(trade.rerun(idea.id))} className="text-xs text-muted underline">Re-run the debate (about $0.30)</button>
              </>
            )}
            {(idea.status === "researching" || idea.status === "awaiting_charts" || idea.status === "writing") && <Research idea={idea} />}
            {idea.status === "awaiting_charts" && !running && <ChartPicker key={idea.round} idea={idea} onIdea={setIdea} busy={running} />}
            {idea.status === "draft_ready" && (
              <div className="grid items-start gap-3.5 lg:grid-cols-[1.45fr_1fr]">
                <Draft idea={idea} />
                <div className="space-y-3.5">
                  <Checks idea={idea} />
                  <Talk idea={idea} n={2} onIdea={setIdea} busy={running} />
                </div>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
