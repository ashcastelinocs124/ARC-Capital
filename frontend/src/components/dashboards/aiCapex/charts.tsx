import { createContext, useContext, type ReactNode } from "react";
import { usd, type Mix } from "@/api/aiCapex";
import { C } from "@/lib/theme";
import { change, useHover, type Tip } from "./hover";

// Hand-drawn SVG charts for the AI Demand & Capex dashboard (as in components/weekAhead/). Every chart
// is role="img" with an aria-label, and every bar carries its name and value as text, so color is never
// the only way to read it. Hovering (or arrow keys, once the chart has focus) shows each item's detail.

// the canvas width the charts are drawn on: a wider canvas draws the same chart smaller on screen
const Width = createContext(420);
export const ChartWidth = Width.Provider;
export const SMALLER = 520; // about a fifth smaller on screen than the default 420

export function ChartTitle({ children }: { children: ReactNode }) {
  return <div className="eyebrow mb-1.5">{children}</div>;
}

export function Legend({ items }: { items: [string, string][] }) {
  return (
    <div className="flex flex-wrap gap-x-3.5 gap-y-1 text-xs text-text-2 mb-2">
      {items.map(([n, c]) => (
        <span key={n} className="flex items-center gap-1.5">
          <i className="inline-block w-2.5 h-2.5 rounded-sm" style={{ background: c }} aria-hidden />{n}
        </span>
      ))}
    </div>
  );
}

const nice = (v: number) => {
  const p = 10 ** Math.floor(Math.log10(Math.max(v, 1)));
  return Math.ceil(v / p / 2) * 2 * p;
};

function Txt({ x, y, children, anchor = "start", fill = C.muted, size = 11, weight = 400 }: {
  x: number; y: number; children: ReactNode; anchor?: "start" | "middle" | "end"; fill?: string; size?: number; weight?: number;
}) {
  return <text x={x} y={y} textAnchor={anchor} fontSize={size} fill={fill} fontWeight={weight}>{children}</text>;
}

const hint = " Hover an item, or focus the chart and use the arrow keys, for its detail.";

/** Quarterly bars stacked by company, the total above each bar and a note under a partial quarter.
 * Hovering a segment shows that company's quarter and lights its segments in every bar. */
export function StackedBars({ labels, names, series, totals, label, height = 240 }: {
  labels: string[];
  names?: string[]; // each quarter in full ("Q2 2026") for the tooltip
  series: { key: string; name: string; color: string; values: (number | null)[] }[];
  totals: { total: number; note?: string }[];
  label: string;
  height?: number;
}) {
  const W = useContext(Width);
  const L = 34, R = 8, T = 18, B = height - 34;
  const max = nice(Math.max(...totals.map((t) => t.total), 1));
  const bw = (W - L - R) / Math.max(labels.length, 1);
  const y = (v: number) => B - (v / max) * (B - T);
  const nS = series.length;
  const tips: Tip[] = labels.flatMap((q, qi) => series.map((s) => {
    const v = s.values[qi] ?? 0;
    const total = totals[qi]?.total ?? 0;
    const yoy = qi >= 4 ? change(v, s.values[qi - 4]) : null;
    return {
      title: `${s.name} · ${names?.[qi] ?? q}`,
      lines: [
        `Capex ${usd(v)}`,
        ...(total ? [`${Math.round((v / total) * 100)}% of the quarter's ${usd(total)}`] : []),
        ...(yoy ? [`${yoy} on a year ago`] : []),
        ...(totals[qi]?.note ? [`${totals[qi].note} companies have filed this quarter`] : []),
      ],
    };
  }));
  const h = useHover(tips);
  const lit = h.active == null ? null : h.active % nS; // the hovered company, across every bar
  return (
    <div {...h.chart}>
      <svg viewBox={`0 0 ${W} ${height}`} className="w-full h-auto overflow-visible" role="img" aria-label={label + hint}>
        {[0, 0.25, 0.5, 0.75, 1].map((f) => (
          <g key={f}>
            <line x1={L} x2={W - R} y1={y(max * f)} y2={y(max * f)} stroke={C.grid} />
            <Txt x={L - 6} y={y(max * f) + 4} anchor="end">{Math.round(max * f)}</Txt>
          </g>
        ))}
        {labels.map((q, qi) => {
          let base = 0;
          const x = L + qi * bw + bw * 0.16, w = bw * 0.68;
          return (
            <g key={q}>
              {series.map((s, si) => {
                const v = s.values[qi] ?? 0;
                const r = (
                  <rect key={s.key} {...h.item(qi * nS + si)} x={x} y={y(base + v)} width={w}
                    height={Math.max(0, y(base) - y(base + v) - 1)} fill={s.color} opacity={lit == null || lit === si ? 1 : 0.28}
                    stroke={h.active === qi * nS + si ? C.text : "none"} strokeWidth={1.5} />
                );
                base += v;
                return r;
              })}
              <Txt x={x + w / 2} y={y(base) - 5} anchor="middle" fill={C.text2} size={10.5} weight={600}>{Math.round(totals[qi]?.total ?? base)}</Txt>
              {(qi % 3 === 0 || qi === labels.length - 1) && <Txt x={x + w / 2} y={B + 15} anchor="middle">{q}</Txt>}
              {totals[qi]?.note && <Txt x={x + w / 2} y={B + 28} anchor="middle" fill={C.text2} size={9.5} weight={600}>{totals[qi].note}</Txt>}
            </g>
          );
        })}
      </svg>
      {h.node}
    </div>
  );
}

