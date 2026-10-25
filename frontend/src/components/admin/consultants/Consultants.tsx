import { useCallback, useEffect, useState } from "react";
import { cn } from "@/lib/cn";
import { consultants, postChart, type Consultant, type Detail, type HistoryLine, type Row, type Watchlist } from "./api";

// /admin → Consultants: type a topic → a suggested watchlist you can trim or add to → Start. Each consultant builds a
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

const X_TONE = "bg-[rgb(var(--c-cat-jobs)_/_0.14)] text-[rgb(var(--c-cat-jobs))]";

// What went out on X that evening, with its chart: shown above that day's review line.
function Posted({ h, slug }: { h: HistoryLine; slug: string }) {
  return (
    <li className="relative">
      <span aria-hidden="true" className="absolute -left-[27px] top-1 h-3 w-3 rounded-sm border-2 border-[rgb(var(--c-cat-jobs))] bg-[rgb(var(--c-cat-jobs))]" />
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
        <b className="text-text">{h.day}</b>
        <span className={cn("rounded-full px-2.5 py-0.5 text-[11px] font-bold", X_TONE)}>
          Posted on X{h.p_post != null ? ` · ${h.p_post.toFixed(2)}` : ""}
        </span>
      </div>
      <div className="mt-2 rounded-xl border border-border bg-surface-2 p-3">
        <div className="text-[13px]"><b>Ashleyn Castelino</b> <span className="text-muted">@AshleynCas46131</span></div>
        <p className="mt-1 text-[14px] leading-relaxed">{h.post}</p>
        {h.chart_form && (
          <img src={postChart(slug, h.day)} alt={`The ${h.chart_form} chart posted with this post`} loading="lazy"
            className="mt-2.5 w-full rounded-lg border border-border bg-white" />
        )}
      </div>
    </li>
  );
}

function Timeline({ history, slug }: { history: HistoryLine[]; slug: string }) {
  return (
    <section className="rounded-2xl border border-border bg-surface p-5" aria-labelledby="moved">
      <h3 id="moved" className="eyebrow">How the view moved</h3>
      {history.length === 0 && <p className="mt-3 text-sm text-muted">Nothing yet. The first view appears after the first build.</p>}
      <ol className="mt-3 space-y-4 border-l-2 border-border-strong pl-5">
        {history.flatMap((h, i) => [
          h.post ? <Posted key={`${h.day}-post-${i}`} h={h} slug={slug} /> : null,
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
          </li>,
        ])}
      </ol>
    </section>
  );
}

// A pasted page's chip label: site and path, no scheme, cut to fit a chip.
const pageLabel = (u: string) => {
  const s = u.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "");
  return `Page: ${s.length > 44 ? `${s.slice(0, 43)}…` : s}`;
};

