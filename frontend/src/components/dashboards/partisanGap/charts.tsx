import { useCallback, useRef, useState, type ReactNode } from "react";
import { C } from "@/lib/theme";
import { useHover, type Tip } from "../aiCapex/hover";

// Hand-drawn SVG charts for the Partisan Policy Gap dashboard, in the AI Demand & Capex style: every
// chart is role="img" with an aria-label, values are written on it as text (color is never the only
// cue), and hovering an item (or the arrow keys, once the chart has focus) shows its detail. Charts
// draw at their container's measured width, so text stays the same size from a phone to a desktop.

const hint = " Hover an item, or focus the chart and use the arrow keys, for its detail.";

const minus = (v: number) => (v < 0 ? "−" : "+");
export const pct = (v: number | null | undefined, d = 1) => (v == null ? "—" : `${(v * 100).toFixed(d).replace("-", "−")}%`);
export const spct = (v: number | null | undefined, d = 1) => (v == null ? "—" : `${minus(v)}${Math.abs(v * 100).toFixed(d)}%`);
export const pp = (v: number | null | undefined, d = 1) => (v == null ? "—" : `${minus(v)}${Math.abs(v * 100).toFixed(d)} pp`);
export const sgn = (v: number | null | undefined, d = 2) => (v == null ? "—" : `${minus(v)}${Math.abs(v).toFixed(d)}`);
// a p just under 0.05 keeps a 4th digit, or it reads "0.050" yet shows as significant
export const pval = (p: number | null | undefined) => (p == null ? "—" : p < 0.001 ? "<0.001" : p < 0.05 && p >= 0.0495 ? p.toFixed(4) : p.toFixed(3));
const ok = (v: number | null | undefined): v is number => v != null && !Number.isNaN(v);

function useWidth() {
  const [w, setW] = useState(420);
  const ro = useRef<ResizeObserver | null>(null);
  const ref = useCallback((el: HTMLDivElement | null) => {
    ro.current?.disconnect();
    if (!el) return;
    ro.current = new ResizeObserver(([e]) => setW(Math.max(260, Math.round(e.contentRect.width))));
    ro.current.observe(el);
  }, []);
  return [ref, w] as const;
}

function Txt({ x, y, children, anchor = "start", fill = C.muted, size = 11, weight = 400 }: {
  x: number; y: number; children: ReactNode; anchor?: "start" | "middle" | "end"; fill?: string; size?: number; weight?: number;
}) {
  return <text x={x} y={y} textAnchor={anchor} fontSize={size} fill={fill} fontWeight={weight}>{children}</text>;
}

