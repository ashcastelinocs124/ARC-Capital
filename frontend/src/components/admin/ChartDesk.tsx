import { useCallback, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/cn";
import { C } from "@/lib/theme";
import { PageIntro } from "@/components/layout/PageIntro";
import { BASE, call } from "@/components/admin/DailyDesk";

// Admin Charts (src/castelino/agents/chart_desk.py): talk to the chart agent about any idea, or run
// one prompt on several models side by side and vote for the best. The model only names forms and
// series; code draws every chart from FRED / Yahoo. Its models are its own (config.yaml chart_desk).
type Chart = {
  form: string; series: string[]; window_days: number; threshold: number | null; title: string; why: string;
  file: string | null; error: string | null;
};
type Reply = {
  model: string; state: "running" | "done" | "failed"; text: string; charts: Chart[]; seconds: number; usd: number;
  error: string | null;
};
type Run = {
  id: string; kind: "chat" | "compare"; title: string; created_at: string; updated_at: string;
  turns: { ask: string; at: string; replies: Reply[] }[]; vote: string | null;
};
type Row = { id: string; kind: "chat" | "compare"; title: string; updated_at: string; turns: number; models: string[]; vote: string | null };
type Overview = { chat_model: string; compare_models: string[]; compare_default: string[]; scoreboard: Record<string, number>; runs: Row[] };

const png = (run: Run, c: Chart) => `${BASE}/charts/${run.id}/png/${c.file}`;
const busy = (run: Run | null) => !!run?.turns.some((t) => t.replies.some((r) => r.state === "running"));
const short = (m: string) => m.split("/").pop()!;
const money = (x: number) => (x > 0 && x < 0.001 ? "<$0.001" : `$${x.toFixed(3)}`);
const when = (iso: string) =>
  new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });

function useTicker(on: boolean) {
  const [s, setS] = useState(0);
  useEffect(() => {
    if (!on) return void setS(0);
    const t = setInterval(() => setS((x) => x + 1), 1000);
    return () => clearInterval(t);
  }, [on]);
  return s;
}

function ProviderChip({ model }: { model: string }) {
  const color = model.includes("/") ? C.ai : C.accent;
  return (
    <span className="rounded-full px-2 py-0.5 text-[10.5px] font-semibold"
      style={{ color, background: `color-mix(in srgb, ${color} 14%, transparent)` }}>
      {model.includes("/") ? "OpenRouter · open weights" : "OpenAI"}
    </span>
  );
}

function Zoom({ src, onClose }: { src: string | null; onClose: () => void }) {
  if (!src) return null;
  return (
    <button type="button" onClick={onClose} className="fixed inset-0 z-50 grid cursor-zoom-out place-items-center bg-black/80 p-6">
      <img src={src} alt="" className="max-h-[88vh] max-w-[88vw] rounded-lg bg-white" />
    </button>
  );
}

function Failed({ c }: { c: Chart }) {
  return (
    <div className="self-start rounded-lg border border-dashed border-danger/50 px-2.5 py-2 text-xs text-danger">
      ✕ <b>{c.form}</b> on <span className="font-mono">{c.series.join(", ")}</span>: not drawn. {c.error}
    </div>
  );
}