// The watchlist's chips (click to remove) and add boxes: a company by ticker, a series by FRED/Yahoo id or a
// web page by link (each build reads the page). Each add is checked by the backend before it becomes a chip.
function WatchlistEditor({ wl, onChange }: { wl: Watchlist; onChange: (w: Watchlist) => void }) {
  const [ticker, setTicker] = useState("");
  const [src, setSrc] = useState<"fred" | "yahoo" | "link">("fred");
  const [sid, setSid] = useState("");
  const [busy, setBusy] = useState<"" | "company" | "series" | "link">("");
  const [error, setError] = useState<{ kind: "company" | "data"; text: string } | null>(null);
  const links = wl.links ?? [];
  const remove = (k: keyof Watchlist, i: number) => onChange({ ...wl, [k]: ((wl[k] ?? []) as unknown[]).filter((_, j) => j !== i) } as Watchlist);
  const add = (kind: "company" | "series" | "link", value: string, clear: () => void) => {
    if (!value.trim() || busy) return;
    setBusy(kind); setError(null);
    consultants.check(kind, value.trim()).then(({ company, series, link }) => {
      if (company) {
        if (wl.companies.some((c) => c.ticker === company.ticker)) throw new Error(`${company.ticker} is already on the watchlist.`);
        onChange({ ...wl, companies: [...wl.companies, company] });
      } else if (series) {
        if (wl.series.includes(series)) throw new Error(`${series} is already on the watchlist.`);
        onChange({ ...wl, series: [...wl.series, series] });
      } else if (link) {
        if (links.includes(link)) throw new Error("That page is already on the watchlist.");
        onChange({ ...wl, links: [...links, link] });
      }
      clear();
    }).catch((e) => setError({ kind: kind === "company" ? "company" : "data", text: String(e.message ?? e) })).finally(() => setBusy(""));
  };
  // a pasted http(s) address is a page whatever the source box says
  const addData = () => {
    const v = sid.trim();
    const isLink = src === "link" || /^https?:\/\//i.test(v);
    add(isLink ? "link" : "series", isLink ? v : v && `${src}:${v}`, () => setSid(""));
  };
  const chip = (label: string, k: keyof Watchlist, i: number, title?: string) => (
    <button key={`${k}-${i}`} type="button" onClick={() => remove(k, i)} disabled={busy !== ""} aria-label={`Remove ${title ?? label}`} title={title}
      className={cn("rounded-full border border-border-strong bg-surface-2 px-3 py-1 text-xs hover:border-danger disabled:opacity-60", FOCUS)}>
      {label} <span aria-hidden="true">✕</span>
    </button>
  );
  const box = cn("w-28 rounded-full border border-dashed border-border-strong bg-surface-2 px-3 py-1 text-xs", FOCUS);
  const addBtn = cn("rounded-full border border-border-strong px-2.5 py-1 text-xs font-semibold text-accent disabled:opacity-50", FOCUS);
  const err = (kind: "company" | "data") =>
    error?.kind === kind && <p role="alert" className="basis-full text-xs text-danger">{error.text}</p>;
  return (
    <dl className="mt-2 grid grid-cols-[110px_1fr] gap-x-3 gap-y-2 text-[13px]">
      <dt className="pt-1 font-semibold text-muted">Companies</dt>
      <dd className="flex flex-wrap items-center gap-1.5">
        {wl.companies.map((c, i) => chip(`${c.name} (${c.ticker})`, "companies", i))}
        <span className="inline-flex items-center gap-1">
          <input value={ticker} onChange={(e) => setTicker(e.target.value)} placeholder="Add ticker" aria-label="Add a company by ticker"
            onKeyDown={(e) => e.key === "Enter" && add("company", ticker, () => setTicker(""))} className={box} />
          <button type="button" onClick={() => add("company", ticker, () => setTicker(""))} disabled={busy !== ""} className={addBtn}>
            {busy === "company" ? "Checking…" : "Add"}
          </button>
        </span>
        {err("company")}
      </dd>
      <dt className="pt-1 font-semibold text-muted">Data</dt>
      <dd className="flex flex-wrap items-center gap-1.5">
        {wl.series.map((s, i) => chip(s, "series", i))}
        {links.map((u, i) => chip(pageLabel(u), "links", i, u))}
        <span className="inline-flex items-center gap-1">
          <select value={src} onChange={(e) => setSrc(e.target.value as "fred" | "yahoo" | "link")} aria-label="Data source"
            className={cn("rounded-full border border-border-strong bg-surface-2 px-2 py-1 text-xs", FOCUS)}>
            <option value="fred">FRED</option>
            <option value="yahoo">Yahoo</option>
            <option value="link">Link</option>
          </select>
          <input value={sid} onChange={(e) => setSid(e.target.value)} placeholder={{ fred: "e.g. DGS10", yahoo: "e.g. ^VIX", link: "Paste a page link" }[src]}
            aria-label="Add a data series id or paste a page link" onKeyDown={(e) => e.key === "Enter" && addData()}
            className={cn(box, src === "link" && "w-64")} />
          <button type="button" onClick={addData} disabled={busy !== ""} className={addBtn}>
            {busy === "series" || busy === "link" ? "Checking…" : "Add"}
          </button>
        </span>
        {err("data")}
      </dd>
      <dt className="pt-1 font-semibold text-muted">News and alt</dt>
      <dd className="flex flex-wrap gap-1.5">{wl.queries.length ? wl.queries.map((q, i) => chip(`News: ${q}`, "queries", i)) : <span className="text-muted">None</span>}</dd>
    </dl>
  );
}