/** Horizontal bars, one row a company: an optional tick for a year ago and an optional dashed line. */
export function HBars({ rows, max, fmt, refLine, ghostLabel, label }: {
  rows: { name: string; value: number | null; ghost?: number | null; color: string; tip?: Tip }[];
  max: number;
  fmt: (v: number) => string;
  refLine?: { at: number; label: string };
  ghostLabel?: string;
  label: string;
}) {
  const W = useContext(Width);
  const RH = 27, L = 84, R = 56, H = rows.length * RH + 30;
  const x = (v: number) => L + (Math.min(v, max) / max) * (W - L - R);
  const b = rows.length * RH;
  const h = useHover(rows.map((r) => r.tip ?? {
    title: r.name,
    lines: [r.value == null ? "Not meaningful" : fmt(r.value), ...(r.ghost != null ? [`A year ago: ${fmt(r.ghost)}`] : [])],
  }));
  return (
    <div {...h.chart}>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto overflow-visible" role="img" aria-label={label + hint}>
        {rows.map((r, i) => {
          const y = 6 + i * RH;
          return (
            <g key={r.name} {...h.item(i)} opacity={h.dim(h.active === i)}>
              <rect x={0} y={y} width={W} height={RH - 2} fill="transparent" />
              <Txt x={L - 8} y={y + 15} anchor="end" fill={C.text} size={12} weight={h.active === i ? 700 : 400}>{r.name}</Txt>
              {r.value == null ? (
                <Txt x={L} y={y + 15} fill={C.muted}>n/m</Txt>
              ) : (
                <>
                  <rect x={L} y={y + 5} width={Math.max(1, x(r.value) - L)} height={RH - 12} rx={3} fill={r.color} />
                  {r.value > max && <Txt x={x(r.value) - 4} y={y + 15} anchor="end" fill={C.ink} size={12} weight={700}>»</Txt>}
                  <Txt x={x(r.value) + 6} y={y + 15} fill={C.text2} size={11.5} weight={600}>{fmt(r.value)}</Txt>
                </>
              )}
              {r.ghost != null && <line x1={x(r.ghost)} x2={x(r.ghost)} y1={y + 1} y2={y + RH - 3} stroke={C.text} strokeWidth={2} />}
            </g>
          );
        })}
        {refLine && (
          <g>
            <line x1={x(refLine.at)} x2={x(refLine.at)} y1={0} y2={b + 6} stroke={C.muted} strokeDasharray="4 3" />
            <Txt x={x(refLine.at)} y={b + 22} anchor="middle">{refLine.label}</Txt>
          </g>
        )}
        {ghostLabel && (
          <g>
            <line x1={L} x2={L} y1={b + 12} y2={b + 24} stroke={C.text} strokeWidth={2} />
            <Txt x={L + 6} y={b + 22}>{ghostLabel}</Txt>
          </g>
        )}
      </svg>
      {h.node}
    </div>
  );
}

