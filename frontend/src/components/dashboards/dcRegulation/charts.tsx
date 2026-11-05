import { C } from "@/lib/theme";
import { useHover, type Tip } from "../aiCapex/hover";
import { Txt, useWidth } from "../partisanGap/charts";

// Charts for the AI Data Centers & the 2026 Vote dashboard, in the Partisan Policy Gap style: SVG drawn at the
// container's width, role="img" with an aria-label, hover or arrow keys (once focused) for each item's detail.
// Text never sits on a solid color: tiles are a tint of their color (at most 45%, or a ramp capped where text
// keeps 4.5:1 in both themes) with a solid edge, so the label stays C.text.

const hint = " Hover an item, or focus the chart and use the arrow keys, for its detail.";

/** Tile-grid map: [column, row] per state (geometry, from the study's dashboard). */
export const GRID: Record<string, [number, number]> = {
  AK: [0, 0], ME: [11, 0], VT: [10, 1], NH: [11, 1], WA: [1, 2], ID: [2, 2], MT: [3, 2], ND: [4, 2], MN: [5, 2], IL: [6, 2],
  WI: [7, 2], MI: [8, 2], NY: [9, 2], RI: [10, 2], MA: [11, 2], OR: [1, 3], NV: [2, 3], WY: [3, 3], SD: [4, 3], IA: [5, 3],
  IN: [6, 3], OH: [7, 3], PA: [8, 3], NJ: [9, 3], CT: [10, 3], CA: [1, 4], UT: [2, 4], CO: [3, 4], NE: [4, 4], MO: [5, 4],
  KY: [6, 4], WV: [7, 4], VA: [8, 4], MD: [9, 4], DE: [10, 4], AZ: [2, 5], NM: [3, 5], KS: [4, 5], AR: [5, 5], TN: [6, 5],
  NC: [7, 5], SC: [8, 5], DC: [9, 5], OK: [4, 6], LA: [5, 6], MS: [6, 6], AL: [7, 6], GA: [8, 6], HI: [0, 7], TX: [4, 7],
  FL: [9, 7],
};

export interface TileCell {
  fill: string; // the tile's color, drawn as a tint
  tint: number; // 0..1 opacity of the fill over the card
  edge?: string; // a solid outline in the category color
  dashed?: boolean; // not yet called
  sub?: string; // a second line under the state code
  dot?: boolean; // new to the office
  stripe?: string; // a bar along the bottom (the officeholder's stance on the money map)
  tip: Tip;
}

/** One square per state; states without a cell are grey with no detail. `onPick` makes tiles clickable (and Enter). */
export function TileMap({ cells, selected, onPick, label }: {
  cells: Record<string, TileCell>; selected?: string | null; onPick?: (st: string) => void; label: string;
}) {
  const [ref, W] = useWidth();
  const order = Object.keys(GRID).filter((st) => cells[st]);
  const h = useHover(order.map((st) => cells[st].tip));
  const cell = Math.min(Math.floor(W / 12), 58), gap = Math.max(2, Math.round(cell * 0.07)), s = cell - gap;
  const fs = Math.max(9, Math.round(cell * 0.24)), two = cell >= 40;
  return (
    <div ref={ref} {...h.chart} onKeyDown={(e) => {
      if (onPick && e.key === "Enter" && h.active != null) onPick(order[h.active]);
      h.chart.onKeyDown(e);
    }}>
      <svg viewBox={`0 0 ${cell * 12} ${cell * 8}`} width="100%" className="block" role="img" aria-label={label + hint + (onPick ? " Press Enter to open a state." : "")}>
        {Object.entries(GRID).map(([st, [c, r]]) => {
          const x = c * cell + gap / 2, y = r * cell + gap / 2, t = cells[st], k = order.indexOf(st);
          if (!t) {
            return (
              <g key={st}>
                <rect x={x} y={y} width={s} height={s} rx={4} fill={C.grid} />
                <text x={x + s / 2} y={y + s / 2} dy="0.35em" textAnchor="middle" fontSize={fs} fill={C.muted}>{st}</text>
              </g>
            );
          }
          const on = h.active === k || selected === st;
          const sub = t.sub && two;
          return (
            <g key={st} {...h.item(k)} opacity={h.dim(h.active === k)} onClick={onPick ? () => onPick(st) : undefined}
              style={{ cursor: onPick ? "pointer" : "default" }}>
              <rect x={x} y={y} width={s} height={s} rx={4} fill={C.surface} />
              <rect x={x} y={y} width={s} height={s} rx={4} fill={t.fill} fillOpacity={t.tint}
                stroke={on ? C.text : t.edge ?? "none"} strokeWidth={on ? 2.5 : 1.5} strokeDasharray={t.dashed && !on ? "3 3" : undefined} />
              {t.stripe && <rect x={x + 4} y={y + s - 7} width={s - 8} height={3.5} rx={1.5} fill={t.stripe} />}
              <text x={x + s / 2} y={y + s / 2 - (sub ? 4 : 0)} dy="0.35em" textAnchor="middle" fontSize={fs} fontWeight={600} fill={C.text}>{st}</text>
              {sub && <text x={x + s / 2} y={y + s / 2 + Math.round(cell * 0.2)} dy="0.2em" textAnchor="middle" fontSize={Math.max(8, Math.round(cell * 0.17))} fill={C.text2}>{t.sub}</text>}
              {t.dot && <circle cx={x + s - 7} cy={y + 7} r={2.6} fill={C.text} />}
            </g>
          );
        })}
      </svg>
      {h.node}
    </div>
  );
}

