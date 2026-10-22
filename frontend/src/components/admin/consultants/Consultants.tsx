import { useCallback, useEffect, useState } from "react";
import { cn } from "@/lib/cn";
import { consultants, type Detail, type HistoryLine, type Row, type Watchlist } from "./api";

// /admin → Consultants: type a topic → a suggested watchlist you can trim → Start. Each consultant builds a
// daily file of cited facts and keeps a thesis (what's happening, what could happen) that the Daily Update
// uses for its ARC view. Layout: the approved mockup's frame C (docs/superpowers/specs/2026-10-22-topic-consultants/).
const FOCUS = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent";
const today = () => new Date().toLocaleDateString("en-CA"); // YYYY-MM-DD in local time

function groupOf(r: Row): string {
  if (r.status === "building" || r.status === "failed") return "Starting / failed";
  if (r.status === "paused") return "Paused";
  return r.last?.day === today() && (r.last.verdict === "updated" || r.last.verdict === "started")
    ? "View changed today"
    : "View held";
}
const GROUPS = ["View changed today", "View held", "Starting / failed", "Paused"];
const DOT: Record<string, string> = {
  "View changed today": "bg-accent", "View held": "bg-muted-2", "Starting / failed": "bg-warning", Paused: "bg-border-strong",
};

function rowNote(r: Row): string {
  if (r.status === "building") return "First build running…";
  if (r.status === "failed") return "Build failed · retry";
  const asked = r.asks_today ? ` · asked ${r.asks_today}×` : "";
  return `${r.facts_today} facts today${asked}`;
}

// Verdict chips carry a word, never color alone.
function Verdict({ h }: { h: HistoryLine }) {
  const p = h.p_thesis != null ? ` · ${h.p_thesis.toFixed(2)}` : "";
  const [label, tone] =
    h.verdict === "updated" ? [`Updated${p}`, "bg-accent-soft text-accent"]
    : h.verdict === "held" ? [`Held${p}`, "bg-surface-3 text-text-2"]
    : h.verdict === "started" ? ["Started", "bg-accent-soft text-accent"]
    : h.verdict === "week" ? ["Week review", "bg-[rgb(var(--c-cat-jobs)_/_0.14)] text-[rgb(var(--c-cat-jobs))]"]
    : ["Skipped", "bg-warning-soft text-warning"];
  return <span className={cn("rounded-full px-2.5 py-0.5 text-[11px] font-bold", tone)}>{label}</span>;
}

function Timeline({ history }: { history: HistoryLine[] }) {
  return (
    <section className="rounded-2xl border border-border bg-surface p-5" aria-labelledby="moved">
      <h3 id="moved" className="eyebrow">How the view moved</h3>
      {history.length === 0 && <p className="mt-3 text-sm text-muted">Nothing yet. The first view appears after the first build.</p>}
      <ol className="mt-3 space-y-4 border-l-2 border-border-strong pl-5">
        {history.map((h, i) => (
          <li key={`${h.day}-${h.kind}-${i}`} className="relative">
            <span aria-hidden="true" className={cn("absolute -left-[27px] top-1 h-3 w-3 rounded-full border-2",
              h.verdict === "updated" || h.verdict === "started" ? "border-accent bg-accent"
              : h.verdict === "week" ? "rounded-sm border-[rgb(var(--c-cat-jobs))] bg-[rgb(var(--c-cat-jobs))]"
              : "border-muted-2 bg-surface")} />
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted"><b className="text-text">{h.day}</b><Verdict h={h} /></div>
            <p className="mt-1 text-[13.5px] leading-relaxed">
              {h.kind === "weekly"
                ? <>{h.moved.length ? `Moved to long-term: ${h.moved.join("; ")}. ` : "Nothing moved to long-term. "}
                    {h.deleted.length ? `Dropped as out of date: ${h.deleted.join("; ")}. ` : ""}{h.reason}</>
                : h.reason || (h.verdict === "held" ? "No change to the view." : "")}
            </p>
          </li>
        ))}
      </ol>
    </section>
  );
}

