import { useEffect, useRef, useState } from "react";
import type { AgentSystem, SystemLane } from "@/api/endpoints";
import { cn } from "@/lib/cn";

// Layout: each step is a column, the boxes in a step stack (parallel), and every box in a
// step links to every box in the next (fan-out / fan-in). Boxes are HTML so text wraps;
// edges, loops and regions are an SVG layer underneath.
const H = 50, ROW = 12, PAD = 4;
const KINDS = ["agent", "code", "gate", "end", "system"] as const;
type Kind = (typeof KINDS)[number] | "input";

function parse(box: string) {
  const i = box.indexOf(":");
  const k = i > 0 ? box.slice(0, i) : "";
  const kind: Kind = (KINDS as readonly string[]).includes(k) ? (k as Kind) : "input";
  const [text, caption] = (kind === "input" ? box : box.slice(i + 1)).split("|");
  return { kind, text, caption };
}

const BOX: Record<Kind, string> = {
  agent: "bg-accent-soft border-accent text-accent font-semibold cursor-pointer hover:bg-accent-soft-2",
  system: "bg-surface border-[1.5px] border-accent text-accent font-semibold cursor-pointer hover:bg-accent-soft",
  code: "bg-surface-2 border-dashed border-muted-2 text-muted",
  gate: "bg-warning-soft border-warning text-warning font-semibold",
  end: "bg-surface border-[1.5px] border-text-2 text-text-2 font-semibold",
  input: "bg-surface border-border text-text-2",
};