/** Counts by stance, Democrats to the left of the centre line and Republicans to the right. */
export function PartyBars({ rows, label }: { rows: { name: string; color: string; D: number; R: number }[]; label: string }) {
  const [ref, W] = useWidth();
  const h = useHover(rows.map((r) => ({ title: r.name, lines: [`Democrats: ${r.D}`, `Republicans: ${r.R}`] })));
  const RH = 32, T = 20, H = T + rows.length * RH + 2;
  const labelW = Math.min(150, Math.round(W * 0.4)), mid = labelW + (W - labelW) / 2, half = (W - labelW) / 2 - 24;
  const max = Math.max(1, ...rows.flatMap((r) => [r.D, r.R]));
  const x = (v: number) => (v / max) * half;
  return (
    <div ref={ref} {...h.chart}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" className="block" role="img" aria-label={label + hint}>
        <Txt x={mid - 6} y={12} anchor="end">← Democrats</Txt>
        <Txt x={mid + 6} y={12}>Republicans →</Txt>
        <line x1={mid} x2={mid} y1={T - 4} y2={H} stroke={C.borderStrong} />
        {rows.map((r, i) => {
          const y = T + i * RH + 5, bh = RH - 12;
          return (
            <g key={r.name} {...h.item(i)} opacity={h.dim(h.active === i)}>
              <rect x={0} y={y - 5} width={W} height={RH} fill="transparent" />
              <Txt x={0} y={y + bh / 2 + 4} fill={C.text} size={11.5} weight={h.active === i ? 700 : 500}>{r.name}</Txt>
              <rect x={mid - x(r.D)} y={y} width={x(r.D)} height={bh} rx={3} fill={r.color} />
              <rect x={mid} y={y} width={x(r.R)} height={bh} rx={3} fill={r.color} />
              <Txt x={mid - x(r.D) - 5} y={y + bh / 2 + 4} anchor="end" fill={C.text2} weight={600}>{r.D}</Txt>
              <Txt x={mid + x(r.R) + 5} y={y + bh / 2 + 4} fill={C.text2} weight={600}>{r.R}</Txt>
            </g>
          );
        })}
      </svg>
      {h.node}
    </div>
  );
}

export interface Seg { name: string; value: number; color: string; dashed?: boolean }

/** One stacked horizontal bar per row: name on the left (or `above` the bar, for long names), segments from 0,
 * `end` text after the bar. `max` fixes the scale (e.g. 100 for shares); `ticks` draws a light axis. */