function NewConsultant({ onCreated }: { onCreated: (r: Row) => void }) {
  const [topic, setTopic] = useState("");
  const [wl, setWl] = useState<Watchlist | null>(null);
  const [busy, setBusy] = useState<"" | "plan" | "start">("");
  const [error, setError] = useState<string | null>(null);
  const t = topic.trim();
  const plan = () => {
    if (t.length < 3) return setError("Type a topic of at least 3 characters.");
    setBusy("plan"); setError(null);
    consultants.plan(t).then((r) => setWl(r.watchlist)).catch((e) => setError(String(e.message ?? e))).finally(() => setBusy(""));
  };
  const start = () => {
    if (!wl) return;
    setBusy("start"); setError(null);
    consultants.create(t, wl).then(onCreated).catch((e) => setError(String(e.message ?? e))).finally(() => setBusy(""));
  };
  const remove = (k: keyof Watchlist, i: number) =>
    wl && setWl({ ...wl, [k]: (wl[k] as unknown[]).filter((_, j) => j !== i) } as Watchlist);
  const chip = (label: string, k: keyof Watchlist, i: number) => (
    <button key={`${k}-${i}`} type="button" onClick={() => remove(k, i)} aria-label={`Remove ${label}`}
      className={cn("rounded-full border border-border-strong bg-surface-2 px-3 py-1 text-xs hover:border-danger", FOCUS)}>
      {label} <span aria-hidden="true">✕</span>
    </button>
  );
  return (
    <div className="rounded-2xl border border-border bg-surface p-6">
      <div className="eyebrow">New consultant</div>
      <p className="mt-1 text-sm text-muted">It builds a file on this topic every day and advises the Daily Update, Weekly Deep Dive, Deep Research and Trade Lab.</p>
      <label htmlFor="consultant-topic" className="mt-4 block text-[13px] font-semibold">Topic</label>
      <div className="mt-1.5 flex flex-wrap gap-2">
        <input id="consultant-topic" value={topic} onChange={(e) => { setTopic(e.target.value); setWl(null); }}
          onKeyDown={(e) => e.key === "Enter" && plan()} placeholder="AI models and chips"
          className={cn("min-w-0 flex-1 rounded-xl border border-border-strong bg-surface-2 px-4 py-2.5 text-[15px]", FOCUS)} />
        <button type="button" onClick={plan} disabled={busy !== ""}
          className={cn("rounded-full border border-border-strong px-4 py-2 text-[13px] font-semibold disabled:opacity-50", FOCUS)}>
          {busy === "plan" ? "Suggesting…" : "Suggest watchlist"}
        </button>
      </div>
      {error && <p role="alert" className="mt-2 text-sm text-danger">{error}</p>}
      {wl && (
        <>
          <div className="eyebrow mt-5">Suggested watchlist (click to remove)</div>
          <dl className="mt-2 grid grid-cols-[110px_1fr] gap-x-3 gap-y-2 text-[13px]">
            <dt className="pt-1 font-semibold text-muted">Companies</dt>
            <dd className="flex flex-wrap gap-1.5">{wl.companies.length ? wl.companies.map((c, i) => chip(`${c.name} (${c.ticker})`, "companies", i)) : <span className="text-muted">None for this topic</span>}</dd>
            <dt className="pt-1 font-semibold text-muted">Data</dt>
            <dd className="flex flex-wrap gap-1.5">{wl.series.length ? wl.series.map((s, i) => chip(s, "series", i)) : <span className="text-muted">None</span>}</dd>
            <dt className="pt-1 font-semibold text-muted">News and alt</dt>
            <dd className="flex flex-wrap gap-1.5">{wl.queries.map((q, i) => chip(`News: ${q}`, "queries", i))}</dd>
          </dl>
          <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
            <span className="text-xs text-muted">The first build runs now (a few minutes). Up to $1 a day per consultant.</span>
            <button type="button" onClick={start} disabled={busy !== ""}
              className={cn("rounded-full bg-accent px-4 py-2 text-[13px] font-semibold text-on-accent disabled:opacity-50", FOCUS)}>
              {busy === "start" ? "Starting…" : "Start consultant"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function ConsultantView({ d, onChange, onDeleted }: { d: Detail; onChange: () => void; onDeleted: () => void }) {
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const c = d.consultant;
  const act = (p: Promise<unknown>, after = onChange) => { setError(null); p.then(after).catch((e) => setError(String(e.message ?? e))); };
  const t = d.thesis;
  return (
    <div className="space-y-3.5">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border bg-surface px-5 py-3">
        <div>
          <h2 className="font-serif text-xl font-bold">{c.topic}</h2>
          <p className="text-xs text-muted">Started {c.created} · status: {c.status}{t ? ` · view v${t.version}` : ""}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {c.status === "failed" && (
            <button type="button" onClick={() => act(consultants.build(c.slug))} className={cn("rounded-full bg-accent px-3 py-1.5 text-xs font-semibold text-on-accent", FOCUS)}>Build now</button>
          )}
          {c.status === "paused"
            ? <button type="button" onClick={() => act(consultants.resume(c.slug))} className={cn("rounded-full border border-border-strong px-3 py-1.5 text-xs font-semibold", FOCUS)}>Resume</button>
            : <button type="button" onClick={() => act(consultants.pause(c.slug))} className={cn("rounded-full border border-border-strong px-3 py-1.5 text-xs font-semibold", FOCUS)}>Pause</button>}
          {confirm
            ? <>
                <button type="button" onClick={() => act(consultants.remove(c.slug), onDeleted)} className={cn("rounded-full bg-danger px-3 py-1.5 text-xs font-semibold text-surface", FOCUS)}>Yes, delete</button>
                <button type="button" onClick={() => setConfirm(false)} className={cn("rounded-full border border-border-strong px-3 py-1.5 text-xs font-semibold", FOCUS)}>Cancel</button>
              </>
            : <button type="button" onClick={() => setConfirm(true)} className={cn("rounded-full border border-danger/50 px-3 py-1.5 text-xs font-semibold text-danger", FOCUS)}>Delete</button>}
        </div>
      </div>
      {c.status === "failed" && c.error && <div role="alert" className="rounded-xl border border-danger bg-danger-soft px-4 py-2.5 text-sm text-danger">Last build failed: {c.error}</div>}
      {c.status === "building" && <div className="rounded-xl bg-warning-soft px-4 py-2.5 text-sm text-warning">First build running. This page updates by itself.</div>}
      {error && <div role="alert" className="rounded-xl border border-danger bg-danger-soft px-4 py-2.5 text-sm text-danger">{error}</div>}
      <div className="grid items-start gap-3.5 lg:grid-cols-[1fr_1.15fr]">
        <Timeline history={d.history} />
        <div className="space-y-3.5">
          <section className="rounded-2xl border border-border bg-surface p-5" aria-labelledby="happening">
            <h3 id="happening" className="eyebrow">What's happening</h3>
            <p className="mt-2 font-serif text-[16px] leading-relaxed">{t ? t.happening.text : "No view yet."}</p>
          </section>
          <section className="rounded-2xl border border-border bg-surface p-5" aria-labelledby="today">
            <h3 id="today" className="eyebrow">
              {d.today.day} · {d.today.facts.length} facts · asked {d.today.asks.length} {d.today.asks.length === 1 ? "time" : "times"}
            </h3>
            <ul className="mt-2 divide-y divide-border text-[13px]">
              {d.today.facts.map((f) => (
                <li key={f.id} className="grid grid-cols-[minmax(0,1fr)_auto] gap-3 py-1.5">
                  <span>{f.text}</span>
                  <a href={f.source_url} target="_blank" rel="noreferrer" className={cn("max-w-[160px] truncate text-xs text-accent underline", FOCUS)} title={f.source_title}>{f.source_title}</a>
                </li>
              ))}
            </ul>
            {d.today.asks.length > 0 && (
              <div className="mt-3 space-y-1 text-[13px]">
                {d.today.asks.map((a) => <p key={a.at + a.asker}><b>{a.asker}</b>: “{a.question}”</p>)}
              </div>
            )}
          </section>
          <section className="rounded-2xl border border-border bg-surface p-5" aria-labelledby="could">
            <h3 id="could" className="eyebrow">What could happen</h3>
            {t ? (
              <ol className="mt-2 list-decimal space-y-1.5 pl-5 text-[13.5px] leading-relaxed">
                <li><b>Leaning to:</b> {t.lean.text}</li>
                <li><b>The other path:</b> {t.alternative.text}</li>
                <li><b>What would change our mind:</b> {t.change_mind.text}</li>
              </ol>
            ) : <p className="mt-2 text-sm text-muted">No view yet.</p>}
          </section>
          <section className="rounded-2xl border border-border bg-surface p-5" aria-labelledby="memory">
            <h3 id="memory" className="eyebrow">Memory · {d.memory.short.length} this week · {d.memory.long.length} long-term</h3>
            <ul className="mt-2 space-y-1 text-[13px]">
              {[...d.memory.short.map((n) => ["This week", n] as const), ...d.memory.long.map((n) => ["Long-term", n] as const)].map(([tier, n]) => (
                <li key={tier + n.title}><span className="text-xs text-muted">{tier} · </span><b>{n.title}</b>: {n.text}</li>
              ))}
            </ul>
          </section>
        </div>
      </div>
    </div>
  );
}

export default function Consultants() {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [d, setD] = useState<Detail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fail = (e: unknown) => setError(String((e as Error).message ?? e));

  const refreshList = useCallback(() => { consultants.list().then((r) => setRows(r.consultants)).catch(fail); }, []);
  const refresh = useCallback(() => {
    refreshList();
    if (sel) consultants.get(sel).then(setD).catch(fail);
  }, [sel, refreshList]);
  useEffect(() => { refreshList(); }, [refreshList]);
  useEffect(() => {
    setD(null);
    if (sel) consultants.get(sel).then(setD).catch(fail);
  }, [sel]);
  const building = d?.consultant.status === "building";
  useEffect(() => {
    if (!building) return;
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, [building, refresh]);

  const groups = GROUPS.map((g) => [g, (rows ?? []).filter((r) => groupOf(r) === g)] as const);
  return (
    <div className="grid items-start gap-4 px-4 pb-8 md:grid-cols-[250px_1fr] md:px-8">
      <aside className="rounded-2xl border border-border bg-surface p-2.5" aria-label="Consultants">
        <button type="button" onClick={() => { setSel(null); setD(null); }}
          className={cn("mb-2 w-full rounded-full bg-accent py-2 text-[13px] font-semibold text-on-accent", FOCUS)}>+ New consultant</button>
        {rows === null && <p className="p-2 text-xs text-muted">Loading…</p>}
        {rows?.length === 0 && <p className="p-2 text-xs text-muted">No consultants yet.</p>}
        {groups.map(([g, list]) => list.length > 0 && (
          <div key={g}>
            <div className="px-2 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wider text-muted">{g}</div>
            {list.map((r) => (
              <button key={r.slug} type="button" onClick={() => setSel(r.slug)} aria-current={sel === r.slug ? "true" : undefined}
                className={cn("grid w-full grid-cols-[10px_1fr] gap-2.5 rounded-xl px-2 py-2 text-left hover:bg-surface-3", FOCUS,
                  sel === r.slug && "bg-accent-soft ring-1 ring-accent/30")}>
                <span aria-hidden="true" className={cn("mt-1.5 h-2 w-2 rounded-full", DOT[g])} />
                <span><b className="block text-[13px] font-semibold leading-tight">{r.topic}</b><span className="text-[11.5px] text-muted">{rowNote(r)}</span></span>
              </button>
            ))}
          </div>
        ))}
      </aside>
      <section className="min-w-0 space-y-3.5" aria-label={d ? d.consultant.topic : "New consultant"}>
        {error && <div role="alert" className="rounded-xl border border-danger bg-danger-soft px-4 py-2.5 text-sm text-danger">{error}</div>}
        {!sel && <NewConsultant onCreated={(r) => { refreshList(); setSel(r.slug); }} />}
        {sel && !d && <p className="text-sm text-muted">Loading the consultant…</p>}
        {d && <ConsultantView d={d} onChange={refresh} onDeleted={() => { setSel(null); setD(null); refreshList(); }} />}
      </section>
    </div>
  );
}
