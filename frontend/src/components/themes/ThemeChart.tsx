import { useState, type ReactNode } from "react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, LabelList, Legend, Line, LineChart, ReferenceArea, ReferenceDot, ReferenceLine,
  ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from "recharts";
import type { ThemeExhibit } from "@/api/endpoints";
import { cn } from "@/lib/cn";
import { C } from "@/lib/theme";

// One Theme Charts exhibit drawn in the browser from the numbers agents/theme_charts.chart_data computed
// (the same ones its PNG was drawn from). The only maths here is display: rebasing a compare to 100 at the
// chosen range's start and the scatter's correlation for that range.

type Pt = [string, number];
type LineData = { series: { name: string; unit: string; points: Pt[] }[]; dated: boolean; window: number; rebase: boolean };
type MoversData = { bars: { label: string; value: number }[]; unit: string };
type HeatData = { rows: { name: string; rate: boolean; cells: [number, number][] }[] };
type ScatterData = { names: string[]; rates: boolean[]; window: number; points: [string, number, number][] };
type TogetherData = { names: string[]; window: number; points: Pt[] }; // weekly % of the last 13 weeks moving the same way
type RangeData = { rows: { name: string; lo: number; hi: number; last: number; ago: number; rate: boolean }[] };

const PALETTE = [C.accent, C.jobs, C.ai, C.inflation];
const RANGES = { "1M": 31, "3M": 92, "6M": 183, "1Y": 366 } as const;
type Range = keyof typeof RANGES;
const pickRange = (days: number, opts: Range[]): Range => opts.find((r) => days <= RANGES[r]) ?? opts[opts.length - 1];
const day = (d: string) => new Date(`${d}T12:00:00Z`);
const short = (d: string) => day(d).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
const long = (d: string) => day(d).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
const since = <T extends [string, ...unknown[]]>(rows: T[], r: Range) => {
  if (!rows.length) return rows;
  const cut = day(rows[rows.length - 1][0]).getTime() - RANGES[r] * 864e5;
  return rows.filter((p) => day(p[0]).getTime() >= cut);
};
const signed = (v: number, d = 1) => `${v >= 0 ? "+" : ""}${v.toFixed(d)}`;
const move = (v: number, rate: boolean) => (rate ? `${signed(v, 0)}bp` : `${signed(v)}%`);
const level = (v: number, rate: boolean) =>
  rate ? `${v.toFixed(2)}%` : v.toLocaleString("en-US", { maximumFractionDigits: Math.abs(v) < 10 ? 4 : 2 });
const tipStyle = { background: C.surface, border: `1px solid ${C.borderStrong}`, borderRadius: 8, fontSize: 12, color: C.text };

function RangeSwitch({ value, opts, onPick }: { value: Range; opts: Range[]; onPick: (r: Range) => void }) {
  return (
    <span className="inline-flex overflow-hidden rounded-lg border border-border-strong">
      {opts.map((r) => (
        <button key={r} type="button" onClick={() => onPick(r)}
          className={cn("px-2.5 py-1 text-[11.5px] font-semibold", r === value ? "bg-accent-soft text-accent" : "text-muted hover:text-text")}>
          {r}
        </button>
      ))}
    </span>
  );
}

// A small floating box for the HTML charts (heatmap, range); recharts brings its own tooltip.
function useTip() {
  const [tip, setTip] = useState<{ x: number; y: number; body: ReactNode } | null>(null);
  const on = (body: ReactNode) => ({
    onMouseMove: (e: React.MouseEvent) => setTip({ x: e.clientX, y: e.clientY, body }),
    onMouseLeave: () => setTip(null),
  });
  const box = tip && (
    <div className="pointer-events-none fixed z-50 rounded-lg border border-border-strong bg-surface px-2.5 py-1.5 text-[11.5px] leading-snug text-text shadow-card-hover"
      style={{ left: tip.x + 14, top: tip.y + 14 }}>{tip.body}</div>
  );
  return { on, box };
}