export function StackRows({ rows, labelW, above = false, max, ticks, rowH = 30, onPick, selected, label }: {
  rows: { name: string; segs: Seg[]; end?: string; tip: Tip; key?: string }[];
  labelW: number; above?: boolean; max?: number; ticks?: number[]; rowH?: number;
  onPick?: (key: string) => void; selected?: string | null; label: string;
}) {
  const [ref, W] = useWidth();
  const h = useHover(rows.map((r) => r.tip));
  const top = Math.max(1, max ?? Math.max(...rows.map((r) => r.segs.reduce((s, g) => s + g.value, 0))));
  const RH = above ? rowH + 8 : rowH, NAME = above ? 16 : 0; // `above`: the name gets its own line
  const endW = max != null ? 44 : 96, B = rows.length * RH, H = B + (ticks ? 18 : 2);
  const x = (v: number) => (above ? 0 : labelW) + (v / top) * (W - (above ? 0 : labelW) - endW);
  const bh = Math.max(8, rowH - 12);
  return (
    <div ref={ref} {...h.chart} onKeyDown={(e) => {
      if (onPick && e.key === "Enter" && h.active != null) onPick(rows[h.active].key ?? rows[h.active].name);
      h.chart.onKeyDown(e);
    }}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" className="block" role="img" aria-label={label + hint + (onPick ? " Press Enter to open a state." : "")}>
        {ticks?.map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={0} y2={B} stroke={C.grid} />
            <Txt x={x(t)} y={H - 4} anchor={x(t) < 8 ? "start" : "middle"}>{t}</Txt>
          </g>
        ))}
        {rows.map((r, i) => {
          const y = i * RH + NAME + (rowH - NAME - bh) / 2 + (above ? 4 : 0), key = r.key ?? r.name, on = h.active === i || selected === key;
          let cx = 0;
          return (
            <g key={key} {...h.item(i)} opacity={h.dim(h.active === i)} onClick={onPick ? () => onPick(key) : undefined}
              style={{ cursor: onPick ? "pointer" : "default" }}>
              <rect x={0} y={i * RH} width={W} height={RH} fill="transparent" />
              <Txt x={0} y={above ? i * RH + 12 : y + bh / 2 + 4} fill={C.text} size={rowH < 24 ? 11 : 12} weight={on ? 700 : 500}>{r.name}</Txt>
              {r.segs.map((g) => {
                const x0 = x(cx), w = x(cx + g.value) - x0;
                cx += g.value;
                if (w <= 0) return null;
                return (
                  <rect key={g.name} x={x0} y={y} width={Math.max(0.5, w - 1)} height={bh} rx={2}
                    fill={g.dashed ? C.surface : g.color} stroke={g.dashed ? C.muted : undefined} strokeDasharray={g.dashed ? "3 2" : undefined} />
                );
              })}
              {r.end && <Txt x={x(cx) + 6} y={y + bh / 2 + 4} fill={C.text2} weight={600}>{r.end}</Txt>}
            </g>
          );
        })}
      </svg>
      {h.node}
    </div>
  );
}

const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** "2026-08" -> months since year 0, and back to "Aug 2026". */
export const month = (ym: string) => Number(ym.slice(0, 4)) * 12 + Number(ym.slice(5, 7)) - 1;
const monthLabel = (m: number) => `${MON[m % 12]} ${Math.floor(m / 12)}`;

/** Shares over time, one line per series on a 0–100% scale, each point hoverable, end labels on the right. */
export function TrendLines({ series, label }: {
  series: { name: string; color: string; pts: { m: number; v: number; note: string }[] }[]; label: string;
}) {
  const [ref, W] = useWidth();
  const flat = series.flatMap((s) => s.pts.map((p) => ({ s, p })));
  const h = useHover(flat.map(({ s, p }) => ({ title: `${s.name} · ${monthLabel(p.m)}`, lines: [`Oppose: ${p.v}%`, p.note] })));
  const H = 230, L = 36, R = 132, T = 10, B = H - 24;
  const ms = flat.map(({ p }) => p.m), m0 = Math.min(...ms), m1 = Math.max(...ms);
  const x = (m: number) => L + ((m - m0) / (m1 - m0 || 1)) * (W - L - R);
  const y = (v: number) => B - (v / 100) * (B - T);
  const ends = series.map((s) => ({ s, y: y(s.pts[s.pts.length - 1].v) })).sort((a, b) => a.y - b.y);
  for (let k = 1; k < ends.length; k++) if (ends[k].y - ends[k - 1].y < 14) ends[k].y = ends[k - 1].y + 14;
  const step = W < 480 ? 6 : 3; // months between x labels
  const xt: number[] = [];
  for (let m = m0; m <= m1; m += step) xt.push(m);
  return (
    <div ref={ref} {...h.chart}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" className="block overflow-visible" role="img" aria-label={label + hint}>
        {[0, 25, 50, 75, 100].map((t) => (
          <g key={t}>
            <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke={C.grid} />
            <Txt x={L - 6} y={y(t) + 4} anchor="end">{`${t}%`}</Txt>
          </g>
        ))}
        {xt.map((m) => <Txt key={m} x={x(m)} y={B + 16} anchor="middle">{monthLabel(m)}</Txt>)}
        {series.map((s) => (
          <path key={s.name} d={s.pts.map((p, i) => `${i ? "L" : "M"}${x(p.m)},${y(p.v)}`).join("")} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" />
        ))}
        {flat.map(({ s, p }, k) => (
          <circle key={k} {...h.item(k)} cx={x(p.m)} cy={y(p.v)} r={h.active === k ? 6 : 4} fill={s.color} stroke={C.surface} strokeWidth={1.5} />
        ))}
        {ends.map(({ s, y: ey }) => (
          <Txt key={s.name} x={W - R + 8} y={ey + 4} fill={C.text} weight={600}>{`${s.name} ${s.pts[s.pts.length - 1].v}%`}</Txt>
        ))}
      </svg>
      {h.node}
    </div>
  );
}

