import { useEffect, useMemo, useRef, useState } from "react";
import { Card } from "@/components/ui/card";
import { PageIntro } from "@/components/layout/PageIntro";
import type { Pipeline, PipelineKind, PipelineLayer, PipelineNode } from "@/api/endpoints";
import { useAgentCatalog } from "@/hooks/useAgentCatalog";
import { cn } from "@/lib/cn";
import { C } from "@/lib/theme";

// The public /agents page: each pipeline in agents.yaml drawn as a layered graph (data sources → agents →
// guardrails → delivery) with a ▶ Play run walk-through. Node positions come from the YAML; edges are routed here.
const a = (name: string, alpha: number) => `rgb(var(--c-${name}) / ${alpha})`;
const H = 572, STEP_MS = 2800;
const STEP_BTN = "h-[34px] min-w-[34px] rounded-lg border border-border-strong text-[13px] text-text-2 hover:border-text-2 hover:text-text";
const LAYERS: { id: PipelineLayer; top: number; h: number; title: string; caption: string; c: string; v: string }[] = [
  { id: "sources", top: 0, h: 124, title: "DATA SOURCES", caption: "where the facts come from", c: C.ai, v: "cat-ai" },
  { id: "agents", top: 124, h: 232, title: "AGENTS", caption: "LLMs that read and write", c: C.accent, v: "accent" },
  { id: "guardrails", top: 356, h: 112, title: "GUARDRAILS", caption: "code that checks their work", c: C.warning, v: "warning" },
  { id: "delivery", top: 468, h: H - 468, title: "DELIVERY", caption: "where you read it", c: C.text2, v: "text" },
];
const LAYER = Object.fromEntries(LAYERS.map((l) => [l.id, l])) as Record<PipelineLayer, (typeof LAYERS)[number]>;

// label, text colour, border, fill, glow variable and dashed border per node kind
const KIND: Record<PipelineKind, { label: string; c: string; border: string; bg?: string; glow: string; dashed?: boolean }> = {
  source: { label: "◇ DATA SOURCE", c: C.ai, border: a("cat-ai", 0.55), bg: a("cat-ai", 0.1), glow: "cat-ai" },
  llm: { label: "◆ LLM AGENT", c: C.accent, border: a("accent", 0.55), bg: `linear-gradient(${a("accent-soft", 0.6)}, ${C.surface})`, glow: "accent" },
  code: { label: "⚙ CODE", c: C.muted, border: C.borderStrong, glow: "text", dashed: true },
  guard: { label: "⛨ GUARDRAIL", c: C.warning, border: a("warning", 0.6), bg: `linear-gradient(${a("warning-soft", 0.7)}, ${C.surface})`, glow: "warning" },
  trigger: { label: "⏱ TRIGGER", c: C.jobs, border: a("cat-jobs", 0.55), glow: "cat-jobs" },
  human: { label: "◎ HUMAN", c: C.inflation, border: a("cat-inflation", 0.55), glow: "cat-inflation" },
  out: { label: "↗ DELIVERY", c: C.text, border: C.text2, glow: "text" },
  stop: { label: "■ STOP", c: C.muted2, border: C.muted2, glow: "text", dashed: true },
};

type Pt = [number, number];
type Box = { x: number; y: number; w: number; h: number; layer: PipelineLayer };
const cx = (b: Box) => b.x + b.w / 2, cy = (b: Box) => b.y + b.h / 2;
const isChip = (n: PipelineNode) => n.kind === "source" && !n.sub;

function nodeBox(n: PipelineNode): Box {
  const L = LAYER[n.layer], w = n.w ?? (isChip(n) ? 100 : 150), h = n.h ?? (isChip(n) ? 28 : 58);
  return { x: n.x, y: L.top + (L.h - h) / 2 + (n.dy ?? 0), w, h, layer: n.layer };
}