/** Last full-year actual (grey) against the latest guidance (colored range), each with its own year. */
export function GuidanceRows({ rows, label }: {
  rows: { name: string; color: string; actual: number | null; low: number | null; high: number | null; text: string; tip?: Tip }[];
  label: string;
}) {
  const W = useContext(Width);
  const RH = 34, L = 84, R = 8, H = rows.length * RH + 28;
  const max = nice(Math.max(...rows.flatMap((r) => [r.actual ?? 0, r.high ?? 0]), 1));
  const x = (v: number) => L + (v / max) * (W - L - R) * 0.62;
  const h = useHover(rows.map((r) => r.tip ?? { title: r.name, lines: [r.text] }));
  return (
    <div {...h.chart}>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto overflow-visible" role="img" aria-label={label + hint}>
        {rows.map((r, i) => {
          const y = 4 + i * RH;
          return (
            <g key={r.name} {...h.item(i)} opacity={h.dim(h.active === i)}>
              <rect x={0} y={y} width={W} height={RH - 4} fill="transparent" />
              <Txt x={L - 8} y={y + 15} anchor="end" fill={C.text} size={12} weight={h.active === i ? 700 : 400}>{r.name}</Txt>
              {r.actual != null && <rect x={L} y={y + 9} width={x(r.actual) - L} height={8} rx={2} fill={C.borderStrong} />}
              {r.low != null && r.high != null && (
                <rect x={x(r.low)} y={y + 5} width={Math.max(10, x(r.high) - x(r.low))} height={16} rx={3} fill={r.color} />
              )}
              <Txt x={r.high != null ? x(r.high) + 12 : L} y={y + 17} fill={C.text2} size={11}>{r.text}</Txt>
            </g>
          );
        })}
        {/* the "last full year" key only when one is drawn: the cited search rarely returns it */}
        {rows.some((r) => r.actual != null) && (
          <>
            <rect x={L} y={rows.length * RH + 12} width={14} height={8} fill={C.borderStrong} />
            <Txt x={L + 20} y={rows.length * RH + 20}>last full year</Txt>
          </>
        )}
        <rect x={L + 110} y={rows.length * RH + 10} width={14} height={12} rx={2} fill={C.text2} />
        <Txt x={L + 130} y={rows.length * RH + 20}>latest guidance (cited)</Txt>
      </svg>
      {h.node}
    </div>
  );
}