/** Each state's index score across against its announced dollars up; dashed = the national median. */
export function IndexScatter({ points, median, onPick, label }: {
  points: { st: string; x: number; y: number; tip: Tip }[]; median: number; onPick?: (st: string) => void; label: string;
}) {
  const [ref, W] = useWidth();
  const h = useHover(points.map((p) => p.tip));
  const H = 300, L = 48, R = 14, T = 14, B = H - 36;
  const yMax = Math.max(1, ...points.map((p) => p.y));
  const stepY = yMax > 80 ? 25 : yMax > 40 ? 10 : 5, top = Math.ceil(yMax / stepY) * stepY;
  const x = (v: number) => L + (v / 100) * (W - L - R);
  const y = (v: number) => B - (v / top) * (B - T);
  const labels = points.filter((p) => p.y >= yMax * 0.18).map((p) => ({ ...p, ly: y(p.y) })).sort((a, b) => a.ly - b.ly);
  for (let k = 1; k < labels.length; k++) {
    if (labels[k].ly - labels[k - 1].ly < 12 && Math.abs(x(labels[k].x) - x(labels[k - 1].x)) < 30) labels[k].ly = labels[k - 1].ly + 12;
  }
  return (
    <div ref={ref} {...h.chart} onKeyDown={(e) => {
      if (onPick && e.key === "Enter" && h.active != null) onPick(points[h.active].st);
      h.chart.onKeyDown(e);
    }}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" className="block overflow-visible" role="img" aria-label={label + hint + (onPick ? " Press Enter to open a state." : "")}>
        {Array.from({ length: top / stepY + 1 }, (_, i) => i * stepY).map((t) => (
          <g key={t}>
            <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke={C.grid} />
            <Txt x={L - 6} y={y(t) + 4} anchor="end">{`$${t}B`}</Txt>
          </g>
        ))}
        {[0, 25, 50, 75, 100].map((t) => <Txt key={t} x={x(t)} y={B + 16} anchor={t === 0 ? "start" : t === 100 ? "end" : "middle"}>{t}</Txt>)}
        <Txt x={(L + W - R) / 2} y={H - 4} anchor="middle" size={10.5}>Index score (higher = more restrictive) →</Txt>
        <line x1={x(median)} x2={x(median)} y1={T} y2={B} stroke={C.muted} strokeDasharray="4 3" />
        <Txt x={x(median) + 5} y={T + 8} size={10.5}>{`median ${median.toFixed(1)}`}</Txt>
        {points.map((p, i) => {
          const money = p.y > 0, on = h.active === i;
          return (
            <circle key={p.st} {...h.item(i)} cx={x(p.x)} cy={y(p.y)} r={on ? 7 : money ? 5 : 3.5} fill={money ? C.jobs : C.muted}
              fillOpacity={h.active == null || on ? 0.8 : 0.25} stroke={on ? C.text : C.surface}
              onClick={onPick ? () => onPick(p.st) : undefined} style={{ cursor: onPick ? "pointer" : "default" }} />
          );
        })}
        {labels.map((p) => <Txt key={p.st} x={x(p.x) + 8} y={p.ly + 4} fill={C.text}>{p.st}</Txt>)}
      </svg>
      {h.node}
    </div>
  );
}