function ReplyView({ run, r, onZoom }: { run: Run; r: Reply; onZoom: (s: string) => void }) {
  const tick = useTicker(r.state === "running");
  const drawn = r.charts.filter((c) => c.file).length;
  return (
    <div className="flex gap-2.5">
      <div className="grid h-[30px] w-[30px] shrink-0 place-items-center rounded-full border border-border-strong text-[9px] font-extrabold text-accent">ARC</div>
      <div className="min-w-0 flex-1">
        {r.state === "running" ? (
          <p className="text-[13px] italic text-muted">
            <span className="font-mono not-italic">{short(r.model)}</span> is picking forms and series, then code fetches FRED / Yahoo and
            draws… {tick}s
          </p>
        ) : (
          <>
            <div className="mb-2 text-[11.5px] text-muted">
              Chart agent · <span className="font-mono">{r.model}</span> · {r.charts.length} proposed, {drawn} drawn · {r.seconds} s · {money(r.usd)}
            </div>
            {r.error && <p className="text-sm text-danger">The model call failed: {r.error}</p>}
            {r.text && <p className="mb-2.5 text-sm leading-relaxed text-text-2">{r.text}</p>}
            <div className="grid gap-3 md:grid-cols-2">
              {r.charts.map((c, i) =>
                c.file ? (
                  <div key={i} className="overflow-hidden rounded-[10px] border border-border bg-surface-2">
                    <button type="button" className="block w-full cursor-zoom-in" onClick={() => onZoom(png(run, c))}>
                      <img src={png(run, c)} alt={c.title} loading="lazy" className="block w-full bg-white" />
                    </button>
                    <div className="grid gap-1.5 px-3 py-2.5">
                      <p className="text-[12.5px] leading-snug text-text-2">{c.why}</p>
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="pill">{c.form.replace("_", " ")}</span>
                        {c.series.map((s) => <span key={s} className="rounded-full bg-surface-3 px-2 py-0.5 font-mono text-[10.5px] text-text-2">{s}</span>)}
                        <a href={png(run, c)} download className="ml-auto text-xs font-semibold text-accent">PNG ↓</a>
                      </div>
                    </div>
                  </div>
                ) : (
                  <Failed key={i} c={c} />
                ),
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function Chat({ ov, reload, onZoom }: { ov: Overview; reload: () => void; onZoom: (s: string) => void }) {
  const threads = ov.runs.filter((r) => r.kind === "chat");
  const [id, setId] = useState<string | null>(threads[0]?.id ?? null);
  const [run, setRun] = useState<Run | null>(null);
  const [ask, setAsk] = useState("");
  const [model, setModel] = useState(ov.chat_model);
  const [err, setErr] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const models = [...new Set([ov.chat_model, ...ov.compare_models])];

  useEffect(() => {
    if (!id) return void setRun(null);
    call<Run>(`/charts/${id}`).then(setRun, (e: Error) => setErr(e.message));
  }, [id]);
  useEffect(() => {
    if (!busy(run)) return;
    const t = setTimeout(() => call<Run>(`/charts/${run!.id}`).then(setRun).then(() => reload(), () => {}), 2500);
    return () => clearTimeout(t);
  }, [run, reload]);
  useEffect(() => {
    box.current?.scrollTo({ top: box.current.scrollHeight });
  }, [run]);

  const send = async () => {
    if (ask.trim().length < 3 || busy(run)) return;
    setErr(null);
    try {
      const r = await call<Run>("/charts/chat", { ask, model, run_id: id });
      setAsk("");
      setRun(r);
      setId(r.id);
      reload();
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[250px_1fr]">
      <div className="card flex flex-col gap-1 self-start p-2.5">
        <button type="button" onClick={() => { setId(null); setRun(null); }}
          className="mb-1.5 rounded-full border border-border-strong px-4 py-2 text-[13px] font-semibold text-text-2 hover:text-text">
          + New idea
        </button>
        {threads.length === 0 && <p className="px-2 py-1 text-xs text-muted">No threads yet.</p>}
        {threads.map((t) => (
          <button key={t.id} type="button" onClick={() => setId(t.id)}
            className={cn("rounded-[10px] px-3 py-2 text-left text-[13px] leading-snug", t.id === id ? "bg-surface-3 font-semibold text-text" : "text-text-2 hover:bg-surface-2")}>
            {t.title}
            <span className="mt-0.5 block text-[11px] font-normal text-muted-2">
              {when(t.updated_at)} · {t.turns} message{t.turns === 1 ? "" : "s"} · {t.models.map(short).join(", ")}
            </span>
          </button>
        ))}
      </div>
      <div className="card flex min-h-[560px] flex-col">
        <div ref={box} className="flex max-h-[70vh] flex-1 flex-col gap-5 overflow-y-auto p-5">
          {!run && (
            <p className="m-auto max-w-md text-center text-sm text-muted">
              Describe an idea, e.g. &ldquo;Is the yen carry trade unwinding? Japan vs the US.&rdquo; The agent proposes up to 4 charts;
              follow up to change one. Replies take from about 15 seconds to a few minutes, depending on the model.
            </p>
          )}
          {run?.turns.map((t, i) => (
            <div key={i} className="flex flex-col gap-4">
              <div className="max-w-[70%] self-end rounded-[14px_14px_4px_14px] border border-accent/30 bg-accent-soft px-3.5 py-2.5 text-sm leading-relaxed">{t.ask}</div>
              <ReplyView run={run} r={t.replies[0]} onZoom={onZoom} />
            </div>
          ))}
        </div>
        {err && <p className="px-4 pb-1 text-xs text-danger">{err}</p>}
        <div className="flex items-end gap-2.5 border-t border-border p-3">
          <textarea value={ask} onChange={(e) => setAsk(e.target.value)} rows={2}
            onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) send(); }}
            placeholder={run ? "Ask for a change or a new chart…" : "Describe your idea…"}
            className="flex-1 resize-none rounded-[10px] border border-border bg-surface-2 px-3 py-2.5 text-sm text-text" />
          <div className="grid gap-1.5">
            <select value={model} onChange={(e) => setModel(e.target.value)} className="rounded-lg border border-border bg-surface-2 px-2 py-1.5 font-mono text-xs text-text">
              {models.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
            <button type="button" onClick={send} disabled={busy(run) || ask.trim().length < 3}
              className="rounded-full bg-accent px-4 py-2 text-[13px] font-bold text-on-accent disabled:opacity-50">
              {busy(run) ? "Drawing…" : "Send"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Compare({ ov, reload, onZoom }: { ov: Overview; reload: () => void; onZoom: (s: string) => void }) {
  const runs = ov.runs.filter((r) => r.kind === "compare");
  const [id, setId] = useState<string | null>(runs[0]?.id ?? null);
  const [run, setRun] = useState<Run | null>(null);
  const [ask, setAsk] = useState("");
  const [picked, setPicked] = useState<string[]>(ov.compare_default);
  const [extra, setExtra] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const tick = useTicker(busy(run));

  useEffect(() => {
    if (!id) return void setRun(null);
    call<Run>(`/charts/${id}`).then(setRun, (e: Error) => setErr(e.message));
  }, [id]);
  useEffect(() => {
    if (!busy(run)) return;
    const t = setTimeout(() => call<Run>(`/charts/${run!.id}`).then(setRun).then(() => reload(), () => {}), 2500);
    return () => clearTimeout(t);
  }, [run, reload]);

  const models = [...picked, ...extra.split(/[\s,]+/).filter(Boolean)];
  const start = async () => {
    setErr(null);
    try {
      const r = await call<Run>("/charts/compare", { ask, models });
      setRun(r);
      setId(r.id);
      reload();
    } catch (e) {
      setErr((e as Error).message);
    }
  };
  const vote = async (model: string) => {
    if (!run) return;
    setRun(await call<Run>(`/charts/${run.id}/vote`, { model }));
    reload();
  };
  const toggle = (m: string) => setPicked((p) => (p.includes(m) ? p.filter((x) => x !== m) : [...p, m]));
  const score = Object.entries(ov.scoreboard);
  const top = Math.max(1, ...score.map(([, n]) => n));
  const replies = run?.turns[0]?.replies ?? [];

  return (
    <div className="space-y-4">
      <div className="card grid gap-3 p-4">
        <textarea value={ask} onChange={(e) => setAsk(e.target.value)} rows={2} placeholder="One prompt for every model, e.g. Is the yen carry trade unwinding? Japan vs the US."
          className="w-full resize-none rounded-[10px] border border-border bg-surface-2 px-3 py-2.5 text-sm text-text" />
        <div className="flex flex-wrap items-center gap-2">
          {ov.compare_models.map((m) => (
            <label key={m} className={cn("inline-flex cursor-pointer items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-xs text-text-2",
              m === ov.chat_model ? "border-accent/50" : "border-border")}>
              <input type="checkbox" checked={picked.includes(m)} onChange={() => toggle(m)} />
              {m}
              {!m.includes("/") && <span className="pill">Trade Lab's</span>}
              {m === ov.chat_model && <span className="pill">chat</span>}
            </label>
          ))}
          <input value={extra} onChange={(e) => setExtra(e.target.value)} placeholder="+ any OpenRouter model id"
            className="w-64 rounded-full border border-dashed border-border-strong bg-surface-2 px-3 py-1.5 font-mono text-xs text-text" />
          <span className="flex-1" />
          <button type="button" onClick={start} disabled={ask.trim().length < 3 || models.length === 0 || busy(run)}
            className="rounded-full bg-accent px-4 py-2 text-[13px] font-bold text-on-accent disabled:opacity-50">
            Run on {models.length} model{models.length === 1 ? "" : "s"}
          </button>
        </div>
        {err && <p className="text-xs text-danger">{err}</p>}
        {runs.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
            Earlier runs:
            <select value={id ?? ""} onChange={(e) => setId(e.target.value)} className="max-w-md rounded-lg border border-border bg-surface-2 px-2 py-1 text-xs text-text">
              {runs.map((r) => <option key={r.id} value={r.id}>{when(r.updated_at)} · {r.title}{r.vote ? ` · ★ ${short(r.vote)}` : ""}</option>)}
            </select>
          </div>
        )}
      </div>

      <div className="card flex flex-wrap items-center gap-3 px-4 py-2.5 text-[13px] text-text-2">
        <b className="text-text">Your votes, {score.reduce((a, [, n]) => a + n, 0)} runs:</b>
        {score.length === 0 && <span className="text-muted">none yet. Click ★ Best under the model you prefer.</span>}
        {score.map(([m, n]) => (
          <span key={m} className="inline-flex items-center">
            <span className="font-mono text-xs">{short(m)}</span>
            <i className="mx-1.5 inline-block h-[7px] rounded bg-accent" style={{ width: `${(n / top) * 60}px` }} />
            {n}
          </span>
        ))}
      </div>

      {run && (
        <>
          <p className="text-sm text-text-2"><b className="text-text">Prompt:</b> {run.turns[0]?.ask}{busy(run) && <span className="text-muted"> · running {tick}s</span>}</p>
          <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(auto-fit, minmax(220px, 1fr))` }}>
            {replies.map((r) => {
              const drawn = r.charts.filter((c) => c.file);
              const best = run.vote === r.model;
              return (
                <div key={r.model} className={cn("card flex flex-col gap-2.5 p-3", best && "ring-2 ring-accent")}>
                  <h3 className="break-all font-mono text-[12.5px] font-semibold text-text">{r.model}</h3>
                  <div><ProviderChip model={r.model} /></div>
                  {r.state === "running" ? (
                    <p className="text-xs italic text-muted">Running…</p>
                  ) : (
                    <>
                      <div className="text-[11.5px] leading-relaxed text-muted">
                        <b className="text-text-2">{drawn.length} of {r.charts.length}</b> charts drew · {r.seconds} s · {money(r.usd)}
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {drawn.map((c, i) => <span key={i} className="rounded-full bg-surface-3 px-2 py-0.5 text-[10.5px] text-text-2">{c.form.replace("_", " ")}</span>)}
                      </div>
                      {r.error && <p className="text-xs text-danger">✕ {r.error}</p>}
                      <div className="grid gap-2">
                        {drawn.map((c, i) => (
                          <button key={i} type="button" onClick={() => onZoom(png(run, c))} className="cursor-zoom-in">
                            <img src={png(run, c)} alt={c.title} loading="lazy" className="block w-full rounded-md bg-white" />
                          </button>
                        ))}
                      </div>
                      {r.charts.filter((c) => c.error).map((c, i) => <Failed key={i} c={c} />)}
                      <button type="button" onClick={() => vote(r.model)} disabled={r.state !== "done"}
                        className={cn("mt-auto rounded-full px-4 py-2 text-[13px] font-bold disabled:opacity-40",
                          best ? "bg-accent text-on-accent" : "text-text-2 ring-1 ring-border-strong hover:text-text")}>
                        {best ? "★ Your pick" : "★ Best"}
                      </button>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

export default function ChartDesk() {
  const [mode, setMode] = useState<"chat" | "compare">("chat");
  const [ov, setOv] = useState<Overview | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [zoom, setZoom] = useState<string | null>(null);
  const reload = useCallback(() => {
    call<Overview>("/charts").then(setOv, (e: Error) => setErr(e.message));
  }, []);
  useEffect(() => {
    reload();
  }, [reload]);

  return (
    <div className="space-y-4 px-4 pb-8 md:px-8">
      <div className="grid gap-4 md:grid-cols-[1fr_auto] md:items-center">
        <PageIntro kicker="Admin · Chart agent" title="Charts for your ideas">
          Tell the chart agent an idea and it proposes charts from Trade Lab&apos;s 12 forms, drawn by code from live FRED and Yahoo data.
          Compare models runs one prompt on several models side by side. Its models are its own: nothing here changes another workflow.
        </PageIntro>
        <div className="flex w-fit rounded-full border border-border bg-surface-2 p-[3px]">
          {(["chat", "compare"] as const).map((m) => (
            <button key={m} type="button" onClick={() => setMode(m)}
              className={cn("rounded-full px-4 py-1.5 text-[13px] font-semibold", m === mode ? "bg-surface text-text ring-1 ring-border" : "text-text-2 hover:text-text")}>
              {m === "chat" ? "Chat" : "Compare models"}
            </button>
          ))}
        </div>
      </div>
      {err && <div className="card p-4 text-sm text-danger">Couldn&apos;t load the chart desk: {err}</div>}
      {!ov && !err && <p className="text-sm text-muted">Loading…</p>}
      {ov && (mode === "chat" ? <Chat ov={ov} reload={reload} onZoom={setZoom} /> : <Compare ov={ov} reload={reload} onZoom={setZoom} />)}
      <Zoom src={zoom} onClose={() => setZoom(null)} />
    </div>
  );
}
