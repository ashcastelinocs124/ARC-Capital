import { useCallback, useEffect, useMemo, useState } from "react";
import { CartesianGrid, LabelList, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { cn } from "@/lib/cn";
import { research, type AgentRun, type Chart, type Fact, type Proposal, type Row, type Session } from "./api";

// /admin → Research: a topic → the clarifier → up to 8 research agents → Claude writes the points → you question
// any point on the editor desk (approved mockup: docs/superpowers/specs/2026-10-19-general-deep-research/).
// The work runs on Fly; this page starts steps and polls while one runs.
const STEPS = ["Clarify", "Plan", "Research", "Check", "Write", "Edit"];
const STEP_BOXES: [string, string, boolean][] = [
  ["1 · Clarify", "up to 3 questions", true],
  ["2 · Plan", "the Lead picks up to 8 angles", false],
  ["3 · Research", "agents · web, X, FRED, Yahoo, BLS", false],
  ["4 · Check", "critic: gaps? one more round", false],
  ["5 · Write", "Claude writes the points", false],
  ["6 · Edit", "question any point", true],
];
// X facts in the AI category colour (index.css), not a new hex
const XTONE = "text-[rgb(var(--c-cat-ai))] bg-[rgb(var(--c-cat-ai)_/_0.12)]";
// The report is white paper in both themes (like Trade Lab's draft), so its chart uses the light category
// colours, in an order the dataviz validator passed on white (2026-10-19).
const SERIES = ["#008744", "#1C7ED6", "#D9480F", "#7048E8"];

const isX = (f?: Fact) => !!f && f.source_url.startsWith("https://x.com/");
const live = (s: Session) =>
  s.job?.state === "queued" || s.job?.state === "running" || s.proposals.some((p) => p.status === "running");

function stepOf(s: Session): number {
  if (s.status === "awaiting_answers") return 0;
  if (s.status === "complete") return 5;
  if (s.status === "writing") return 4;
  if (!s.agents.length) return 1;
  return s.agents.filter((a) => a.round === 1).every((a) => a.findings.length || a.error) ? 3 : 2;
}

function groupOf(r: Row): string {
  if (r.status === "awaiting_answers" || r.pending > 0 || r.job?.state === "failed" || r.job?.state === "interrupted")
    return "Needs you";
  if (r.job?.state === "queued" || r.job?.state === "running") return "Running";
  return "Reports";
}

function rowNote(r: Row): string {
  if (r.job?.state === "failed" || r.job?.state === "interrupted") return "Failed · retry";
  if (r.pending) return `${r.pending} proposal${r.pending > 1 ? "s" : ""} to review`;
  if (r.status === "awaiting_answers") return "Answer the clarifier";
  if (r.job?.state === "queued" || r.job?.state === "running") return r.status === "writing" ? "Writing…" : "Research…";
  return `${r.created_at.slice(0, 10)}${r.compacted ? " · summarized" : ""}`;
}

// word-level diff for the before → after card
function diffWords(a: string, b: string): [string, -1 | 0 | 1][] {
  const x = a.split(/(\s+)/);
  const y = b.split(/(\s+)/);
  const L = Array.from({ length: x.length + 1 }, () => new Array<number>(y.length + 1).fill(0));
  for (let i = x.length - 1; i >= 0; i--)
    for (let j = y.length - 1; j >= 0; j--) L[i][j] = x[i] === y[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  const out: [string, -1 | 0 | 1][] = [];
  let i = 0;
  let j = 0;
  while (i < x.length && j < y.length) {
    if (x[i] === y[j]) {
      out.push([x[i], 0]);
      i++;
      j++;
    } else if (L[i + 1][j] >= L[i][j + 1]) out.push([x[i++], -1]);
    else out.push([y[j++], 1]);
  }
  while (i < x.length) out.push([x[i++], -1]);
  while (j < y.length) out.push([y[j++], 1]);
  return out;
}

const Diff = ({ a, b }: { a: string; b: string }) => (
  <>
    {diffWords(a, b).map(([t, k], i) =>
      k === 0 ? (
        <span key={i}>{t}</span>
      ) : (
        <span key={i} className={k < 0 ? "rounded-sm bg-danger-soft text-danger line-through decoration-danger/60" : "rounded-sm bg-success-soft text-success"}>
          {t}
        </span>
      ),
    )}
  </>
);

function Chip({ id, facts }: { id: string; facts: Record<string, Fact> }) {
  const [open, setOpen] = useState(false);
  const f = facts[id];
  return (
    <span className="relative font-sans">
      <button onClick={(e) => { e.stopPropagation(); setOpen((o) => !o); }}
        className={cn("rounded px-1 font-mono text-[10px] font-bold", isX(f) ? XTONE : "bg-accent-soft-2 text-accent")}>{id}</button>
      {open && f && (
        <span className="absolute left-0 top-5 z-20 block w-72 rounded-xl border border-border-strong bg-surface-3 p-3 text-xs text-text shadow-lg">
          <span className="block">{f.text}</span>
          <span className="mt-1 block text-muted">{f.source_title}</span>
          {f.source_url && <a href={f.source_url} target="_blank" rel="noreferrer" className="mt-1 block font-semibold text-accent">Open the source ↗</a>}
        </span>
      )}
    </span>
  );
}

const Chips = ({ ids, facts }: { ids: string[]; facts: Record<string, Fact> }) => (
  <>{ids.map((i) => <span key={i}> <Chip id={i} facts={facts} /></span>)}</>
);

const Owner = ({ a, letter }: { a?: AgentRun; letter: string }) => (
  <span className="inline-flex items-center gap-1 rounded-full bg-surface-3 px-2 py-0.5 text-[11px] font-semibold text-text-2">
    <b className="grid h-4 w-4 place-items-center rounded-full bg-text text-[10px] text-surface">{letter}</b>{a?.brief.name ?? "agent"}
  </span>
);

// One y-axis: two or more series (a comparison) are indexed to 100 at their first point.
function MiniChart({ c }: { c: Chart }) {
  const indexed = c.series.length > 1;
  const rows = useMemo(() => {
    const by: Record<string, Record<string, number | string>> = {};
    c.series.forEach((s) => {
      const base = s.points[0]?.y || 1;
      s.points.forEach((p) => { (by[p.x] ??= { x: p.x })[s.name] = indexed ? Math.round((p.y / base) * 1000) / 10 : p.y; });
    });
    return Object.values(by).sort((a, b) => String(a.x).localeCompare(String(b.x)));
  }, [c, indexed]);
  const label = indexed ? "Index, first day = 100" : c.y_label;
  const last = rows.length - 1;
  return (
    <figure className="my-3 rounded-lg border border-black/10 p-3">
      <figcaption className="text-[13px] font-semibold">{c.title}</figcaption>
      {c.rationale && <p className="text-[12px] text-black/55">{c.rationale}</p>}
      <div className="mt-2 h-44">
        <ResponsiveContainer>
          <LineChart data={rows} margin={{ top: 8, right: 56, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="rgb(0 0 0 / 0.07)" vertical={false} />
            <XAxis dataKey="x" tick={{ fontSize: 10, fill: "rgb(0 0 0 / 0.5)" }} tickLine={false} axisLine={{ stroke: "rgb(0 0 0 / 0.12)" }} minTickGap={48} />
            <YAxis tick={{ fontSize: 10, fill: "rgb(0 0 0 / 0.5)" }} tickLine={false} axisLine={false} width={48} domain={["auto", "auto"]} />
            <Tooltip contentStyle={{ background: "#fff", border: "1px solid rgb(0 0 0 / 0.15)", borderRadius: 8, fontSize: 12, color: "rgb(0 0 0 / 0.85)" }} />
            {c.series.map((s, k) => (
              <Line key={s.name} dataKey={s.name} stroke={SERIES[k % SERIES.length]} strokeWidth={2} dot={false} isAnimationActive={false}>
                {/* direct label at the line's end: identity never rests on colour alone */}
                <LabelList dataKey={s.name} content={(p: { index?: number; x?: number | string; y?: number | string }) =>
                  p.index === last ? <text x={Number(p.x) + 6} y={Number(p.y) + 4} fontSize={10.5} fill="rgb(0 0 0 / 0.65)">{s.name}</text> : null} />
              </Line>
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-3 text-[11px] text-black/55">
        {c.series.length > 1 && c.series.map((s, k) => (
          <span key={s.name} className="inline-flex items-center gap-1"><i className="h-2 w-2 rounded-full" style={{ background: SERIES[k % SERIES.length] }} />{s.name}</span>
        ))}
        <span>{[label, c.source].filter(Boolean).join(" · ")}</span>
      </div>
      <details className="mt-1 text-[11px] text-black/55">
        <summary className="cursor-pointer">Data</summary>
        <div className="mt-1 max-h-40 overflow-auto">
          <table className="w-full"><thead><tr><th className="text-left font-semibold">Date</th>{c.series.map((s) => <th key={s.name} className="text-right font-semibold">{s.name}</th>)}</tr></thead>
            <tbody>{rows.map((r) => <tr key={String(r.x)}><td>{String(r.x)}</td>{c.series.map((s) => <td key={s.name} className="num text-right">{r[s.name] ?? ""}</td>)}</tr>)}</tbody></table>
        </div>
      </details>
    </figure>
  );
}

function Header({ s }: { s: Session }) {
  const at = stepOf(s);
  return (
    <div className="rounded-2xl border border-border bg-surface px-5 py-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="eyebrow">Deep research · started {s.created_at.slice(0, 16).replace("T", " ")}</div>
          <h2 className="mt-0.5 font-serif text-[24px] font-bold leading-tight">{s.topic}</h2>
          {s.question && <p className="text-[13px] text-muted">{s.question}</p>}
        </div>
        <div className="text-right text-[12px] text-muted"><b className="block font-serif text-[22px] text-text">${s.cost_usd.toFixed(2)}</b>of ${s.cost_cap_usd.toFixed(0)} spent</div>
      </div>
      <div className="mt-3 flex gap-1.5">
        {STEPS.map((x, i) => (
          <span key={x} className={cn("flex-1 rounded-full py-1 text-center text-[11.5px] font-semibold",
            i < at ? "bg-accent-soft text-accent" : i === at ? "bg-warning-soft text-warning ring-1 ring-warning/40" : "bg-surface-2 text-muted-2")}>
            {i < at ? "✓ " : ""}{x}
          </span>
        ))}
      </div>
      {s.fallbacks.length > 0 && <p className="mt-2 text-[11.5px] text-muted">Fallbacks: {s.fallbacks.slice(-3).join(" · ")}</p>}
    </div>
  );
}

function NewTopic({ onCreate }: { onCreate: (t: string) => Promise<void> }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const go = () => {
    const t = text.trim();
    if (t.length < 3 || busy) return;
    setBusy(true);
    onCreate(t).finally(() => setBusy(false));
  };
  return (
    <div className="rounded-2xl border border-border bg-surface p-6">
      <div className="eyebrow">New research</div>
      <h2 className="mt-1 font-serif text-2xl font-bold">What should we research?</h2>
      <p className="text-sm text-muted">A topic or a question. The clarifier asks up to 3 questions before anything is spent.</p>
      <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="AI adoption"
        className="mt-3 w-full rounded-xl border border-border-strong bg-surface-2 px-4 py-3 font-serif text-[17px] outline-none focus:border-accent" />
      <div className="mt-4 grid grid-cols-2 gap-2 text-xs text-muted md:grid-cols-6">
        {STEP_BOXES.map(([a, b, you]) => (
          <div key={a} className={cn("rounded-xl border bg-surface-2 p-2.5", you ? "border-warning/50" : "border-border")}>
            <b className={cn("block text-[13px]", you ? "text-warning" : "text-text")}>{a}</b>{b}
          </div>
        ))}
      </div>
      <div className="mt-4 flex items-center justify-between gap-3">
        <span className="text-xs text-muted">Research and writing take about 8 minutes. Up to $8 per report, edits included.</span>
        <button onClick={go} disabled={busy} className="rounded-full bg-accent px-4 py-2 text-[13px] font-semibold text-on-accent disabled:opacity-50">
          {busy ? "Asking…" : "Ask the clarifier →"}
        </button>
      </div>
    </div>
  );
}

function Clarify({ s, onStart }: { s: Session; onStart: (a: Record<string, string>) => void }) {
  const [a, setA] = useState<Record<string, string>>({});
  const qs = s.clarifying_questions;
  return (
    <div className="rounded-2xl border border-warning/50 bg-surface p-5">
      <div className="eyebrow text-warning">
        {qs.length ? `Before we spend anything · ${qs.length} question${qs.length > 1 ? "s" : ""}` : "The clarifier has no questions"}
      </div>
      <div className="mt-3 space-y-3">
        {qs.map((q) => (
          <div key={q.question} className="grid gap-4 rounded-xl border border-border bg-surface-2 p-3 md:grid-cols-[1fr_1.1fr]">
            <div><b className="text-[14px]">{q.question}</b><p className="text-[12px] text-muted">{q.why}</p></div>
            <input value={a[q.question] ?? ""} onChange={(e) => setA({ ...a, [q.question]: e.target.value })}
              placeholder="Leave blank: the Lead picks a sensible assumption"
              className="rounded-lg border border-border-strong bg-surface px-3 py-2 text-[13.5px] outline-none focus:border-accent" />
          </div>
        ))}
      </div>
      <div className="mt-4 flex items-center justify-between">
        <span className="text-xs text-muted">Next: the Lead plans up to 8 agents · about 8 minutes · about $2</span>
        <button onClick={() => onStart(a)} className="rounded-full bg-accent px-4 py-2 text-[13px] font-semibold text-on-accent">Start research →</button>
      </div>
    </div>
  );
}

// ponytail: agent cards fill in when each agent finishes (that's when the runner saves it), not per tool call
function Agents({ s, facts }: { s: Session; facts: Record<string, Fact> }) {
  const running = live(s);
  return (
    <>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {s.agents.map((a) => {
          const state = a.error ? "failed" : a.findings.length ? "done" : running ? "running" : "waiting";
          const settled = state === "done" || state === "failed";
          const own = a.facts.filter((f) => f.id.startsWith(a.letter)).length;
          const stats: [number, string][] = [[a.tool_calls, "tool calls"], [own, "facts"], [a.x_posts, "X posts"]];
          return (
            <div key={a.letter} className="rounded-2xl border border-border bg-surface p-4">
              <div className="flex items-center gap-2">
                <span className="grid h-6 w-6 place-items-center rounded-lg bg-text text-xs font-bold text-surface">{a.letter}</span>
                <b className="text-sm">{a.brief.name}</b>
                <span className={cn("ml-auto text-[11px] font-semibold", state === "done" ? "text-accent" : state === "failed" ? "text-danger" : "text-warning")}>
                  {state}{a.round === 2 ? " · gap round" : ""}
                </span>
              </div>
              <p className="my-2 text-[12.5px] text-muted">{a.brief.angle}</p>
              <div className="grid grid-cols-3 gap-1.5 text-center">
                {stats.map(([v, l]) => (
                  <div key={l} className="rounded-lg bg-surface-2 py-1.5">
                    <b className="block font-serif text-lg">{settled ? v : "…"}</b>
                    <span className="text-[10px] uppercase tracking-wide text-muted">{l}</span>
                  </div>
                ))}
              </div>
              {a.error && <p className="mt-2 text-xs text-danger">{a.error}</p>}
            </div>
          );
        })}
      </div>
      {s.board.length > 0 && (
        <div className="rounded-2xl border border-border bg-surface p-4">
          <div className="eyebrow">Shared board · {s.board.length} posts</div>
          <div className="mt-2 space-y-1.5 text-[13px] text-text-2">
            {s.board.slice(-4).map((p, i) => <div key={i}><b>{p.agent}:</b> {p.note}<Chips ids={p.fact_ids} facts={facts} /></div>)}
          </div>
        </div>
      )}
    </>
  );
}

function ReportView({ s, facts, selected, onSelect }: {
  s: Session; facts: Record<string, Fact>; selected: string | null; onSelect: (id: string) => void;
}) {
  const r = s.report!;
  const agentOf = (l: string) => s.agents.find((a) => a.letter === l);
  const openFor = (pid: string) => s.proposals.some((p) => p.point_id === pid && (p.status === "pending" || p.status === "running"));
  const cited = [...new Set(r.points.flatMap((p) => p.fact_ids))].map((i) => facts[i]).filter(Boolean);
  const sources = [...new Map(cited.map((f) => [f.source_url || f.source_title, f])).values()];
  const calls = s.agents.reduce((n, a) => n + a.tool_calls, 0);
  return (
    <div className="overflow-hidden rounded-2xl bg-white text-black/90">
      <div className="flex justify-between border-b border-black/10 px-4 py-2.5 text-xs text-black/50">
        <span>Deep research · for you only · {s.agents.length} agents, {calls} tool calls, {sources.length} sources</span>
        <a href="#research-sources" className="font-semibold text-accent">Sources ({sources.length}) ↓</a>
      </div>
      <div className="px-6 py-5">
        <div className="text-[11px] font-bold uppercase tracking-wider text-accent">ARC Deep Research</div>
        <h3 className="mt-1 font-serif text-[26px] font-bold leading-tight">{r.title}</h3>
        <p className="mb-3 text-[13.5px] text-black/55">{r.subtitle}</p>
        <div className="text-[11px] font-bold uppercase tracking-wider text-black/50">Key findings</div>
        <ol className="mt-1 list-decimal pl-5 text-sm">
          {r.points.map((p) => (
            <li key={p.id} className={cn("my-1", p.id === selected && "font-semibold")}>{p.headline} <span className="text-[11px] text-black/40">{p.agent}</span></li>
          ))}
        </ol>
        {r.charts.map((c) => <MiniChart key={c.title} c={c} />)}
        {r.points.map((p, i) => (
          <section key={p.id} onClick={() => onSelect(p.id)}
            className={cn("mt-4 cursor-pointer rounded-xl", p.id === selected && "-mx-3 bg-accent-soft/60 px-3 py-2 ring-2 ring-accent/40")}>
            <div className="flex items-center justify-between gap-2 border-t border-black/10 pt-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[11px] font-bold text-black/40">POINT {i + 1}</span>
                <Owner a={agentOf(p.agent)} letter={p.agent} />
                {p.version > 1 && <span className="rounded-full bg-accent-soft px-2 py-0.5 text-[11px] font-semibold text-accent">v{p.version} · edited</span>}
                {openFor(p.id) && <span className="rounded-full bg-warning-soft px-2 py-0.5 text-[11px] font-semibold text-warning">open question</span>}
              </div>
              <span className={cn("rounded-full border px-2.5 py-0.5 text-[11.5px] font-semibold",
                p.id === selected ? "border-accent bg-accent text-on-accent" : "border-black/15 text-black/55")}>Ask or edit</span>
            </div>
            <h4 className="mt-2 font-serif text-[18px] font-bold leading-snug">{p.headline}</h4>
            <p className="my-1.5 font-serif text-base leading-relaxed">{p.body}<Chips ids={p.fact_ids} facts={facts} /></p>
          </section>
        ))}
        {r.caveats.length > 0 && (
          <div className="mt-5 rounded-lg bg-black/5 p-3 text-xs"><b>Caveats</b><ul className="list-disc pl-4">{r.caveats.map((c, i) => <li key={i}>{c}</li>)}</ul></div>
        )}
        {r.gaps_remaining.length > 0 && (
          <div className="mt-2 rounded-lg bg-black/5 p-3 text-xs"><b>Still open</b><ul className="list-disc pl-4">{r.gaps_remaining.map((c, i) => <li key={i}>{c}</li>)}</ul></div>
        )}
        <details id="research-sources" className="mt-5 text-xs">
          <summary className="cursor-pointer font-semibold">Sources ({sources.length})</summary>
          <ul className="mt-2 space-y-1">
            {sources.map((f) => (
              <li key={f.id}>{f.source_url ? <a href={f.source_url} target="_blank" rel="noreferrer" className="text-accent">{f.source_title}</a> : f.source_title}</li>
            ))}
          </ul>
        </details>
      </div>
    </div>
  );
}

function ProposalCard({ x, facts, n, onDecide }: {
  x: Proposal; facts: Record<string, Fact>; n: number; onDecide: (ok: boolean) => void;
}) {
  const a = x.before!;
  const b = x.after!;
  return (
    <div className="rounded-xl border border-warning/50 bg-surface p-3.5">
      <div className="flex items-center justify-between">
        <div className="eyebrow text-warning">Proposal · Point {n} · before → after</div>
        <span className="text-[11px] text-muted">v{a.version} → v{b.version}</span>
      </div>
      <p className="mt-2 font-serif text-[15px] font-bold leading-relaxed text-text"><Diff a={a.headline} b={b.headline} /></p>
      <p className="mt-1 font-serif text-[15px] leading-relaxed text-text-2"><Diff a={a.body} b={b.body} /><Chips ids={b.fact_ids} facts={facts} /></p>
      {x.new_facts.length > 0 && (
        <div className="mt-2 rounded-lg bg-surface-2 px-3 py-2 text-[12px] text-muted">
          New: {x.new_facts.map((f) => <span key={f.id} className="mr-2"><b className="text-text-2">{f.source_title}</b> <Chip id={f.id} facts={facts} /></span>)}
        </div>
      )}
      <div className="mt-3 flex items-center justify-between gap-2">
        <span className="text-[11.5px] text-muted">Approve changes Point {n} only. Nothing else in the report is rewritten.</span>
        <span className="flex gap-2">
          <button onClick={() => onDecide(false)} className="rounded-full border border-border-strong px-3.5 py-1.5 text-[12.5px] font-semibold text-text-2">Reject</button>
          <button onClick={() => onDecide(true)} className="rounded-full bg-accent px-3.5 py-1.5 text-[12.5px] font-semibold text-on-accent">Approve</button>
        </span>
      </div>
    </div>
  );
}

function Exchange({ x, s, facts, n, onSession, onError }: {
  x: Proposal; s: Session; facts: Record<string, Fact>; n: number; onSession: (s: Session) => void; onError: (e: string) => void;
}) {
  const a = s.agents.find((g) => g.letter === x.agent);
  const decide = (ok: boolean) =>
    (ok ? research.approve(s.id, x.n) : research.reject(s.id, x.n)).then(onSession).catch((e) => onError(String(e.message ?? e)));
  return (
    <>
      <div className="max-w-[94%] self-end rounded-xl rounded-br-sm bg-surface-3 px-3 py-2 text-[13px] leading-relaxed text-text-2">{x.text}</div>
      {x.status === "running" ? (
        <div className="self-start rounded-xl border border-dashed border-warning/60 bg-warning-soft/50 px-3 py-2 text-[12.5px] font-semibold text-warning">
          <span className="mr-1.5 inline-block h-2.5 w-2.5 animate-spin rounded-full border-2 border-warning border-r-transparent align-[-1px]" />
          {x.agent} · {a?.brief.name} is rechecking…
        </div>
      ) : x.answer && (
        <div className="max-w-[96%] self-start rounded-xl rounded-bl-sm border border-border bg-surface-2 px-3 py-2 text-[13px] leading-relaxed text-text-2">
          <div className="mb-0.5 text-[11px] font-bold text-muted">{x.agent} · {a?.brief.name}</div>
          {x.answer}
          {x.trail.length > 0 && <div className="mt-1.5 flex flex-col gap-0.5 text-[11.5px] text-muted">{x.trail.map((t, i) => <div key={i}>{t}</div>)}</div>}
        </div>
      )}
      {x.status === "pending" && <ProposalCard x={x} facts={facts} n={n} onDecide={decide} />}
      {x.status === "answered" && <span className="w-fit rounded-full bg-surface-3 px-2 py-0.5 text-[11px] font-semibold text-muted">No change proposed</span>}
      {x.status === "approved" && <span className="w-fit rounded-full bg-accent-soft px-2 py-0.5 text-[11px] font-semibold text-accent">Approved · v{x.after?.version}</span>}
      {x.status === "rejected" && <span className="w-fit rounded-full bg-surface-3 px-2 py-0.5 text-[11px] font-semibold text-muted">Rejected · point kept</span>}
      {x.status === "failed" && (
        <div className="rounded-xl border border-danger bg-danger-soft px-3 py-2 text-[13px] text-danger"><b>Point {n} · not changed.</b> {x.error} Your report is untouched.</div>
      )}
    </>
  );
}

function Desk({ s, facts, pid, onSession }: { s: Session; facts: Record<string, Fact>; pid: string; onSession: (s: Session) => void }) {
  const [text, setText] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const points = s.report!.points;
  const n = points.findIndex((p) => p.id === pid) + 1;
  const p = points[n - 1];
  if (!p) return null;
  const mine = s.proposals.filter((x) => x.point_id === pid);
  const open = mine.some((x) => x.status === "running" || x.status === "pending");
  const send = () => {
    const t = text.trim();
    if (!t || open) return;
    setErr(null);
    research.ask(s.id, pid, t).then((x) => { setText(""); onSession(x); }).catch((e) => setErr(String(e.message ?? e)));
  };
  return (
    <div className="rounded-2xl border border-warning/50 bg-surface">
      <div className="flex flex-col gap-2.5 p-4">
        <div className="eyebrow text-warning">Editor desk · Point {n}</div>
        <div className="-mt-1 flex items-center gap-2 text-[11.5px] text-muted">
          <Owner a={s.agents.find((a) => a.letter === p.agent)} letter={p.agent} /> answers questions about this point
        </div>
        {mine.map((x) => <Exchange key={x.n} x={x} s={s} facts={facts} n={n} onSession={onSession} onError={setErr} />)}
        <textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} disabled={open}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
          placeholder={open ? "Answer the open proposal first…" : `Ask about Point ${n}, or tell it what to change…`}
          className="w-full rounded-xl border border-border-strong bg-surface-2 px-3 py-2 text-sm outline-none focus:border-accent disabled:opacity-60" />
        {err && <div className="text-xs text-danger">{err}</div>}
        <div className="flex justify-between text-[11.5px] text-muted">
          <span>One question per point at a time · click any point to switch</span>
          <span>${s.cost_usd.toFixed(2)} of ${s.cost_cap_usd.toFixed(0)} spent</span>
        </div>
      </div>
    </div>
  );
}

const PILL: Record<Proposal["status"], string> = {
  running: "bg-warning-soft text-warning",
  pending: "bg-warning-soft text-warning",
  answered: "bg-surface-3 text-muted",
  approved: "bg-accent-soft text-accent",
  rejected: "bg-surface-3 text-muted",
  failed: "bg-danger-soft text-danger",
};
const PILL_LABEL: Record<Proposal["status"], string> = {
  running: "rechecking", pending: "pending", answered: "answered, no change", approved: "approved", rejected: "rejected", failed: "failed",
};

function EditLog({ s, onPick }: { s: Session; onPick: (pid: string) => void }) {
  if (!s.proposals.length) return null;
  const idx = (pid: string) => s.report!.points.findIndex((p) => p.id === pid) + 1;
  return (
    <div className="rounded-2xl border border-border bg-surface p-4">
      <div className="eyebrow">Edit log</div>
      <div className="mt-2 space-y-1.5 text-[12.5px]">
        {[...s.proposals].reverse().map((x) => (
          <button key={x.n} onClick={() => onPick(x.point_id)} className="flex w-full justify-between gap-2 text-left hover:text-accent">
            <span className="truncate">Point {idx(x.point_id)} · "{x.text}"</span>
            <span className={cn("whitespace-nowrap rounded-full px-2 text-[11px] font-semibold", PILL[x.status])}>
              {PILL_LABEL[x.status]}{x.status === "approved" ? ` · v${x.after?.version}` : ""}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

const DOT: Record<string, string> = { "Needs you": "bg-warning", Running: "bg-info animate-pulse", Reports: "bg-accent" };

export default function Research() {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [s, setS] = useState<Session | null>(null);
  const [point, setPoint] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fail = (e: unknown) => setError(String((e as Error).message ?? e));

  const refreshList = useCallback(() => { research.list().then((r) => setRows(r.sessions)).catch(fail); }, []);
  useEffect(() => { refreshList(); }, [refreshList]);
  useEffect(() => {
    if (sel && s?.id !== sel) {
      setS(null);
      setPoint(null);
      research.get(sel).then(setS).catch(fail);
    }
  }, [sel]); // eslint-disable-line react-hooks/exhaustive-deps

  const polling = !!s && live(s);
  useEffect(() => {
    if (!polling || !sel) return;
    const t = setInterval(() => { research.get(sel).then(setS).catch(fail); refreshList(); }, 3000);
    return () => clearInterval(t);
  }, [polling, sel, refreshList]);

  const onSession = (x: Session) => { setError(null); setS(x); setSel(x.id); refreshList(); };
  const act = (p: Promise<Session>) => { setError(null); p.then(onSession).catch(fail); };
  const facts = useMemo(() => {
    const out: Record<string, Fact> = { ...(s?.board_facts ?? {}) };
    s?.agents.forEach((a) => a.facts.forEach((f) => { out[f.id] = f; }));
    s?.proposals.forEach((p) => p.new_facts.forEach((f) => { out[f.id] = f; }));
    return out;
  }, [s]);

  const groups = ["Needs you", "Running", "Reports"].map((g) => [g, (rows ?? []).filter((r) => groupOf(r) === g)] as const);
  const job = s?.job;
  const done = s ? s.agents.filter((a) => a.findings.length || a.error).length : 0;

  return (
    <div className="grid items-start gap-4 px-4 pb-8 md:grid-cols-[250px_1fr] md:px-8">
      <aside className="rounded-2xl border border-border bg-surface p-2.5">
        <button onClick={() => { setSel(null); setS(null); }} className="mb-2 w-full rounded-full bg-accent py-2 text-[13px] font-semibold text-on-accent">+ New research</button>
        {rows === null && <p className="p-2 text-xs text-muted">Loading…</p>}
        {rows?.length === 0 && <p className="p-2 text-xs text-muted">No research yet.</p>}
        {groups.map(([g, list]) => list.length > 0 && (
          <div key={g}>
            <div className="px-2 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wider text-muted-2">{g}</div>
            {list.map((r) => (
              <button key={r.id} onClick={() => setSel(r.id)}
                className={cn("grid w-full grid-cols-[10px_1fr] gap-2.5 rounded-xl px-2 py-2 text-left hover:bg-surface-3", sel === r.id && "bg-accent-soft ring-1 ring-accent/30")}>
                <span className={cn("mt-1.5 h-2 w-2 rounded-full", DOT[g])} />
                <span><b className="block text-[13px] font-semibold leading-tight">{r.topic}</b><span className="text-[11.5px] text-muted">{rowNote(r)}</span></span>
              </button>
            ))}
          </div>
        ))}
      </aside>

      <main className="min-w-0 space-y-3.5">
        {error && <div className="rounded-xl border border-danger bg-danger-soft px-4 py-2.5 text-sm text-danger">{error}</div>}
        {!sel && <NewTopic onCreate={(t) => research.create(t).then(onSession).catch(fail)} />}
        {sel && !s && <p className="text-sm text-muted">Loading the research…</p>}
        {s && (
          <>
            <Header s={s} />
            {job && (job.state === "failed" || job.state === "interrupted") && (
              <div className="flex items-center justify-between gap-3 rounded-xl border border-danger bg-danger-soft px-4 py-2.5 text-sm text-danger">
                <span>{job.step} {job.state}: {job.message}</span>
                <button onClick={() => act(research.retry(s.id))} className="rounded-full border border-danger px-3 py-1 text-xs font-semibold">Retry</button>
              </div>
            )}
            {(job?.state === "queued" || job?.state === "running") && (
              <div className="rounded-xl bg-warning-soft px-4 py-2.5 text-sm text-warning">
                {s.status === "writing" ? "Writing…" : job.step === "compact" ? "Summarizing…" : `Research… ${done} of ${s.agents.length || "?"} agents done`}
                {" "}(started {job.at.slice(11, 16)}). This page updates by itself.
              </div>
            )}
            {s.status === "awaiting_answers" && <Clarify s={s} onStart={(a) => act(research.answers(s.id, a))} />}
            {(s.status === "researching" || s.status === "writing") && s.agents.length > 0 && <Agents s={s} facts={facts} />}
            {s.status === "complete" && s.report && (
              <div className="grid items-start gap-3.5 lg:grid-cols-[1.45fr_1fr]">
                <ReportView s={s} facts={facts} selected={point} onSelect={setPoint} />
                <div className="space-y-3.5 lg:sticky lg:top-4">
                  {point ? <Desk key={point} s={s} facts={facts} pid={point} onSession={onSession} />
                    : <div className="rounded-2xl border border-dashed border-border-strong bg-surface p-5 text-sm text-muted">Click any point to question it or tell its agent what to change.</div>}
                  <EditLog s={s} onPick={setPoint} />
                </div>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