/** A year ago (hollow) to now (filled), per company. */
export function Dumbbell({ rows, label }: {
  rows: { name: string; color: string; from: number | null; to: number; fmt: string; tip?: Tip }[];
  label: string;
}) {
  const W = useContext(Width);
  const RH = 30, L = 84, R = 56, H = rows.length * RH + 34;
  const max = nice(Math.max(...rows.map((r) => Math.max(r.to, r.from ?? 0)), 1));
  const x = (v: number) => L + (v / max) * (W - L - R);
  const b = rows.length * RH;
  const h = useHover(rows.map((r) => r.tip ?? {
    title: r.name,
    lines: [`Latest ${r.fmt}`, ...(r.from != null ? [`A year ago ${usd(r.from)}`, `${change(r.to, r.from)} in a year`] : ["No year-ago figure"])],
  }));
  return (
    <div {...h.chart}>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto overflow-visible" role="img" aria-label={label + hint}>
        {[0, 0.5, 1].map((f) => (
          <g key={f}>
            <line x1={x(max * f)} x2={x(max * f)} y1={0} y2={b} stroke={C.grid} />
            <Txt x={x(max * f)} y={b + 14} anchor="middle">{`$${Math.round(max * f)}bn`}</Txt>
          </g>
        ))}
        {rows.map((r, i) => {
          const y = 14 + i * RH;
          return (
            <g key={r.name} {...h.item(i)} opacity={h.dim(h.active === i)}>
              <rect x={0} y={y - RH / 2} width={W} height={RH} fill="transparent" />
              <Txt x={L - 8} y={y + 4} anchor="end" fill={C.text} size={12} weight={h.active === i ? 700 : 400}>{r.name}</Txt>
              {r.from != null && (
                <>
                  <line x1={x(r.from)} x2={x(r.to)} y1={y} y2={y} stroke={r.color} strokeWidth={3} opacity={0.55} />
                  <circle cx={x(r.from)} cy={y} r={5} fill={C.surface} stroke={r.color} strokeWidth={2} />
                </>
              )}
              <circle cx={x(r.to)} cy={y} r={h.active === i ? 7.5 : 6} fill={r.color} />
              <Txt x={x(r.to) + 10} y={y + 4} fill={C.text2} size={11.5} weight={600}>{r.fmt}</Txt>
            </g>
          );
        })}
        <circle cx={L + 4} cy={b + 26} r={4} fill={C.surface} stroke={C.text} strokeWidth={2} />
        <Txt x={L + 12} y={b + 30}>a year ago</Txt>
        <circle cx={L + 90} cy={b + 26} r={5} fill={C.text} />
        <Txt x={L + 98} y={b + 30}>latest</Txt>
      </svg>
      {h.node}
    </div>
  );
}

/** One dot per bond or loan against reference lines (the 10-year Treasury, high-yield bonds). */
export function DotRows({ rows, refs, label }: {
  rows: { name: string; sub: string; value: number; color: string; tip?: Tip }[];
  refs: { at: number; label: string }[];
  label: string;
}) {
  const W = useContext(Width);
  const RH = 24, L = 170, R = 40, top = 18, H = rows.length * RH + top + 34;
  const max = Math.max(10, Math.ceil(Math.max(...rows.map((r) => r.value), ...refs.map((r) => r.at)) / 2) * 2);
  const x = (v: number) => L + (v / max) * (W - L - R);
  const b = top + rows.length * RH;
  const h = useHover(rows.map((r) => r.tip ?? { title: r.name, lines: [r.sub, `${r.value}%`] }));
  return (
    <div {...h.chart}>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto overflow-visible" role="img" aria-label={label + hint}>
        {refs.map((r, k) => (
          <g key={r.label}>
            <line x1={x(r.at)} x2={x(r.at)} y1={top - 4} y2={b} stroke={C.muted} strokeDasharray="4 3" />
            <Txt x={x(r.at)} y={k ? top - 7 : b + 14} anchor="middle" size={10.5}>{r.label}</Txt>
          </g>
        ))}
        {Array.from({ length: max / 2 + 1 }, (_, i) => i * 2).map((v) => (
          <Txt key={v} x={x(v)} y={b + 28} anchor="middle" size={10}>{`${v}%`}</Txt>
        ))}
        {rows.map((r, i) => {
          const y = top + i * RH + 12;
          return (
            <g key={`${r.name}-${r.sub}-${i}`} {...h.item(i)} opacity={h.dim(h.active === i)}>
              <rect x={0} y={y - RH / 2} width={W} height={RH} fill="transparent" />
              <text x={L - 8} y={y + 4} textAnchor="end" fontSize={11.5} fill={C.muted}>
                {/* cut long labels: they'd run left out of the chart, over its neighbour (the tooltip has it whole) */}
                <tspan fill={C.text} fontWeight={600}>{r.name}</tspan> · {r.sub.length > 17 ? `${r.sub.slice(0, 16)}…` : r.sub}
              </text>
              <line x1={L} x2={W - R} y1={y} y2={y} stroke={C.grid} />
              <circle cx={x(r.value)} cy={y} r={h.active === i ? 7.5 : 6} fill={r.color} />
              <Txt x={x(r.value) + 10} y={y + 4} fill={C.text2} weight={600}>{`${r.value}%`}</Txt>
            </g>
          );
        })}
      </svg>
      {h.node}
    </div>
  );
}