/** Round axis bounds and ticks around [lo, hi]. */
function nice(lo: number, hi: number, n = 4) {
  if (lo === hi) [lo, hi] = [lo - 1, hi + 1];
  const raw = (hi - lo) / n, p = 10 ** Math.floor(Math.log10(raw)), f = raw / p;
  const step = (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * p;
  const a = Math.floor(lo / step + 1e-9) * step, b = Math.ceil(hi / step - 1e-9) * step;
  const ticks = Array.from({ length: Math.round((b - a) / step) + 1 }, (_, i) => +(a + i * step).toPrecision(12));
  return { lo: a, hi: b, ticks };
}

/** One or more lines over a shared x (years, or month numbers with an xFmt); `step` holds each value until the next. */
export function Lines({ xs, xFmt, xTickFmt, xTicks, series, yFmt, tickFmt, refY, height = 240, label }: {
  xs: number[];
  xFmt: (x: number) => string; // the tooltip's title
  xTickFmt?: (x: number) => string;
  xTicks?: (w: number) => number[];
  series: { name: string; color: string; values: (number | null)[]; step?: boolean; dots?: boolean[] }[];
  yFmt: (v: number) => string;
  tickFmt?: (v: number) => string;
  refY?: { at: number; label?: string };
  height?: number;
  label: string;
}) {
  const [ref, W] = useWidth();
  const tips: Tip[] = xs.map((xv, i) => ({
    title: xFmt(xv),
    lines: series.flatMap((s) => (ok(s.values[i]) ? [`${s.name}: ${yFmt(s.values[i]!)}`] : [])),
  }));
  const h = useHover(tips);
  const vals = series.flatMap((s) => s.values).filter(ok);
  const ys = nice(Math.min(...vals, refY?.at ?? Infinity), Math.max(...vals, refY?.at ?? -Infinity));
  const L = 42, R = 10, T = 8, B = height - 22;
  const x0 = xs[0], x1 = xs[xs.length - 1];
  const x = (v: number) => L + ((v - x0) / (x1 - x0 || 1)) * (W - L - R);
  const y = (v: number) => B - ((v - ys.lo) / (ys.hi - ys.lo)) * (B - T);
  const path = (s: (typeof series)[number]) => {
    let d = "", on = false;
    s.values.forEach((v, i) => {
      if (!ok(v)) return void (on = false);
      d += on ? (s.step ? `H${x(xs[i])}V${y(v)}` : `L${x(xs[i])},${y(v)}`) : `M${x(xs[i])},${y(v)}`;
      on = true;
    });
    return d;
  };
  const every = W < 480 ? 20 : 10; // years between x ticks
  const ticks = xTicks ? xTicks(W) : xs.filter((v) => v % every === 0);
  const col = (W - L - R) / Math.max(xs.length - 1, 1);
  const a = h.active;
  return (
    <div ref={ref} {...h.chart}>
      <svg viewBox={`0 0 ${W} ${height}`} width="100%" className="block overflow-visible" role="img" aria-label={label + hint}>
        {ys.ticks.map((t) => (
          <g key={t}>
            <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke={C.grid} />
            <Txt x={L - 6} y={y(t) + 4} anchor="end">{(tickFmt ?? yFmt)(t)}</Txt>
          </g>
        ))}
        {refY && (
          <g>
            <line x1={L} x2={W - R} y1={y(refY.at)} y2={y(refY.at)} stroke={C.muted} strokeDasharray="4 3" />
            {refY.label && <Txt x={W - R} y={y(refY.at) - 5} anchor="end" size={10.5}>{refY.label}</Txt>}
          </g>
        )}
        {ticks.map((t) => <Txt key={t} x={x(t)} y={B + 16} anchor="middle">{(xTickFmt ?? xFmt)(t)}</Txt>)}
        {series.map((s) => (
          <g key={s.name}>
            <path d={path(s)} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" />
            {s.dots?.map((on, i) => (on && ok(s.values[i]) ? <circle key={i} cx={x(xs[i])} cy={y(s.values[i]!)} r={3} fill={s.color} /> : null))}
          </g>
        ))}
        {a != null && (
          <g>
            <line x1={x(xs[a])} x2={x(xs[a])} y1={T} y2={B} stroke={C.muted2} />
            {series.map((s) => (ok(s.values[a]) ? <circle key={s.name} cx={x(xs[a])} cy={y(s.values[a]!)} r={3.5} fill={s.color} /> : null))}
          </g>
        )}
        {/* one invisible column per x, so the hover doesn't need pixel aim */}
        {xs.map((xv, i) => (
          <rect key={xv} {...h.item(i)} x={x(xv) - col / 2} y={T} width={col} height={B - T} fill="transparent" />
        ))}
      </svg>
      {h.node}
    </div>
  );
}

/** Vertical bars by group, one bar per series, each labelled with its value; `bands` caption runs of groups. */
export function VBars({ groups, series, values, ns, nUnit = "years", fmt, bands, tipTitle, height = 210, label }: {
  groups: string[];
  series: [string, string][]; // [name, color]
  values: (number | null)[][]; // [group][series]
  ns?: (number | null)[][];
  nUnit?: string;
  fmt: (v: number) => string;
  bands?: { from: number; label: string }[];
  tipTitle?: (g: number, s: number) => string;
  height?: number;
  label: string;
}) {
  const [ref, W] = useWidth();
  const cells = groups.flatMap((_, gi) => series.map((_, si) => [gi, si] as const)).filter(([gi, si]) => ok(values[gi][si]));
  const h = useHover(cells.map(([gi, si]) => ({
    title: tipTitle?.(gi, si) ?? (series.length > 1 ? `${groups[gi]} · ${series[si][0]}` : groups[gi]),
    lines: [`Average ${fmt(values[gi][si]!)}`, ...(ns?.[gi]?.[si] != null ? [`${ns[gi][si]} ${nUnit}`] : [])],
  })));
  const all = values.flat().filter(ok);
  const lo = Math.min(0, ...all), hi = Math.max(0, ...all), pad = (hi - lo) * 0.14;
  const L = 4, R = 4, T = bands ? 30 : 14, B = height - 24;
  const y = (v: number) => B - ((v - (lo < 0 ? lo - pad : 0)) / (hi + pad - (lo < 0 ? lo - pad : 0))) * (B - T);
  const gw = (W - L - R) / groups.length;
  const bw = Math.min(36, (gw * 0.74) / series.length);
  const cx = (gi: number, si: number) => L + gi * gw + gw / 2 + (si - (series.length - 1) / 2) * bw * 1.14;
  const labels = bw * 1.14 >= 30; // narrower and neighbouring labels collide: the tooltip has the value
  return (
    <div ref={ref} {...h.chart}>
      <svg viewBox={`0 0 ${W} ${height}`} width="100%" className="block overflow-visible" role="img" aria-label={label + hint}>
        {bands?.map((b, k) => (
          <g key={b.label}>
            {k > 0 && <line x1={L + b.from * gw} x2={L + b.from * gw} y1={6} y2={B} stroke={C.border} strokeDasharray="3 3" />}
            <Txt x={L + b.from * gw + 6} y={13} size={10.5} weight={600} fill={C.text2}>{b.label}</Txt>
          </g>
        ))}
        <line x1={L} x2={W - R} y1={y(0)} y2={y(0)} stroke={C.borderStrong} />
        {cells.map(([gi, si], k) => {
          const v = values[gi][si]!;
          return (
            <g key={`${gi}-${si}`} {...h.item(k)} opacity={h.dim(h.active === k)}>
              <rect x={cx(gi, si) - bw / 2} y={Math.min(y(v), y(0))} width={bw} height={Math.max(1, Math.abs(y(v) - y(0)))} rx={3} fill={series[si][1]} />
              {labels && <Txt x={cx(gi, si)} y={v >= 0 ? y(v) - 5 : y(v) + 13} anchor="middle" fill={C.text2} size={10.5} weight={600}>{fmt(v)}</Txt>}
            </g>
          );
        })}
        {groups.map((g, gi) => <Txt key={g} x={L + gi * gw + gw / 2} y={B + 16} anchor="middle" fill={C.text}>{g}</Txt>)}
      </svg>
      {h.node}
    </div>
  );
}

/** Rows of paired horizontal bars, the name above its bars so long names fit any width; dashed lines mark `refs`. */
export function RowBars({ rows, series, refs, fmt, label }: {
  rows: { name: string; values: (number | null)[]; color?: string; faded?: boolean; tip: Tip }[];
  series: [string, string][];
  refs?: (number | null)[]; // one per series, e.g. the all-years average
  fmt: (v: number) => string;
  label: string;
}) {
  const [ref, W] = useWidth();
  const h = useHover(rows.map((r) => r.tip));
  const all = rows.flatMap((r) => r.values).filter(ok);
  const lo = Math.min(0, ...all), hi = Math.max(0, ...all);
  const L = lo < 0 ? 62 : 4, R = 62, bh = 10, RH = 18 + series.length * (bh + 3) + 8, H = rows.length * RH + 8;
  const x = (v: number) => L + ((v - lo) / (hi - lo || 1)) * (W - L - R);
  const barsH = series.length * (bh + 3);
  return (
    <div ref={ref} {...h.chart}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" className="block overflow-visible" role="img" aria-label={label + hint}>
        {rows.map((r, i) => {
          const top = 4 + i * RH;
          return (
            <g key={r.name} {...h.item(i)} opacity={h.dim(h.active === i) * (r.faded ? 0.6 : 1)}>
              <rect x={0} y={top} width={W} height={RH - 2} fill="transparent" />
              <Txt x={4} y={top + 12} fill={C.text} size={12} weight={h.active === i ? 700 : 500}>{r.name}</Txt>
              {refs?.map((v, si) => (ok(v) ? (
                <line key={si} x1={x(v)} x2={x(v)} y1={top + 15} y2={top + 21 + barsH} stroke={series[si][1]} strokeDasharray="3 2" opacity={0.8} />
              ) : null))}
              {lo < 0 && <line x1={x(0)} x2={x(0)} y1={top + 15} y2={top + 21 + barsH} stroke={C.borderStrong} />}
              {series.map(([, sc], si) => {
                const color = r.color ?? sc;
                const v = r.values[si];
                if (!ok(v)) return null;
                const by = top + 18 + si * (bh + 3);
                return (
                  <g key={si}>
                    <rect x={Math.min(x(v), x(0))} y={by} width={Math.max(1, Math.abs(x(v) - x(0)))} height={bh} rx={2} fill={color} />
                    <Txt x={v >= 0 ? x(v) + 5 : x(v) - 5} y={by + 9} anchor={v >= 0 ? "start" : "end"} fill={C.text2} size={10.5} weight={600}>{fmt(v)}</Txt>
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

/** Raw (hollow) to adjusted (filled) value per row, the line showing how far it moved; dashed = `at`. */
export function Dots({ rows, at, atLabel, fmt, color, label }: {
  rows: { name: string; from: number; to: number; tip: Tip }[];
  at: number; // the dashed reference, e.g. the overall average
  atLabel: string;
  fmt: (v: number) => string;
  color: string;
  label: string;
}) {
  const [box, W] = useWidth();
  const h = useHover(rows.map((r) => r.tip));
  const vs = rows.flatMap((r) => [r.from, r.to]);
  const lo = Math.min(...vs, at), hi = Math.max(...vs, at);
  const L = 8, R = 56, RH = 36, H = rows.length * RH + 24;
  const x = (v: number) => L + ((v - lo) / (hi - lo || 1)) * (W - L - R);
  return (
    <div ref={box} {...h.chart}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" className="block overflow-visible" role="img" aria-label={label + hint}>
        <line x1={x(at)} x2={x(at)} y1={0} y2={rows.length * RH} stroke={C.muted} strokeDasharray="4 3" />
        <Txt x={x(at)} y={rows.length * RH + 15} anchor="middle" size={10.5}>{atLabel}</Txt>
        {rows.map((r, i) => {
          const top = i * RH, cy = top + 25;
          return (
            <g key={r.name} {...h.item(i)} opacity={h.dim(h.active === i)}>
              <rect x={0} y={top} width={W} height={RH} fill="transparent" />
              <Txt x={L} y={top + 11} fill={C.text} size={11.5} weight={h.active === i ? 700 : 400}>{r.name}</Txt>
              <line x1={x(r.from)} x2={x(r.to)} y1={cy} y2={cy} stroke={C.muted2} strokeWidth={2} />
              <circle cx={x(r.from)} cy={cy} r={4.5} fill={C.surface} stroke={color} strokeWidth={1.5} />
              <circle cx={x(r.to)} cy={cy} r={5} fill={color} />
              <Txt x={Math.max(x(r.from), x(r.to)) + 9} y={cy + 4} fill={C.text2} size={10.5} weight={600}>{fmt(r.to)}</Txt>
            </g>
          );
        })}
      </svg>
      {h.node}
    </div>
  );
}

/** Coefficient plot: each test's effect with its 95% interval. Filled = significant at 5%, hollow = not. */
export function Coef({ rows, fmt, label }: {
  rows: { name: string; beta: number; se: number; p: number; n: number }[];
  fmt: (v: number) => string;
  label: string;
}) {
  const [ref, W] = useWidth();
  const h = useHover(rows.map((r) => ({
    title: r.name,
    lines: [`Effect ${fmt(r.beta)}`, `95% interval ${fmt(r.beta - 1.96 * r.se)} to ${fmt(r.beta + 1.96 * r.se)}`, `p ${pval(r.p)} · ${r.n} years`],
  })));
  const ext = Math.max(...rows.map((r) => Math.abs(r.beta) + 1.96 * Math.abs(r.se)));
  const L = 8, R = 92, RH = 34, H = rows.length * RH + 22;
  const x = (v: number) => L + ((v + ext) / (2 * ext)) * (W - L - R);
  return (
    <div ref={ref} {...h.chart}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" className="block overflow-visible" role="img" aria-label={label + hint}>
        <line x1={x(0)} x2={x(0)} y1={0} y2={rows.length * RH} stroke={C.muted} strokeDasharray="4 3" />
        <Txt x={x(0)} y={rows.length * RH + 14} anchor="middle" size={10.5}>0 = no effect</Txt>
        {rows.map((r, i) => {
          const top = i * RH, sig = r.p < 0.05, cy = top + 24;
          return (
            <g key={r.name} {...h.item(i)} opacity={h.dim(h.active === i)}>
              <rect x={0} y={top} width={W} height={RH} fill="transparent" />
              <Txt x={L} y={top + 11} fill={C.text} size={11.5} weight={h.active === i ? 700 : 400}>{r.name}</Txt>
              <line x1={x(r.beta - 1.96 * r.se)} x2={x(r.beta + 1.96 * r.se)} y1={cy} y2={cy} stroke={sig ? C.accent : C.muted} strokeWidth={2} />
              <circle cx={x(r.beta)} cy={cy} r={5} fill={sig ? C.accent : C.surface} stroke={sig ? C.accent : C.muted} strokeWidth={2} />
              <Txt x={W - R + 8} y={cy + 4} fill={C.text2} size={10.5} weight={sig ? 700 : 400}>{`${fmt(r.beta)} · p ${pval(r.p)}`}</Txt>
            </g>
          );
        })}
      </svg>
      {h.node}
    </div>
  );
}

/** One dot per point with a least-squares line through them. */
export function Scatter({ points, xFmt, yFmt, xTitle, yTitle, color, label }: {
  points: { x: number; y: number; name: string }[];
  xFmt: (v: number) => string;
  yFmt: (v: number) => string;
  xTitle: string;
  yTitle: string;
  color: string;
  label: string;
}) {
  const [ref, W] = useWidth();
  const h = useHover(points.map((p) => ({ title: p.name, lines: [`${xTitle}: ${xFmt(p.x)}`, `${yTitle}: ${yFmt(p.y)}`] })));
  const H = 260, L = 46, R = 10, T = 18, B = H - 36;
  const xs = nice(Math.min(...points.map((p) => p.x)), Math.max(...points.map((p) => p.x)));
  const ys = nice(Math.min(...points.map((p) => p.y)), Math.max(...points.map((p) => p.y)));
  const x = (v: number) => L + ((v - xs.lo) / (xs.hi - xs.lo)) * (W - L - R);
  const y = (v: number) => B - ((v - ys.lo) / (ys.hi - ys.lo)) * (B - T);
  const mx = points.reduce((s, p) => s + p.x, 0) / points.length, my = points.reduce((s, p) => s + p.y, 0) / points.length;
  const b = points.reduce((s, p) => s + (p.x - mx) * (p.y - my), 0) / points.reduce((s, p) => s + (p.x - mx) ** 2, 0);
  const fit = (v: number) => my + b * (v - mx);
  return (
    <div ref={ref} {...h.chart}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" className="block overflow-visible" role="img" aria-label={label + hint}>
        {ys.ticks.map((t) => (
          <g key={t}>
            <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke={C.grid} />
            <Txt x={L - 6} y={y(t) + 4} anchor="end">{yFmt(t)}</Txt>
          </g>
        ))}
        {xs.ticks.map((t) => <Txt key={t} x={x(t)} y={B + 15} anchor="middle">{xFmt(t)}</Txt>)}
        <Txt x={W - R} y={H - 4} anchor="end" size={10.5}>{`${xTitle} →`}</Txt>
        <Txt x={L} y={10} size={10.5}>{`↑ ${yTitle}`}</Txt>
        <line x1={x(xs.lo)} x2={x(xs.hi)} y1={y(fit(xs.lo))} y2={y(fit(xs.hi))} stroke={C.text2} strokeWidth={1.5} />
        {points.map((p, i) => (
          <circle key={p.name} {...h.item(i)} cx={x(p.x)} cy={y(p.y)} r={h.active === i ? 6 : 4} fill={color}
            fillOpacity={h.active == null || h.active === i ? 0.7 : 0.25} stroke={h.active === i ? C.text : "none"} />
        ))}
      </svg>
      {h.node}
    </div>
  );
}

export type Cell = string | number | { v: string; bold?: boolean };

/** A plain table; the first `left` columns are text, the rest right-aligned numbers. Bold cells are p < 0.05. */
export function Table({ head, rows, left = 1, caption, tall = false }: {
  head: string[]; rows: Cell[][]; left?: number; caption: string; tall?: boolean;
}) {
  return (
    // a scrolling region gets a Tab stop and a name, so keyboard users can scroll it too
    <div tabIndex={0} role="region" aria-label={caption}
      className={`overflow-auto rounded-md outline-none focus-visible:ring-2 focus-visible:ring-accent ${tall ? "max-h-[26rem]" : ""}`}>
      <table className="w-full text-[12.5px]">
        <caption className="sr-only">{caption}</caption>
        <thead className="sticky top-0 bg-surface">
          <tr className="text-[11px] uppercase tracking-[0.05em] text-muted">
            {head.map((h, i) => (
              <th key={h + i} scope="col" className={`font-semibold py-1.5 px-2 first:pl-0 whitespace-nowrap ${i < left ? "text-left" : "text-right"}`}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, ri) => (
            <tr key={ri} className="border-t border-border">
              {r.map((c, i) => {
                const v = typeof c === "object" ? c.v : String(c), bold = typeof c === "object" && c.bold;
                return (
                  <td key={i} className={`py-1.5 px-2 first:pl-0 ${i < left ? "text-left text-text" : "num text-right text-text-2"} ${bold ? "font-bold text-text" : ""}`}>{v}</td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** A p-value cell, bold when below 0.05. */
export const P = (p: number | null | undefined): Cell => ({ v: pval(p), bold: p != null && p < 0.05 });