/** Straight when the boxes face each other, else a Z: sideways via the gap's middle, or down/up turning near the target. */
function route(p: Box, q: Box): Pt[] {
  const ox = Math.min(p.x + p.w, q.x + q.w) - Math.max(p.x, q.x), oy = Math.min(p.y + p.h, q.y + q.h) - Math.max(p.y, q.y);
  if (q.x >= p.x + p.w || q.x + q.w <= p.x) {
    const right = q.x >= p.x + p.w, x1 = right ? p.x + p.w : p.x, x2 = right ? q.x : q.x + q.w;
    if (oy >= 24) { const y = Math.max(p.y, q.y) + oy / 2; return [[x1, y], [x2, y]]; }
    const m = (x1 + x2) / 2;
    return [[x1, cy(p)], [m, cy(p)], [m, cy(q)], [x2, cy(q)]];
  }
  const down = q.y >= p.y + p.h, y1 = down ? p.y + p.h : p.y, y2 = down ? q.y : q.y + q.h;
  if (ox >= 24) { const x = Math.max(p.x, q.x) + ox / 2; return [[x, y1], [x, y2]]; }
  const t = down ? q.y - 24 : q.y + q.h + 24;
  return [[cx(p), y1], [cx(p), t], [cx(q), t], [cx(q), y2]];
}

/** A loop drawn round one side; below/above clears every box of the same layer it passes over. */
function loop(p: Box, q: Box, side: string, all: Box[]): { pts: Pt[]; label: Pt; anchor: "start" | "middle" | "end" } {
  const lo = Math.min(cx(p), cx(q)), hi = Math.max(cx(p), cx(q));
  const near = all.filter((o) => o.layer === p.layer && o.x < hi && o.x + o.w > lo);
  if (side === "below" || side === "above") {
    const y = side === "below" ? Math.max(...near.map((o) => o.y + o.h), p.y + p.h, q.y + q.h) + 14 : Math.min(...near.map((o) => o.y), p.y, q.y) - 14;
    const e = (b: Box) => (side === "below" ? b.y + b.h : b.y);
    return { pts: [[cx(p), e(p)], [cx(p), y], [cx(q), y], [cx(q), e(q)]], label: [(lo + hi) / 2, side === "below" ? y + 13 : y - 6], anchor: "middle" };
  }
  // sideways loops leave and enter at the upper third, clear of the boxes' centre-line edges
  const ya = p.y + p.h * 0.3, yb = q.y + q.h * 0.3, right = side === "right";
  const x = right ? Math.max(p.x + p.w, q.x + q.w) + 32 : Math.min(p.x, q.x) - 32, ex = (b: Box) => (right ? b.x + b.w : b.x);
  return { pts: [[ex(p), ya], [x, ya], [x, yb], [ex(q), yb]], label: [x + (right ? 6 : -6), (ya + yb) / 2], anchor: right ? "start" : "end" };
}

/** The point halfway along a polyline: where a step's number sits. */
function midpoint(pts: Pt[]): Pt {
  const seg = pts.slice(1).map((p, i) => Math.hypot(p[0] - pts[i][0], p[1] - pts[i][1]));
  let half = seg.reduce((s, l) => s + l, 0) / 2;
  for (let i = 0; i < seg.length; i++) {
    if (half <= seg[i]) { const t = seg[i] ? half / seg[i] : 0; return [pts[i][0] + (pts[i + 1][0] - pts[i][0]) * t, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t]; }
    half -= seg[i];
  }
  return pts[pts.length - 1];
}

/** Slide a loop's label off a step number that sits on its line. */
function labelAt(l: { label: Pt; anchor: "start" | "middle" | "end" }, text: string, dots: Pt[]) {
  const w = text.length * 6.3, [x, y] = l.label;
  const left = l.anchor === "start" ? x : l.anchor === "end" ? x - w : x - w / 2;
  const hit = dots.find(([dx, dy]) => Math.abs(dy - (y - 4)) < 18 && dx > left - 14 && dx < left + w + 14);
  if (!hit) return { x, y, anchor: l.anchor };
  return hit[0] > left + w / 2 ? { x: hit[0] - 16, y, anchor: "end" as const } : { x: hit[0] + 16, y, anchor: "start" as const };
}

const key = (s: string) => s.split("|")[0].replace(/\s/g, ""); // "a > b | below | …" → "a>b"