// colors chosen so the near-black % label (C.ink) passes 4.5:1 on each, in both themes
export const MIX_PARTS: [keyof Mix, string, string][] = [
  ["own_cash", "Own operating cash", C.muted2],
  ["debt", "New debt", C.jobs],
  ["convertible", "Convertible notes", C.warning],
  ["shares", "New shares", C.inflation],
  ["cash_on_hand", "Cash on hand", C.earnings],
];

/** Where each company's cash for capex came from, as one 100% bar per company. Hovering a segment
 * shows the company's whole mix and lights that source in every row. */
export function Mix100({ rows, label }: { rows: { name: string; mix: Mix }[]; label: string }) {
  const W = useContext(Width);
  const RH = 26, L = 84, R = 4, H = rows.length * RH + 6;
  const x = (p: number) => L + (p / 100) * (W - L - R);
  const cells = rows.flatMap((r, ri) => MIX_PARTS.filter(([k]) => r.mix[k] > 0).map(([k], pi) => ({ ri, k, pi })));
  const h = useHover(cells.map(({ ri, k }) => {
    const r = rows[ri];
    return {
      title: `${r.name} · ${MIX_PARTS.find(([p]) => p === k)![1]} ${r.mix[k]}%`,
      lines: [
        "Share of all the cash that came in over the last four quarters:",
        ...MIX_PARTS.filter(([p]) => r.mix[p] > 0 && p !== k).map(([p, n]) => `${n} ${r.mix[p]}%`),
      ],
    };
  }));
  const lit = h.active == null ? null : cells[h.active].k; // the hovered source, in every row
  let n = 0;
  return (
    <div {...h.chart}>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto overflow-visible" role="img" aria-label={label + hint}>
        {rows.map((r, i) => {
          const y = 3 + i * RH;
          let acc = 0;
          return (
            <g key={r.name}>
              <Txt x={L - 8} y={y + 15} anchor="end" fill={C.text} size={12}>{r.name}</Txt>
              {MIX_PARTS.map(([k, , color]) => {
                const p = r.mix[k];
                if (!p) return null;
                const x0 = x(acc);
                acc += p;
                const idx = n++;
                return (
                  <g key={k} {...h.item(idx)} opacity={lit == null || lit === k ? 1 : 0.3}>
                    <rect x={x0} y={y + 3} width={Math.max(0, x(acc) - x0 - 1)} height={RH - 8} fill={color}
                      stroke={h.active === idx ? C.text : "none"} strokeWidth={1.5} />
                    {p >= 10 && <Txt x={(x0 + x(acc)) / 2} y={y + 15} anchor="middle" fill={C.ink} size={10.5} weight={700}>{`${p}%`}</Txt>}
                  </g>
                );
              })}
            </g>
          );
        })}
      </svg>
      {h.node}
    </div>
  );
}

