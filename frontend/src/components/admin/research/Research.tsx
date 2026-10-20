import { useCallback, useEffect, useMemo, useState } from "react";
import { cn } from "@/lib/cn";
import {
  research, type AgentRun, type ChartValue, type Fact, type PointChart as PointChartT, type Proposal, type Row,
  type Session,
} from "./api";

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
  if (r.job?.state === "queued" || r.job?.state === "running")
    return r.status === "writing" ? "Writing…" : r.job.step === "add" ? "Adding angles…" : "Research…";
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

// A point's chart, drawn from the figures it cites (charts.py). The report is white paper in both themes,
// so it uses the light accent; one series per chart, so no legend. Every value is labelled, hover or focus
// shows its source fact, and "Data" opens the table.
const INK = "#008744";

function fmt(v: number, unit: PointChartT["unit"], decimals: number): string {
  const n = v.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  return unit === "%" ? `${n}%` : unit === "$" ? `$${n}` : unit === "bp" || unit === "pp" ? `${n} ${unit}` : n;
}

function PointChart({ c, facts }: { c: PointChartT; facts: Record<string, Fact> }) {
  const [hover, setHover] = useState<ChartValue | null>(null);
  // as many decimals as the most precise value, so 20.0 / 20.2 / 19.8 line up and 69 stays 69
  const decimals = Math.max(0, ...c.values.map((v) => (String(v.value).split(".")[1] ?? "").length));
  const f = (v: number) => fmt(v, c.unit, decimals);
  const max = Math.max(...c.values.map((v) => v.value), 0) || 1;
  const aria = `${c.title}: ${c.values.map((v) => `${v.label} ${f(v.value)}`).join(", ")}`;
  const on = (v: ChartValue) => ({
    onMouseEnter: () => setHover(v), onMouseLeave: () => setHover(null), onFocus: () => setHover(v), onBlur: () => setHover(null),
    tabIndex: 0,
  });
  let body: JSX.Element;
  if (c.form === "stat") {
    const v = c.values[0];
    body = (
      <div className="mt-1 flex items-baseline gap-3" role="img" aria-label={aria}>
        <b className="font-serif text-[40px] leading-none" style={{ color: INK }}>{f(v.value)}</b>
        <span className="text-[12.5px] text-black/60">{v.label}</span>
      </div>
    );
  } else if (c.form === "bars") {
    body = (
      <div className="mt-2 space-y-1.5" role="img" aria-label={aria}>
        {c.values.map((v) => (
          <div key={`${v.fact_id}-${v.label}`} className="grid grid-cols-[minmax(90px,170px)_1fr_auto] items-center gap-2 text-[12px]">
            <span className="truncate text-right text-black/65" title={v.label}>{v.label}</span>
            <span className="relative h-4 outline-none" {...on(v)}>
              <span className="absolute inset-y-0 left-0 rounded-r-[4px]" style={{ width: `${(Math.max(v.value, 0) / max) * 100}%`, background: INK }} />
            </span>
            <span className="num font-semibold text-black/80">{f(v.value)}</span>
          </div>
        ))}
      </div>
    );
  } else {
    const W = 560, H = c.form === "line" ? 130 : 66, pad = 34, top = max * 1.15;
    const xs = (i: number) => pad + (i * (W - 2 * pad)) / Math.max(1, c.values.length - 1);
    const xv = (v: number) => pad + (v / top) * (W - 2 * pad);
    const y = (v: number) => H - 22 - (v / top) * (H - 42);
    body = c.form === "line" ? (
      <svg viewBox={`0 0 ${W} ${H}`} className="mt-1 w-full max-w-[600px]" role="img" aria-label={aria}>
        <line x1={pad} x2={W - pad} y1={H - 22} y2={H - 22} stroke="rgb(0 0 0 / .12)" />
        <polyline fill="none" stroke={INK} strokeWidth={2} points={c.values.map((v, i) => `${xs(i)},${y(v.value)}`).join(" ")} />
        {c.values.map((v, i) => (
          <g key={`${v.fact_id}-${v.label}`}>
            <circle cx={xs(i)} cy={y(v.value)} r={5} fill={INK} stroke="#fff" strokeWidth={2} className="outline-none" {...on(v)} />
            <text x={xs(i)} y={y(v.value) - 10} textAnchor="middle" fontSize={11} fontWeight={600} fill="rgb(0 0 0 / .75)">{f(v.value)}</text>
            <text x={xs(i)} y={H - 6} textAnchor="middle" fontSize={10.5} fill="rgb(0 0 0 / .5)">{v.label}</text>
          </g>
        ))}
      </svg>
    ) : (
      <svg viewBox={`0 0 ${W} ${H}`} className="mt-1 w-full max-w-[600px]" role="img" aria-label={aria}>
        <line x1={xv(c.values[0].value)} x2={xv(c.values[1].value)} y1={28} y2={28} stroke="rgb(0 0 0 / .2)" strokeWidth={3} />
        {c.values.map((v, i) => (
          <g key={`${v.fact_id}-${v.label}`}>
            <circle cx={xv(v.value)} cy={28} r={7} fill={i ? INK : "#fff"} stroke={i ? "#fff" : INK} strokeWidth={i ? 2 : 2.5} className="outline-none" {...on(v)} />
            <text x={xv(v.value)} y={56} textAnchor="middle" fontSize={11} fill="rgb(0 0 0 / .65)">{v.label} · <tspan fontWeight={700}>{f(v.value)}</tspan></text>
          </g>
        ))}
      </svg>
    );
  }
  const ids = [...new Set(c.values.map((v) => v.fact_id))];
  return (
    <figure className="mt-2 rounded-lg border border-black/10 bg-white p-3 font-sans">
      <figcaption className="text-[12.5px] font-semibold text-black/80">{c.title}</figcaption>
      {body}
      <div className="mt-1.5 flex flex-wrap items-center gap-1 text-[11px] text-black/45">
        {hover ? <span className="text-black/70">{hover.label}: <b>{f(hover.value)}</b> · {facts[hover.fact_id]?.source_title ?? hover.fact_id}</span>
          : <>From the point's cited facts<Chips ids={ids} facts={facts} />{c.fallback && " · big-number tile (the chart agent's chart failed the check)"}</>}
      </div>
      <details className="mt-1 text-[11px] text-black/55">
        <summary className="cursor-pointer font-semibold text-accent">Data</summary>
        <table className="mt-1 w-full">
          <thead><tr><th className="text-left font-semibold">Label</th><th className="text-right font-semibold">Value</th><th className="text-right font-semibold">Fact</th></tr></thead>
          <tbody>{c.values.map((v) => (
            <tr key={`${v.fact_id}-${v.label}`}><td>{v.label}</td><td className="num text-right">{f(v.value)}</td><td className="text-right font-mono">{v.fact_id}</td></tr>
          ))}</tbody>
        </table>
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
        {r.points.map((p, i) => (
          <section key={p.id} onClick={() => onSelect(p.id)}
            className={cn("mt-4 cursor-pointer rounded-xl", p.id === selected && "-mx-3 bg-accent-soft/60 px-3 py-2 ring-2 ring-accent/40")}>
            <div className="flex items-center justify-between gap-2 border-t border-black/10 pt-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[11px] font-bold text-black/40">POINT {i + 1}</span>
                <Owner a={agentOf(p.agent)} letter={p.agent} />
                {p.added && <span title={s.additions.find((a) => a.n === p.added)?.text} className="rounded-full bg-info-soft px-2 py-0.5 text-[11px] font-semibold text-info">added</span>}
                {p.older && <span title="No figure from this year was found; the point says its data is the latest available" className="rounded-full bg-warning-soft px-2 py-0.5 text-[11px] font-semibold text-warning">older data · {p.older}</span>}
                {p.version > 1 && <span className="rounded-full bg-accent-soft px-2 py-0.5 text-[11px] font-semibold text-accent">v{p.version} · edited</span>}
                {openFor(p.id) && <span className="rounded-full bg-warning-soft px-2 py-0.5 text-[11px] font-semibold text-warning">open question</span>}
              </div>
              <span className={cn("rounded-full border px-2.5 py-0.5 text-[11.5px] font-semibold",
                p.id === selected ? "border-accent bg-accent text-on-accent" : "border-black/15 text-black/55")}>Ask or edit</span>
            </div>
            <h4 className="mt-2 font-serif text-[18px] font-bold leading-snug">{p.headline}</h4>
            <p className="my-1.5 font-serif text-base leading-relaxed">{p.body}<Chips ids={p.fact_ids} facts={facts} /></p>
            {p.chart && <PointChart c={p.chart} facts={facts} />}
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
      {b.chart && <div className="mt-2 text-[11px] font-semibold text-muted">The chart after the edit</div>}
      {b.chart && <PointChart c={b.chart} facts={facts} />}
      {x.new_facts.length > 0 && (
        <div className="mt-2 rounded-lg bg-surface-2 px-3 py-2 text-[12px] text-muted">
          New: {x.new_facts.map((f) => <span key={f.id} className="mr-2"><b className="text-text-2">{f.source_title}</b> <Chip id={f.id} facts={facts} /></span>)}
        </div>
      )}
      <div className="mt-3 flex items-center justify-between gap-2">
        <span className="text-[11.5px] text-muted">Approve swaps Point {n}'s text and chart. Nothing else in the report changes.</span>
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

// The report's Substack draft in the Artificial Intelligence section (publish.py): made when the report
// finishes, updated after added angles and approved edits, never over your own edits on Substack.
function DraftBar({ s, onSession }: { s: Session; onSession: (s: Session) => void }) {
  const [busy, setBusy] = useState(false);
  const d = s.substack;
  const push = () => {
    setBusy(true);
    research.draft(s.id)
      .then(() => setTimeout(() => research.get(s.id).then(onSession).finally(() => setBusy(false)), 12000))
      .catch(() => setBusy(false));
  };
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-border bg-surface px-4 py-3 text-[12.5px]">
      <span className="text-muted">
        <b className="text-text">Substack draft</b> · Artificial Intelligence
        {d?.at ? ` · ${d.note ? "tried" : "updated"} ${d.at.slice(11, 16)}` : ""}
      </span>
      <span className="flex items-center gap-3">
        {d?.url && (
          <a href={d.url} target="_blank" rel="noreferrer" className="font-semibold text-accent underline-offset-2 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent">
            Open draft ↗<span className="sr-only"> (opens Substack in a new tab)</span>
          </a>
        )}
        <button onClick={push} disabled={busy || live(s)}
          className="rounded-full border border-border-strong px-3 py-1 text-xs font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-50">
          {busy ? "Pushing…" : d?.url ? "Push again" : "Push to Substack"}
        </button>
      </span>
      {d?.note && <p role="status" className="w-full text-[11.5px] text-warning">{d.note}</p>}
    </div>
  );
}

// Angles you ask to add to a finished report: new agents research them, Claude writes new points only.
function AddAngles({ s, onSession }: { s: Session; onSession: (s: Session) => void }) {
  const [text, setText] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const running = s.job?.state === "queued" || s.job?.state === "running" || s.additions.some((a) => a.status === "running");
  const send = () => {
    const t = text.trim();
    if (t.length < 3 || running) return;
    setErr(null);
    research.addAngles(s.id, t).then((x) => { setText(""); onSession(x); }).catch((e) => setErr(String(e.message ?? e)));
  };
  return (
    <div className="flex flex-col gap-2.5 rounded-2xl border border-border bg-surface p-4">
      <label htmlFor="add-angles" className="eyebrow">Add angles to this report</label>
      <p className="-mt-1 text-[12.5px] text-muted">
        Up to 3 new agents research what you ask. Claude writes new points with charts; the points already in the report don't change.
      </p>
      <textarea id="add-angles" rows={3} value={text} onChange={(e) => setText(e.target.value)} disabled={running}
        placeholder={running ? "Wait for the current step to finish…" : "e.g. which AI models companies use, frontier vs open models, interest in sovereign AI"}
        className="w-full rounded-xl border border-border-strong bg-surface-2 px-3 py-2 text-sm outline-none focus:border-accent disabled:opacity-60" />
      {err && <div role="alert" className="text-xs text-danger">{err}</div>}
      <div className="flex items-center justify-between gap-2 text-[11.5px] text-muted">
        <span>About $0.50 to $1 · ${s.cost_usd.toFixed(2)} of ${s.cost_cap_usd.toFixed(0)} spent</span>
        <button onClick={send} disabled={running || text.trim().length < 3}
          className="rounded-full bg-accent px-3.5 py-1.5 text-xs font-semibold text-on-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-50">
          Add angles
        </button>
      </div>
      {s.additions.length > 0 && (
        <ul className="space-y-1.5 border-t border-border pt-2.5 text-[12.5px]">
          {[...s.additions].reverse().map((a) => {
            const made = s.report!.points.filter((p) => p.added === a.n).length;
            return (
              <li key={a.n}>
                <div className="flex justify-between gap-2">
                  <span className="truncate" title={a.text}>"{a.text}"</span>
                  <span className={cn("whitespace-nowrap rounded-full px-2 text-[11px] font-semibold",
                    a.status === "done" ? "bg-accent-soft text-accent" : a.status === "failed" ? "bg-danger-soft text-danger" : "bg-warning-soft text-warning")}>
                    {a.status === "done" ? `${made} new point${made === 1 ? "" : "s"}` : a.status === "failed" ? "failed" : "researching"}
                  </span>
                </div>
                {a.status === "failed" && a.error && <div className="text-[11.5px] text-danger">{a.error}</div>}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

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
  const lastAdd = s?.additions[s.additions.length - 1];
  const fresh = lastAdd ? s!.agents.filter((a) => a.round === lastAdd.round) : [];

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
                {s.status === "writing" ? "Writing…" : job.step === "compact" ? "Summarizing…"
                  : job.step === "add" ? `Adding angles… ${fresh.filter((a) => a.findings.length || a.error).length} of ${fresh.length || "?"} new agents done, then Claude writes the new points`
                  : `Research… ${done} of ${s.agents.length || "?"} agents done`}
                {" "}(started {job.at.slice(11, 16)}). This page updates by itself.
              </div>
            )}
            {s.status === "awaiting_answers" && <Clarify s={s} onStart={(a) => act(research.answers(s.id, a))} />}
            {(s.status === "researching" || s.status === "writing") && s.agents.length > 0 && <Agents s={s} facts={facts} />}
            {s.status === "complete" && s.report && (
              <div className="grid items-start gap-3.5 lg:grid-cols-[1.45fr_1fr]">
                <ReportView s={s} facts={facts} selected={point} onSelect={setPoint} />
                <div className="space-y-3.5 lg:sticky lg:top-4">
                  <DraftBar s={s} onSession={onSession} />
                  {point ? <Desk key={point} s={s} facts={facts} pid={point} onSession={onSession} /> : (
                    <>
                      <div className="rounded-2xl border border-dashed border-border-strong bg-surface p-5 text-sm text-muted">Click any point to question it or tell its agent what to change.</div>
                      <AddAngles s={s} onSession={onSession} />
                    </>
                  )}
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