// A running consultant's watchlist: each add or remove saves at once and applies from the next build.
function WatchlistCard({ c }: { c: Consultant }) {
  const [wl, setWl] = useState(c.watchlist);
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  const save = (w: Watchlist) => {
    const prev = wl;
    setWl(w); setNote({ ok: true, text: "Saving…" });
    consultants.setWatchlist(c.slug, w)
      .then(() => setNote({ ok: true, text: "Saved · applies from the next build" }))
      .catch((e) => { setWl(prev); setNote({ ok: false, text: `Not saved: ${String(e.message ?? e)}` }); });
  };
  return (
    <section className="rounded-2xl border border-border bg-surface p-5" aria-labelledby="watchlist">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 id="watchlist" className="eyebrow">Watchlist</h3>
        <span aria-live="polite" className={cn("text-xs", note?.ok === false ? "text-danger" : "text-accent")}>{note?.text}</span>
      </div>
      <WatchlistEditor wl={wl} onChange={save} />
      <p className="mt-3 text-xs text-muted">Changes apply from the next daily build (17:00 New York). Today's facts and the current view stay as they are.</p>
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
          className={cn("rounded-lg border border-border-strong px-4 py-2 text-[13px] font-semibold disabled:opacity-50", FOCUS)}>
          {busy === "plan" ? "Suggesting…" : "Suggest watchlist"}
        </button>
      </div>
      {error && <p role="alert" className="mt-2 text-sm text-danger">{error}</p>}
      {wl && (
        <>
          <div className="eyebrow mt-5">Suggested watchlist (click a chip to remove, or add your own)</div>
          <WatchlistEditor wl={wl} onChange={setWl} />
          <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
            <span className="text-xs text-muted">The first build runs now (a few minutes). Up to $1 a day per consultant.</span>
            <button type="button" onClick={start} disabled={busy !== ""}
              className={cn("rounded-lg bg-accent px-4 py-2 text-[13px] font-semibold text-on-accent disabled:opacity-50", FOCUS)}>
              {busy === "start" ? "Starting…" : "Start consultant"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

// The posting knob: Off (the default) posts nothing; Auto lets the evening review post one notable point a
// day to X, with a chart the Post Writer picks (agents/consultants/post.py).
function PostKnob({ on, onSet }: { on: boolean; onSet: (on: boolean) => void }) {
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-border-strong py-1 pl-3 pr-1 text-xs font-semibold">
      Post to X
      <span role="group" aria-label="Post to X" className="inline-flex rounded-full bg-surface-3 p-0.5">
        {[false, true].map((v) => (
          <button key={String(v)} type="button" aria-pressed={on === v} onClick={() => on !== v && onSet(v)}
            className={cn("rounded-full px-3 py-0.5 text-xs font-semibold", FOCUS,
              on === v ? (v ? "bg-accent text-on-accent" : "bg-border-strong text-text") : "text-muted hover:text-text")}>
            {v ? "Auto" : "Off"}
          </button>
        ))}
      </span>
    </span>
  );
}

const KNOB_NOTE = {
  off: "Off: this consultant never posts. Its view still feeds the Daily Update's ARC view.",
  on: "Auto: when the evening review finds a notable new point (a fresh development, a turning point or a surprise, not a recap), it posts one analysis post to X with a chart the agent picks. At most one a day; no links; every number must be one of its facts.",
};

// The last evening review's scores in words; the post question is only asked while the knob is on.
function reviewLine(h: HistoryLine | undefined, knob: boolean): string | null {
  if (!h || h.kind !== "daily" || h.p_thesis == null) return null;
  const parts = [`thesis changed (${h.p_thesis.toFixed(2)})`, `worth remembering (${(h.p_memory ?? 0).toFixed(2)})`];
  if (h.p_post != null) parts.push(`notable point to post (${h.p_post.toFixed(2)})${h.post ? ": posted" : ""}`);
  const tail = h.p_post == null && !knob ? ". Posting was off, so the post question wasn't asked." : ".";
  return `${h.day}: ${parts.join(" · ")}${tail}`;
}

function ConsultantView({ d, onChange, onDeleted }: { d: Detail; onChange: () => void; onDeleted: () => void }) {
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const c = d.consultant;
  const act = (p: Promise<unknown>, after = onChange) => { setError(null); p.then(after).catch((e) => setError(String(e.message ?? e))); };
  const t = d.thesis;
  return (
    <div className="space-y-3.5">
      <div className="rounded-2xl border border-border bg-surface px-5 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">{c.topic}</h2>
          <p className="text-xs text-muted">Started {c.created} · status: {c.status}{t ? ` · view v${t.version}` : ""}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <PostKnob on={c.post_to_x} onSet={(v) => act(consultants.setPostToX(c.slug, v))} />
          {c.status === "failed" && (
            <button type="button" onClick={() => act(consultants.build(c.slug))} className={cn("rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-on-accent", FOCUS)}>Build now</button>
          )}
          {c.status === "paused"
            ? <button type="button" onClick={() => act(consultants.resume(c.slug))} className={cn("rounded-lg border border-border-strong px-3 py-1.5 text-xs font-semibold", FOCUS)}>Resume</button>
            : <button type="button" onClick={() => act(consultants.pause(c.slug))} className={cn("rounded-lg border border-border-strong px-3 py-1.5 text-xs font-semibold", FOCUS)}>Pause</button>}
          {confirm
            ? <>
                <button type="button" onClick={() => act(consultants.remove(c.slug), onDeleted)} className={cn("rounded-full bg-danger px-3 py-1.5 text-xs font-semibold text-surface", FOCUS)}>Yes, delete</button>
                <button type="button" onClick={() => setConfirm(false)} className={cn("rounded-lg border border-border-strong px-3 py-1.5 text-xs font-semibold", FOCUS)}>Cancel</button>
              </>
            : <button type="button" onClick={() => setConfirm(true)} className={cn("rounded-full border border-danger/50 px-3 py-1.5 text-xs font-semibold text-danger", FOCUS)}>Delete</button>}
        </div>
      </div>
      <p className="mt-2 text-xs text-muted">{c.post_to_x ? KNOB_NOTE.on : KNOB_NOTE.off}</p>
      </div>
      {c.status === "failed" && c.error && <div role="alert" className="rounded-xl border border-danger bg-danger-soft px-4 py-2.5 text-sm text-danger">Last build failed: {c.error}</div>}
      {c.status === "building" && <div className="rounded-xl bg-warning-soft px-4 py-2.5 text-sm text-warning">First build running. This page updates by itself.</div>}
      {error && <div role="alert" className="rounded-xl border border-danger bg-danger-soft px-4 py-2.5 text-sm text-danger">{error}</div>}
      <WatchlistCard key={c.slug} c={c} />
      {d.log.notes.length > 0 && (
        <div className="rounded-xl border border-warning/50 bg-warning-soft px-4 py-2.5 text-sm">
          <b className="text-warning">Today ({d.log.day}, ${d.log.cost_usd.toFixed(2)} spent):</b>
          <ul className="mt-1 list-disc pl-5 text-text-2">{d.log.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
        </div>
      )}
      <div className="grid items-start gap-3.5 lg:grid-cols-[1fr_1.15fr]">
        <Timeline history={d.history} slug={c.slug} />
        <div className="space-y-3.5">
          <section className="rounded-2xl border border-border bg-surface p-5" aria-labelledby="happening">
            <h3 id="happening" className="eyebrow">What's happening</h3>
            <p className="mt-2 text-[16px] leading-relaxed">{t ? t.happening.text : "No view yet."}</p>
            {reviewLine(d.history[0], c.post_to_x) && (
              <>
                <h4 className="eyebrow mt-4">Last evening review</h4>
                <p className="mt-1 text-[13px] leading-relaxed text-text-2">{reviewLine(d.history[0], c.post_to_x)}</p>
              </>
            )}
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
    <div className="grid items-start gap-4 p-5 md:grid-cols-[250px_1fr] md:p-8">
      <aside className="rounded-2xl border border-border bg-surface p-2.5" aria-label="Consultants">
        <button type="button" onClick={() => { setSel(null); setD(null); }}
          className={cn("mb-2 w-full rounded-lg bg-accent py-2 text-[13px] font-semibold text-on-accent", FOCUS)}>+ New consultant</button>
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
                <span>
                  <b className="block text-[13px] font-semibold leading-tight">{r.topic}</b>
                  {r.post_to_x && <span className="mr-1.5 rounded-full bg-accent-soft px-1.5 text-[10.5px] font-bold text-accent">Posts to X</span>}
                  <span className="text-[11.5px] text-muted">{rowNote(r)}</span>
                </span>
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