/** Power online (filled) inside power contracted (outline), in GW. */
export function PowerBars({ rows, label }: {
  rows: { name: string; online: number; contracted: number; color: string; cited?: boolean; tip?: Tip }[];
  label: string;
}) {
  const W = useContext(Width);
  const RH = 30, L = 84, R = 112, H = rows.length * RH + 30;
  const max = Math.max(...rows.map((r) => r.contracted), 1);
  const x = (v: number) => L + (v / max) * (W - L - R);
  const h = useHover(rows.map((r) => r.tip ?? {
    title: r.name,
    lines: [
      `${r.online.toFixed(2)} GW running`,
      `${r.contracted.toFixed(1)} GW contracted`,
      `${Math.round((r.online / r.contracted) * 100)}% online; ${(r.contracted - r.online).toFixed(1)} GW still to come`,
      ...(r.cited ? ["Private company: from a cited search"] : []),
    ],
  }));
  return (
    <div {...h.chart}>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto overflow-visible" role="img" aria-label={label + hint}>
        {rows.map((r, i) => {
          const y = 6 + i * RH;
          return (
            <g key={r.name} {...h.item(i)} opacity={h.dim(h.active === i)}>
              <rect x={0} y={y} width={W} height={RH - 2} fill="transparent" />
              <Txt x={L - 8} y={y + 14} anchor="end" fill={C.text} size={12} weight={h.active === i ? 700 : 400}>{r.name}</Txt>
              {r.cited && <Txt x={L - 8} y={y + 25} anchor="end" size={9.5}>private · cited</Txt>}
              <rect x={L} y={y + 4} width={x(r.contracted) - L} height={RH - 12} rx={3} fill="none" stroke={r.color} strokeWidth={1.5} strokeDasharray={r.cited ? "3 2" : undefined} />
              <rect x={L} y={y + 4} width={Math.max(1, x(r.online) - L)} height={RH - 12} rx={3} fill={r.color} />
              <Txt x={x(r.contracted) + 6} y={y + 15} fill={C.text2} weight={600}>
                {`${r.online.toFixed(2)} of ${r.contracted.toFixed(1)} GW · ${Math.round((r.online / r.contracted) * 100)}%`}
              </Txt>
            </g>
          );
        })}
        <rect x={L} y={rows.length * RH + 10} width={14} height={10} rx={2} fill={C.text2} />
        <Txt x={L + 20} y={rows.length * RH + 19}>online</Txt>
        <rect x={L + 70} y={rows.length * RH + 10} width={14} height={10} rx={2} fill="none" stroke={C.text2} />
        <Txt x={L + 90} y={rows.length * RH + 19}>contracted</Txt>
      </svg>
      {h.node}
    </div>
  );
}

/** A small line for a tile, its last point marked; each point names itself on hover. */
export function Spark({ values, tips, label }: { values: number[]; tips?: Tip[]; label: string }) {
  const h = useHover(tips ?? []);
  if (values.length < 2) return null;
  const SW = 220, SH = 46, mn = Math.min(...values), mx = Math.max(...values);
  const pts = values.map((v, i) => [(i / (values.length - 1)) * SW, SH - 4 - ((v - mn) / (mx - mn || 1)) * (SH - 8)]);
  const k = h.active ?? values.length - 1; // the point to mark: the hovered one, else the last
  return (
    <div {...h.chart}>
      <svg viewBox={`0 0 ${SW} ${SH}`} className="w-full h-auto overflow-visible" role="img" aria-label={label + (tips ? hint : "")}>
        <polyline points={pts.map((p) => p.join(",")).join(" ")} fill="none" stroke={C.accent} strokeWidth={2} strokeLinejoin="round" />
        {h.active != null && <line x1={pts[k][0]} x2={pts[k][0]} y1={0} y2={SH} stroke={C.muted2} />}
        <circle cx={pts[k][0]} cy={pts[k][1]} r={3.5} fill={C.accent} />
        {/* wide invisible columns, one per point, so the hover doesn't need pixel aim */}
        {tips && pts.map((p, i) => (
          <rect key={i} {...h.item(i)} x={p[0] - SW / values.length / 2} y={0} width={SW / values.length} height={SH} fill="transparent" />
        ))}
      </svg>
      {h.node}
    </div>
  );
}