function layout(p: Pipeline) {
  const boxes: Record<string, Box> = Object.fromEntries(p.nodes.map((n) => [n.id, nodeBox(n)]));
  const members: Record<string, string[]> = {};
  for (const g of p.groups ?? []) {
    const ms = g.nodes.map((id) => boxes[id]).filter(Boolean);
    const x = Math.min(...ms.map((b) => b.x)) - 12, y = Math.min(...ms.map((b) => b.y)) - 12;
    const w = Math.max(...ms.map((b) => b.x + b.w)) + 12 - x, h = Math.max(...ms.map((b) => b.y + b.h)) + (g.note ? 16 : 12) - y;
    boxes[g.id] = { x, y, w, h, layer: ms[0].layer };
    members[g.id] = g.nodes;
  }
  const all = Object.values(boxes);
  const edges = p.edges.map((s) => {
    const [ends, side, label] = s.split("|").map((t) => t.trim());
    const [from, to] = ends.split(">").map((t) => t.trim());
    const l = side ? loop(boxes[from], boxes[to], side, all) : null;
    const pts = l?.pts ?? route(boxes[from], boxes[to]);
    // stop 2px short so the arrowhead's tip touches the box
    const [x1, y1] = pts[pts.length - 2], [x2, y2] = pts[pts.length - 1], len = Math.hypot(x2 - x1, y2 - y1) || 1;
    pts[pts.length - 1] = [x2 - ((x2 - x1) / len) * 2, y2 - ((y2 - y1) / len) * 2];
    return { id: key(s), pts, loop: !!side, guard: p.nodes.find((n) => n.id === from)?.kind === "guard", label, l };
  });
  const loopEnds = edges.filter((e) => e.l?.anchor === "start").map((e) => e.l!.label[0] + (e.label?.length ?? 0) * 6.5);
  const W = Math.ceil(Math.max(...all.map((b) => b.x + b.w), ...loopEnds) + 40);
  const expand = (ids: string[]) => ids.flatMap((id) => members[id] ?? [id]);
  return { boxes, edges, W, expand };
}

function useWidth() {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(1200);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}