function Lane({ lane, width, names, onAgent, onSystem }: {
  lane: SystemLane; width: number; names: Record<string, string>;
  onAgent: (id: string) => void; onSystem: (group: string) => void;
}) {
  // shrink to fit the card; below the minimum the lane scrolls sideways (phones)
  const n = lane.flow.length;
  const GAP = n >= 5 ? 24 : 36; // lanes are ≤ 5 steps (tests/test_agent_catalog.py)
  const W = Math.max(84, Math.min(140, (width - PAD * 2 - (n - 1) * GAP) / n));
  const top = (lane.loops?.length ? 36 : 0) + (lane.regions?.length ? 22 : 0) + 6;
  const tallest = Math.max(...lane.flow.map((s) => s.length));
  const inner = tallest * H + (tallest - 1) * ROW;
  const x = (i: number) => PAD + i * (W + GAP);
  const cols = lane.flow.map((step, i) => {
    const y0 = top + (inner - (step.length * H + (step.length - 1) * ROW)) / 2;
    return step.map((b, j) => ({ ...parse(b), x: x(i), y: y0 + j * (H + ROW) }));
  });
  const w = PAD * 2 + n * (W + GAP) - GAP;
  const h = top + inner + (lane.regions?.length ? 10 : 4);
  const colTop = (i: number) => Math.min(...cols[i].map((c) => c.y));

  return (
    <div className="overflow-x-auto">
      <div className="relative" style={{ width: w, height: h }}>
        <svg width={w} height={h} className="absolute inset-0 overflow-visible">
          <defs>
            {[["ar", "#a1a1aa"], ["arg", "#008744"]].map(([id, c]) => (
              <marker key={id} id={id} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
                <path d="M0,0L10,5L0,10z" fill={c} />
              </marker>
            ))}
          </defs>
          {lane.regions?.map((r) => (
            <g key={r.label}>
              <rect x={x(r.from) - 12} y={top - 22} width={x(r.to) + W + 12 - (x(r.from) - 12)} height={inner + 30}
                rx="12" fill="#f3f8f5" stroke="#cfe8da" strokeDasharray="5 4" />
              <text x={x(r.from) - 2} y={top - 8} fontSize="10" fontWeight="600" letterSpacing="1" fill="#008744">
                {r.label.toUpperCase()}
              </text>
            </g>
          ))}
          {cols.slice(0, -1).flatMap((col, i) => col.flatMap((a) => cols[i + 1].map((b) => {
            const x1 = a.x + W, y1 = a.y + H / 2, x2 = b.x - 2, y2 = b.y + H / 2, m = (x1 + x2) / 2;
            return <path key={`${i}-${a.y}-${b.y}`} d={`M${x1} ${y1}C${m} ${y1} ${m} ${y2} ${x2} ${y2}`}
              stroke="#a1a1aa" strokeWidth="1.4" fill="none" markerEnd="url(#ar)" />;
          })))}
          {lane.loops?.map((l) => {
            const xa = x(l.from) + W / 2, xb = x(l.to) + W / 2 + 8, yt = 16;
            return (
              <g key={l.label}>
                <path d={`M${xa} ${colTop(l.from)}V${yt + 6}Q${xa} ${yt} ${xa - 6} ${yt}H${xb + 6}Q${xb} ${yt} ${xb} ${yt + 6}V${colTop(l.to) - 2}`}
                  stroke="#008744" strokeWidth="1.4" strokeDasharray="5 4" fill="none" markerEnd="url(#arg)" />
                <text x={(xa + xb) / 2} y={yt - 3} textAnchor="middle" fontSize="10.5" fill="#008744">{l.label}</text>
              </g>
            );
          })}
        </svg>
        {cols.flat().map((b, k) => {
          const click = b.kind === "agent" ? () => onAgent(b.text) : b.kind === "system" ? () => onSystem(b.text) : undefined;
          const label = b.kind === "agent" ? (names[b.text] ?? b.text).replace(/^.*· /, "") : b.text;
          return (
            <div key={k} onClick={click} title={b.kind === "agent" ? names[b.text] : undefined}
              className={cn("absolute flex flex-col items-center justify-center text-center rounded-[10px] border px-1.5 overflow-hidden text-xs leading-[15px]", BOX[b.kind])}
              style={{ left: b.x, top: b.y, width: W, height: H }}>
              <span>{b.kind === "system" && "⬚ "}{label}</span>
              {b.caption && <span className="text-[10.5px] leading-[13px] font-normal opacity-75 mt-0.5">{b.caption}</span>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Key({ cls, children }: { cls: string; children: React.ReactNode }) {
  return <span className="flex items-center gap-1.5"><i className={cn("inline-block w-3.5 h-2.5 rounded-[3px] border", cls)} />{children}</span>;
}

export function SystemDiagram({ system, names, onAgent, onSystem }: {
  system: AgentSystem; names: Record<string, string>;
  onAgent: (id: string) => void; onSystem: (group: string) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(800);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  return (
    <>
      <div className="px-6 py-5 border-b border-border">
        <div className="text-lg font-semibold">{system.group} <span className="font-normal text-muted">· architecture</span></div>
        <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-sm mt-2.5">
          <b className="font-semibold text-text-2">Starts when</b><span className="text-muted">{system.trigger}</span>
          <b className="font-semibold text-text-2">Produces</b><span className="text-muted">{system.output}</span>
        </div>
        <div className="text-sm text-muted mt-2">{system.blurb}</div>
      </div>
      <div ref={ref} className="mx-6" />
      {system.lanes.map((lane) => (
        <div key={lane.title} className="px-6 pt-4 pb-5 border-b border-border">
          {system.lanes.length > 1 && <div className="text-xs font-semibold uppercase tracking-wide text-muted mb-2">{lane.title}</div>}
          <Lane lane={lane} width={width} names={names} onAgent={onAgent} onSystem={onSystem} />
        </div>
      ))}
      <div className="flex flex-wrap gap-x-4 gap-y-1.5 px-6 py-3 text-xs text-muted">
        <Key cls="bg-accent-soft border-accent">LLM agent: click to open</Key>
        <Key cls="bg-surface-2 border-dashed border-muted-2">deterministic code</Key>
        <Key cls="bg-warning-soft border-warning">waits for a human</Key>
        <Key cls="border-accent">⬚ another system: click</Key>
        <span className="text-accent">⇢ dashed green = loop back</span>
      </div>
    </>
  );
}