function LineView({ d, range }: { d: LineData; range: Range }) {
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const names = d.series.map((s) => s.name);
  const unit = d.series[0]?.unit ?? "";
  // one row per date that every series has, like the PNG's compare frame; undated (Polymarket, releases) as is
  const byDate = new Map<string, Record<string, number | string>>();
  d.series.forEach((s) => s.points.forEach(([x, v]) => byDate.set(x, { ...(byDate.get(x) ?? { x }), [s.name]: v })));
  let rows = [...byDate.values()].filter((r) => names.every((n) => typeof r[n] === "number"));
  if (d.dated) {
    rows.sort((a, b) => String(a.x).localeCompare(String(b.x)));
    rows = since(rows.map((r) => [r.x as string, r] as [string, typeof r]), range).map(([, r]) => r);
  }
  if (d.rebase && rows.length) {
    const base = rows[0];
    rows = rows.map((r) => ({ ...r, ...Object.fromEntries(names.map((n) => [n, ((r[n] as number) / (base[n] as number)) * 100])) }));
  }
  const fmtV = (v: number) => (d.rebase ? `${v.toFixed(1)} (${signed(v - 100)}%)` : unit === "%" ? `${v.toFixed(2)}%` : level(v, false));
  const xFmt = (x: string) => (d.dated ? short(x) : x);
  const common = {
    data: rows, margin: { top: 8, right: 12, left: 0, bottom: 0 },
  };
  const axes = (
    <>
      <CartesianGrid stroke={C.border} strokeOpacity={0.6} vertical={false} />
      <XAxis dataKey="x" tickFormatter={xFmt} minTickGap={36} tick={{ fontSize: 11, fill: C.muted }} tickLine={false} axisLine={{ stroke: C.border }} />
      <YAxis domain={["auto", "auto"]} width={48} tick={{ fontSize: 11, fill: C.muted }} tickLine={false} axisLine={false}
        tickFormatter={(v: number) => (unit === "%" && !d.rebase ? `${v}%` : `${v}`)} />
      <Tooltip contentStyle={tipStyle} labelFormatter={(x) => (d.dated ? long(String(x)) : String(x))}
        formatter={(v: number, n: string) => [fmtV(v), n]} />
      {d.rebase && <ReferenceLine y={100} stroke={C.muted2} strokeDasharray="3 3" />}
    </>
  );
  if (names.length === 1) {
    return (
      <ResponsiveContainer width="100%" height={340}>
        <AreaChart {...common}>
          {axes}
          <Area type="monotone" dataKey={names[0]} stroke={C.accent} strokeWidth={2} fill={C.accent} fillOpacity={0.12}
            dot={rows.length <= 12} isAnimationActive={false} />
        </AreaChart>
      </ResponsiveContainer>
    );
  }
  return (
    <ResponsiveContainer width="100%" height={340}>
      <LineChart {...common}>
        {axes}
        <Legend iconType="circle" iconSize={9} wrapperStyle={{ fontSize: 11.5, cursor: "pointer" }}
          onClick={(e) => { const n = String(e.dataKey); setHidden((h) => { const s = new Set(h); s.has(n) ? s.delete(n) : s.add(n); return s; }); }}
          formatter={(v: string) => <span style={{ color: hidden.has(v) ? C.muted2 : C.text2 }}>{v}</span>} />
        {names.map((n, i) => (
          <Line key={n} type="monotone" dataKey={n} stroke={PALETTE[i % 4]} strokeWidth={2} dot={false} hide={hidden.has(n)} isAnimationActive={false} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

function MoversView({ d }: { d: MoversData }) {
  const fmt = (v: number) => (d.unit === "bp" ? `${signed(v, 0)}bp` : `${signed(v)}${d.unit}`);
  return (
    <ResponsiveContainer width="100%" height={Math.max(160, d.bars.length * 34 + 20)}>
      <BarChart data={d.bars} layout="vertical" margin={{ top: 4, right: 52, left: 0, bottom: 4 }}>
        <XAxis type="number" hide domain={["auto", "auto"]} />
        <YAxis type="category" dataKey="label" width={130} tick={{ fontSize: 11.5, fill: C.text2 }} tickLine={false} axisLine={false} />
        <ReferenceLine x={0} stroke={C.border} />
        <Tooltip contentStyle={tipStyle} cursor={{ fill: C.soft }} formatter={(v: number) => [fmt(v), "move"]} />
        <Bar dataKey="value" radius={3} isAnimationActive={false}>
          {d.bars.map((b) => <Cell key={b.label} fill={b.value >= 0 ? C.accent : C.danger} />)}
          <LabelList dataKey="value" position="right" formatter={fmt} style={{ fontSize: 11, fill: C.muted }} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

const H = ["1D", "1W", "1M", "3M"];
const heatSub = (d: HeatData) => {
  let best = { name: "", v: 0, z: 0, j: 0, rate: false };
  d.rows.forEach((r) => r.cells.forEach(([v, z], j) => { if (Math.abs(z) > Math.abs(best.z)) best = { name: r.name.split(" · ")[0], v, z, j, rate: r.rate }; }));
  return `Most unusual: ${best.name} ${move(best.v, best.rate)} over ${H[best.j]} (${signed(best.z)}σ)`;
};

function HeatView({ d }: { d: HeatData }) {
  const { on, box } = useTip();
  const shade = (z: number) => `rgb(var(--c-${z >= 0 ? "accent" : "danger"}) / ${(Math.min(Math.abs(z), 3) / 3) * 0.85 + 0.08})`;
  return (
    <div className="mt-2 grid gap-1 text-xs" style={{ gridTemplateColumns: "minmax(110px,1.4fr) repeat(4, minmax(0,1fr))" }}>
      <span />
      {H.map((h) => <span key={h} className="text-center text-[11px] font-bold text-muted">{h}</span>)}
      {d.rows.map((r) => {
        const [name, when] = r.name.split(" · ");
        return [
          <span key={r.name} className="self-center text-text-2">{name}{when && <span className="text-[10.5px] text-muted-2"> · {when}</span>}</span>,
          ...r.cells.map(([v, z], j) => (
            <span key={`${r.name}-${j}`} {...on(<><b>{name}</b><br />{move(v, r.rate)} over {H[j]}<br />{signed(z)}σ vs its last 2 years</>)}
              className="rounded-md py-2 text-center font-bold hover:outline hover:outline-2 hover:outline-text"
              style={{ background: shade(z), color: Math.abs(z) > 1.8 ? "white" : C.text }}>
              {move(v, r.rate)}
            </span>
          )),
        ];
      })}
      {box}
    </div>
  );
}

function corr(pts: [string, number, number][]) {
  const dx = pts.slice(1).map((p, i) => p[1] - pts[i][1]), dy = pts.slice(1).map((p, i) => p[2] - pts[i][2]);
  const m = (a: number[]) => a.reduce((s, v) => s + v, 0) / a.length;
  const mx = m(dx), my = m(dy);
  const num = dx.reduce((s, v, i) => s + (v - mx) * (dy[i] - my), 0);
  const den = Math.sqrt(dx.reduce((s, v) => s + (v - mx) ** 2, 0) * dy.reduce((s, v) => s + (v - my) ** 2, 0));
  return den ? num / den : 0;
}

function ScatterView({ d, range }: { d: ScatterData; range: Range }) {
  const pts = since(d.points, range);
  const n = pts.length;
  const rows = pts.map(([date, x, y], i) => ({ date, x, y, i }));
  const axisName = (k: 0 | 1) => d.names[k] + (d.rates[k] ? " (%)" : "");
  return (
    <ResponsiveContainer width="100%" height={340}>
      <ScatterChart margin={{ top: 10, right: 16, left: 4, bottom: 18 }}>
        <CartesianGrid stroke={C.border} strokeOpacity={0.5} />
        <XAxis type="number" dataKey="x" domain={["auto", "auto"]} tick={{ fontSize: 11, fill: C.muted }} tickLine={false}
          label={{ value: axisName(0), position: "insideBottom", offset: -10, fontSize: 11, fill: C.muted }} />
        <YAxis type="number" dataKey="y" domain={["auto", "auto"]} width={52} tick={{ fontSize: 11, fill: C.muted }} tickLine={false}
          label={{ value: axisName(1), angle: -90, position: "insideLeft", fontSize: 11, fill: C.muted, dy: 50 }} />
        <ZAxis range={[40, 40]} />
        <Tooltip contentStyle={tipStyle} cursor={{ strokeDasharray: "3 3" }}
          content={({ active, payload }) => {
            const p = active && payload?.[0]?.payload;
            return p ? (
              <div style={{ ...tipStyle, padding: "6px 9px" }}>
                <b>{long(p.date)}</b><br />{d.names[0]} {level(p.x, d.rates[0])}<br />{d.names[1]} {level(p.y, d.rates[1])}
              </div>
            ) : null;
          }} />
        <Scatter data={rows} isAnimationActive={false} line={{ stroke: C.accent, strokeOpacity: 0.45, strokeWidth: 1.6 }}
          shape={(props: unknown) => {
            const { cx, cy, payload } = props as { cx: number; cy: number; payload: { i: number } };
            const last = payload.i === n - 1, first = payload.i === 0;
            return (
              <circle cx={cx} cy={cy} r={last ? 7 : first ? 5 : 3.5} stroke={first ? C.muted : C.surface} strokeWidth={first || last ? 1.5 : 0}
                fill={first ? C.surface : C.accent} fillOpacity={last || first ? 1 : 0.3 + (0.6 * payload.i) / n} />
            );
          }} />
      </ScatterChart>
    </ResponsiveContainer>
  );
}

// agents/theme_charts.together: the same bands and colours as the PNG
const ROLL = 13, TOGETHER = 60, APART = 40;
const zone = (v: number) => (v >= TOGETHER ? C.accent : v <= APART ? C.danger : C.muted);

function TogetherView({ d }: { d: TogetherData }) {
  const rows = d.points.map(([x, v]) => ({ x, v }));
  const last = rows[rows.length - 1];
  const vs = rows.map((r) => r.v), hi = Math.max(...vs), lo = Math.min(...vs);
  // the line's colour switches at the band edges: a vertical gradient over its own min..max with hard stops
  const at = (v: number) => (hi > lo ? Math.min(1, Math.max(0, (hi - v) / (hi - lo))) : 0);
  const key: [string, string][] = [
    [C.accent, `Move together (${Math.ceil((ROLL * TOGETHER) / 100)}+ of ${ROLL} weeks)`],
    [C.muted, "No steady link"],
    [C.danger, `Move opposite (${Math.floor((ROLL * APART) / 100)} or fewer)`],
  ];
  return (
    <>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11.5px] text-text-2">
        {key.map(([c, t]) => <span key={t} className="flex items-center gap-1.5"><i className="inline-block h-0.5 w-4" style={{ background: c }} />{t}</span>)}
      </div>
      <ResponsiveContainer width="100%" height={340}>
        <LineChart data={rows} margin={{ top: 8, right: 44, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="together-zone" x1="0" y1="0" x2="0" y2="1">
              <stop offset={at(TOGETHER)} stopColor={C.accent} /><stop offset={at(TOGETHER)} stopColor={C.muted} />
              <stop offset={at(APART)} stopColor={C.muted} /><stop offset={at(APART)} stopColor={C.danger} />
            </linearGradient>
          </defs>
          <ReferenceArea y1={TOGETHER} y2={100} fill={C.accent} fillOpacity={0.07} />
          <ReferenceArea y1={0} y2={APART} fill={C.danger} fillOpacity={0.06} />
          <CartesianGrid stroke={C.border} strokeOpacity={0.6} vertical={false} />
          <XAxis dataKey="x" tickFormatter={short} minTickGap={36} tick={{ fontSize: 11, fill: C.muted }} tickLine={false} axisLine={{ stroke: C.border }} />
          <YAxis domain={[0, 100]} ticks={[0, 20, 40, 60, 80, 100]} width={44} tick={{ fontSize: 11, fill: C.muted }} tickLine={false} axisLine={false}
            tickFormatter={(v: number) => `${v}%`} />
          <Tooltip contentStyle={tipStyle} labelFormatter={(x) => `Week of ${long(String(x))}`}
            formatter={(v: number) => [`${Math.round((v * ROLL) / 100)} of the last ${ROLL} weeks (${v.toFixed(0)}%)`, `${d.names.join(" & ")} moved the same way`]} />
          <Line type="monotone" dataKey="v" stroke="url(#together-zone)" strokeWidth={2.2} dot={false} isAnimationActive={false} />
          {last && <ReferenceDot x={last.x} y={last.v} r={6} fill={zone(last.v)} stroke={C.surface} strokeWidth={1.5}
            label={{ value: `${last.v.toFixed(0)}%`, position: "right", fontSize: 11, fontWeight: 700, fill: zone(last.v) }} />}
        </LineChart>
      </ResponsiveContainer>
    </>
  );
}

const pos = (v: number, lo: number, hi: number) => (hi > lo ? ((v - lo) / (hi - lo)) * 100 : 50);
const rangeSub = (d: RangeData) => {
  const top = d.rows.reduce((a, b) => (Math.abs(pos(b.last, b.lo, b.hi) - 50) > Math.abs(pos(a.last, a.lo, a.hi) - 50) ? b : a));
  return `${top.name.split(" · ")[0]}: ${pos(top.last, top.lo, top.hi).toFixed(0)}% of its 1-year range · ring = a month ago`;
};

function RangeView({ d }: { d: RangeData }) {
  const { on, box } = useTip();
  return (
    <div className="mt-3 space-y-3.5">
      {d.rows.map((r) => {
        const p = pos(r.last, r.lo, r.hi), pa = pos(r.ago, r.lo, r.hi);
        const up = r.last >= r.ago ? C.success : C.danger;
        return (
          <div key={r.name} className="grid grid-cols-[120px_minmax(0,1fr)] items-center gap-3 text-xs md:grid-cols-[150px_minmax(0,1fr)]">
            <span className="text-text-2">{r.name}</span>
            <div>
              <div className="relative mb-2 mt-4 h-2.5 rounded-full bg-surface-3"
                {...on(<><b>{r.name}</b><br />now {level(r.last, r.rate)} · {p.toFixed(0)}% of its 1-year range<br />a month ago {level(r.ago, r.rate)}<br />1-year low {level(r.lo, r.rate)} · high {level(r.hi, r.rate)}</>)}>
                <span className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-muted bg-surface" style={{ left: `${pa}%` }} />
                <span className="absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-surface" style={{ left: `${p}%`, background: up }} />
                <span className="absolute -top-[18px] -translate-x-1/2 whitespace-nowrap text-[11px] font-bold" style={{ left: `${p}%`, color: up }}>{level(r.last, r.rate)}</span>
              </div>
              <div className="flex justify-between text-[10.5px] text-muted-2"><span>{level(r.lo, r.rate)}</span><span>{level(r.hi, r.rate)}</span></div>
            </div>
          </div>
        );
      })}
      {box}
    </div>
  );
}

export function ThemeChartCard({ ex, png }: { ex: ThemeExhibit; png: string }) {
  const d = ex.data!;
  const timeOpts: Range[] | null =
    ex.kind === "scatter" ? ["3M", "6M", "1Y"] : (ex.kind === "line" || ex.kind === "compare") && (d as LineData).dated ? ["1M", "3M", "6M", "1Y"] : null;
  const [range, setRange] = useState<Range>(() => (timeOpts ? pickRange((d as { window: number }).window, timeOpts) : "1Y"));
  const title = ex.title.replace(/^Exhibit \d+:\s*/, "");
  const sub =
    ex.kind === "heatmap" ? heatSub(d as HeatData)
    : ex.kind === "range" ? rangeSub(d as RangeData)
    : ex.kind === "scatter" ? `Weekly closes, last ${range} · weekly moves correlate ${signed(corr(since((d as ScatterData).points, range)), 2)}`
    : ex.kind === "compare" && (d as LineData).rebase ? "Rebased to 100 at the start of the range · click a name to hide it"
    : ex.subtitle;
  return (
    <section className="flex min-w-0 flex-col rounded-[10px] border border-border bg-surface px-4 pb-3 pt-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[10.5px] font-bold uppercase tracking-[0.08em] text-accent">ARC Research · Theme Charts · Exhibit {ex.n}</div>
          <h3 className="mt-0.5 text-[15.5px] font-semibold leading-snug text-text">{title}</h3>
          <div className="text-xs text-muted">{sub}</div>
          {timeOpts && <div className="mt-2"><RangeSwitch value={range} opts={timeOpts} onPick={setRange} /></div>}
        </div>
        <img src="/arc-logo.png" alt="ARC Research" className="logo-img splash-logo -mr-1 -mt-1 h-10 w-auto shrink-0" />
      </div>
      <div className="mt-2 flex-1">
        {ex.kind === "line" || ex.kind === "compare" ? <LineView d={d as LineData} range={range} />
          : ex.kind === "movers" ? <MoversView d={d as MoversData} />
          : ex.kind === "heatmap" ? <HeatView d={d as HeatData} />
          : ex.kind === "scatter" ? <ScatterView d={d as ScatterData} range={range} /> // runs before 2026-10-17
          : ex.kind === "together" ? <TogetherView d={d as TogetherData} />
          : <RangeView d={d as RangeData} />}
      </div>
      <div className="mt-2 flex justify-between gap-3 border-t border-border pt-2 text-[11px] text-muted">
        <span>{ex.kind === "heatmap" ? "Shade = size of the move in standard deviations vs the last 2 years · " : ex.kind === "range" ? "Dot = now · ring = a month ago · " : ""}
          {d.sources?.length ? `Data: ${d.sources.join(", ")}` : ""}</span>
        <a href={png} download className="shrink-0 font-semibold text-accent hover:text-accent-hover">PNG ↓</a>
      </div>
    </section>
  );
}