function Graph({ p, summaries }: { p: Pipeline; summaries: Record<string, { name: string; summary: string }> }) {
  const { boxes, edges, W, expand } = useMemo(() => layout(p), [p]);
  const [step, setStep] = useState(-1);
  const [playing, setPlaying] = useState(false);
  const [sel, setSel] = useState<string | null>(null);
  const [ref, width] = useWidth();
  const k = Math.min(1, Math.max(0.72, width / W)); // shrink to fit; below 72% the canvas scrolls sideways (phones)
  const last = p.steps.length - 1;

  useEffect(() => {
    if (!playing) return;
    if (step >= last) { setPlaying(false); return; }
    const t = setTimeout(() => setStep((s) => s + 1), step < 0 ? 0 : STEP_MS);
    return () => clearTimeout(t);
  }, [playing, step, last]);

  const go = (i: number) => { setPlaying(false); setSel(null); setStep(Math.max(-1, Math.min(i, last))); };
  const play = () => {
    if (playing) return setPlaying(false);
    setSel(null);
    if (step >= last) setStep(-1);
    setPlaying(true);
  };
  const cur = step >= 0 ? p.steps[step] : null;
  const lit = new Set(cur ? expand(cur.nodes) : sel ? [sel] : []);
  const litEdges = new Set(cur?.edges.map(key));
  const litLayers = new Set(p.nodes.filter((n) => lit.has(n.id)).map((n) => n.layer));
  const callouts = p.steps.map((s) => midpoint(edges.find((e) => e.id === key(s.edges[0]))?.pts ?? [[0, 0]]));
  const node = sel ? p.nodes.find((n) => n.id === sel) : undefined;
  const agent = node?.agent ? summaries[node.agent] : undefined;

  return (
    <>
      <div ref={ref} className="overflow-x-auto bg-surface-2"
        style={{ backgroundImage: `radial-gradient(${a("border-strong", 0.55)} 1px, transparent 1px)`, backgroundSize: "18px 18px" }}>
        <div className="relative" style={{ width: Math.max(width, W * k), height: H * k }}>
          {/* layer bands span the card; the graph itself is centred and scaled */}
          {LAYERS.map((l, i) => (
            <div key={l.id} className={cn("absolute inset-x-0 transition-colors duration-300", i < LAYERS.length - 1 && "border-b border-dashed border-border-strong")}
              style={{ top: l.top * k, height: l.h * k, background: litLayers.has(l.id) ? a(l.v, 0.06) : undefined }} />
          ))}
          <div className="absolute top-0" style={{ left: Math.max(0, (width - W * k) / 2), width: W, height: H, transform: `scale(${k})`, transformOrigin: "0 0" }}>
            {LAYERS.map((l) => (
              <div key={l.id} className="absolute left-[18px] w-[110px]" style={{ top: l.top + 14 }}>
                <div className="font-mono text-[10.5px] font-semibold tracking-[0.12em]" style={{ color: l.c }}>{l.title}</div>
                <div className="text-[11.5px] leading-[15px] text-muted-2 mt-0.5">{l.caption}</div>
              </div>
            ))}
            {(p.groups ?? []).map((g) => {
              const b = boxes[g.id];
              return (
                <div key={g.id} className="absolute rounded-[14px] border border-dashed border-border-strong" style={{ left: b.x, top: b.y, width: b.w, height: b.h }}>
                  <span className="absolute -top-2 left-3 bg-surface-2 px-1.5 font-mono text-[10px] font-semibold tracking-[0.1em] text-muted leading-4">{g.label}</span>
                  {g.note && <span className="absolute bottom-[3px] right-3 font-mono text-[9.5px] tracking-[0.1em] text-muted-2">{g.note}</span>}
                </div>
              );
            })}
            <svg width={W} height={H} className="absolute inset-0 overflow-visible" aria-hidden>
              <defs>
                {[["pa", C.muted2], ["pg", C.accent], ["pw", C.warning]].map(([id, c]) => (
                  <marker key={id} id={id} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
                    <path d="M0,0L10,5L0,10z" fill={c} />
                  </marker>
                ))}
              </defs>
              {edges.map((e) => {
                const on = litEdges.has(e.id), c = e.loop || on ? (e.guard ? C.warning : C.accent) : C.muted2;
                return (
                  <g key={e.id} className="transition-opacity duration-300" opacity={cur && !on ? 0.2 : e.loop && !on ? 0.75 : 1}>
                    <path d={`M${e.pts.map((q) => q.join(" ")).join("L")}`} fill="none" stroke={c} strokeWidth={1.4}
                      strokeDasharray={e.loop && !on ? "5 4" : undefined} className={on ? "edge-flow" : undefined}
                      markerEnd={`url(#${c === C.muted2 ? "pa" : c === C.warning ? "pw" : "pg"})`} />
                    {e.label && e.l && (() => {
                      const t = labelAt(e.l, e.label, callouts);
                      return <text x={t.x} y={t.y} textAnchor={t.anchor} fontSize="10.5" fill={c} className="font-mono">{e.label}</text>;
                    })()}
                  </g>
                );
              })}
            </svg>
            {p.nodes.map((n) => {
              const b = boxes[n.id], s = KIND[n.kind], on = lit.has(n.id);
              return (
                <button key={n.id} type="button" onClick={() => { setPlaying(false); setStep(-1); setSel(n.id); }}
                  aria-label={`${n.name}: ${n.does}`}
                  className={cn("absolute flex flex-col justify-center rounded-[11px] border text-left transition-all duration-300 hover:brightness-110",
                    isChip(n) ? "items-center px-1.5" : "px-[11px] py-1", cur && !on && "opacity-30", on && "-translate-y-0.5")}
                  style={{ left: b.x, top: b.y, width: b.w, height: b.h, borderColor: s.border, borderStyle: s.dashed ? "dashed" : "solid",
                    borderWidth: n.kind === "out" ? 1.5 : 1, background: s.bg ?? C.surface,
                    boxShadow: on ? `0 0 0 1px ${s.c}, 0 0 26px ${a(s.glow, s.glow === "text" ? 0.14 : 0.35)}` : undefined,
                    outline: sel === n.id ? `2px solid ${C.accent}` : undefined, outlineOffset: 3 }}>
                  {isChip(n) ? <span className="font-mono text-[11px] font-medium truncate max-w-full" style={{ color: s.c }}>{n.name}</span> : <>
                    <span className="font-mono text-[9.5px] leading-[13px] font-semibold tracking-[0.1em] shrink-0" style={{ color: s.c }}>{s.label}</span>
                    <span className="text-[13.5px] leading-[18px] font-semibold text-text truncate max-w-full shrink-0 mt-0.5">{n.name}</span>
                    {n.sub && <span className="font-mono text-[10.5px] leading-[14px] text-muted truncate max-w-full shrink-0">{n.sub}</span>}
                  </>}
                </button>
              );
            })}
            {callouts.map(([x, y], i) => (
              <button key={i} type="button" onClick={() => go(i)} aria-label={`Step ${i + 1}: ${p.steps[i].title}`} title={`Step ${i + 1}: ${p.steps[i].title}`}
                className={cn("absolute z-10 grid h-[22px] w-[22px] place-items-center rounded-full border-2 border-surface-2 text-[11.5px] font-bold transition-all duration-200",
                  step === i ? "bg-accent text-on-accent scale-[1.3]" : "bg-text text-surface hover:scale-110", cur && step !== i && "opacity-45")}
                style={{ left: x - 11, top: y - 11, boxShadow: step === i ? `0 0 16px ${a("accent", 0.6)}` : undefined }}>
                {i + 1}
              </button>
            ))}
          </div>
        </div>
      </div>
      <div className="grid gap-4 px-5 py-4 border-t border-border sm:grid-cols-[1fr_auto] items-start">
        <div className="min-w-0">
          <div className="flex gap-1 mb-2.5">
            {p.steps.map((s, i) => (
              <button key={s.title} type="button" onClick={() => go(i)} aria-label={`Step ${i + 1}: ${s.title}`}
                className={cn("h-[3px] flex-1 rounded-full", i < step ? "bg-accent/55" : i === step ? "bg-accent" : "bg-surface-3")} />
            ))}
          </div>
          {cur ? <>
            <div className="flex items-center gap-2 font-mono text-[11px] font-semibold tracking-[0.1em]" style={{ color: cur.nodes.some((id) => p.nodes.find((n) => n.id === id)?.kind === "guard") ? C.warning : C.accent }}>
              <span className="grid h-[18px] w-[18px] place-items-center rounded-full bg-current text-[10.5px]"><span className="text-surface">{step + 1}</span></span>
              STEP {step + 1} OF {p.steps.length} · {cur.title.toUpperCase()}
            </div>
            <p className="mt-1.5 text-[14px] leading-[22px] text-text-2 max-w-4xl">{cur.text}</p>
            {cur.io && <div className="mt-2 flex flex-wrap gap-1.5">{cur.io.map((x) => <span key={x} className="font-mono text-[11.5px] rounded-md border border-border bg-surface-2 px-2 py-0.5 text-text-2">{x}</span>)}</div>}
          </> : node ? <>
            <div className="font-mono text-[11px] font-semibold tracking-[0.1em]" style={{ color: KIND[node.kind].c }}>{KIND[node.kind].label} · {node.name.toUpperCase()}</div>
            <p className="mt-1.5 text-[14px] leading-[22px] text-text-2 max-w-4xl">{node.does}</p>
            {agent && <p className="mt-1 text-[12.5px] leading-[19px] text-muted max-w-4xl"><span className="font-mono">{agent.name}</span> · {agent.summary}</p>}
          </> : <>
            <div className="font-mono text-[11px] font-semibold tracking-[0.1em] text-accent">{p.name.toUpperCase()} · READY · {p.steps.length} STEPS</div>
            <p className="mt-1.5 text-[14px] leading-[22px] text-text-2">Press <b>▶ Play run</b> to watch a run step by step, click a numbered circle to jump to a step, or click any box to see what it does.</p>
          </>}
        </div>
        <div className="flex gap-1.5">
          <button type="button" onClick={() => go(step - 1)} aria-label="Previous step" className={STEP_BTN}>◀</button>
          <button type="button" onClick={() => go(step + 1)} aria-label="Next step" className={STEP_BTN}>▶</button>
          <button type="button" onClick={play} className="h-[34px] rounded-lg bg-accent px-3 text-[13px] font-semibold text-on-accent hover:bg-accent-hover">
            {playing ? "❚❚ Pause" : "▶ Play run"}
          </button>
        </div>
      </div>
    </>
  );
}

function Legend() {
  const sw = (k: PipelineKind) => ({ borderColor: KIND[k].c, borderStyle: KIND[k].dashed ? "dashed" : "solid", background: KIND[k].bg });
  return (
    <div className="flex flex-wrap gap-x-[18px] gap-y-1.5 px-5 py-3 border-t border-border font-mono text-[11.5px] text-muted">
      {([["source", "Data source"], ["llm", "LLM agent"], ["code", "Code, no AI"], ["guard", "Guardrail"], ["trigger", "Trigger"], ["human", "A person"], ["out", "Delivery"]] as const).map(([k, t]) => (
        <span key={k} className="flex items-center gap-1.5"><i className="inline-block h-2.5 w-3.5 rounded-[3px] border" style={sw(k)} />{t}</span>
      ))}
      <span className="text-accent">- - → loop back</span>
      <span className="flex items-center gap-1.5"><b className="grid h-4 w-4 place-items-center rounded-full bg-text text-[10px] text-surface">1</b>step of a run</span>
    </div>
  );
}

export default function PipelinesPage() {
  const { data, isLoading } = useAgentCatalog();
  const pipelines = useMemo(() => data?.pipelines ?? [], [data]);
  const [pick, setPick] = useState<string | null>(null);
  const p = pipelines.find((x) => x.id === pick) ?? pipelines[0];
  const summaries = useMemo(() => Object.fromEntries((data?.agents ?? []).map((x) => [x.id, x])), [data]);
  const agentCount = new Set(pipelines.flatMap((x) => x.nodes.flatMap((n) => (n.agent ? [n.agent] : [])))).size;

  if (isLoading) return <div className="p-4 md:p-8 text-sm text-muted">Loading agents…</div>;

  const llms = p ? new Set(p.nodes.flatMap((n) => (n.agent ? [n.agent] : []))).size : 0;
  const sources = p ? p.nodes.filter((n) => n.kind === "source").length : 0;
  return (
    <div className="p-4 md:p-8 space-y-5">
      <PageIntro kicker="Agents · Architecture" title="How ARC's agents are built"
        steps={["Data sources", "Agents", "Guardrails", "Delivery"]}
        when={{ label: `${agentCount} agents`, value: `${pipelines.length} pipelines` }}>
        Every ARC product is a pipeline in four layers: data sources feed LLM agents, code guardrails check every number
        they write, and the result is delivered to you. Pick a pipeline and press ▶ Play run to watch one run, step by step.
      </PageIntro>
      {p ? (
        <Card className="overflow-hidden">
          <div className="flex flex-wrap gap-1.5 px-4 py-3.5 border-b border-border">
            {pipelines.map((x) => (
              <button key={x.id} type="button" onClick={() => setPick(x.id)}
                className={cn("font-mono text-[12.5px] px-2.5 py-1.5 rounded-lg border",
                  x.id === p.id ? "text-accent border-accent/45 bg-accent-soft" : "text-muted border-transparent hover:text-text hover:bg-surface-3")}>
                {x.id}
              </button>
            ))}
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-border border-b border-border font-mono">
            {[["TRIGGER", p.trigger], ["AGENTS", `${llms} LLM agent${llms === 1 ? "" : "s"} · ${sources} data source${sources === 1 ? "" : "s"}`], ["GUARDRAILS", p.guardrails], ["DELIVERY", p.delivery]].map(([k, v]) => (
              <div key={k} className="bg-surface px-4 py-2.5">
                <div className="text-[10.5px] font-semibold tracking-[0.12em] text-muted-2">{k}</div>
                <div className="text-[13px] text-text mt-0.5">{v}</div>
              </div>
            ))}
          </div>
          <Graph key={p.id} p={p} summaries={summaries} />
          <Legend />
        </Card>
      ) : <Card className="p-4 md:p-8 text-sm text-muted">No pipelines to show yet.</Card>}
    </div>
  );
}
