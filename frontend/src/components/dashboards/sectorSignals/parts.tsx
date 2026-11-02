import { useMemo, useState } from "react";
import { Area, Bar, BarChart, CartesianGrid, Cell, ComposedChart, LabelList, Line, ReferenceDot, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { cn } from "@/lib/cn";
import { C } from "@/lib/theme";
import { useHover, type Tip } from "@/components/dashboards/aiCapex/hover";
import type { CatalogSignal, SectorSignals, SignalTest, Verdict } from "@/api/sectorSignals";

// Sector Signal Significance (dashboards/sector_signals/). Every number on the page is computed in Python;
// this file only draws it. Green = the sector rose more than usual after the signal, red = less.

export type Sel = { etf: string; signal: string };

export const pct = (v: number | null | undefined, d = 1, sign = true) =>
  v == null ? "—" : `${sign && v > 0 ? "+" : ""}${(v * 100).toFixed(d)}%`;
const pval = (p: number | null | undefined) => (p == null ? "—" : p < 0.001 ? "<0.001" : p.toFixed(3));
export const day = (d: string) => new Date(`${d}T12:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
const short = (d: string) => new Date(`${d}T12:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });

export const VERDICT: Record<Verdict, { label: string; glyph: string; cls: string; blurb: string }> = {
  signal: { label: "Signal", glyph: "●", cls: "bg-accent-soft text-accent border-accent/50", blurb: "survives the false-discovery check" },
  weak: { label: "Weak", glyph: "◐", cls: "bg-warning-soft text-warning border-warning/40", blurb: "p < 0.10 alone; could be luck across this many tests" },
  noise: { label: "Noise", glyph: "○", cls: "bg-surface-3 text-muted border-border-strong", blurb: "no different from random dates" },
  few: { label: "Too few", glyph: "·", cls: "bg-surface-2 text-muted-2 border-border", blurb: "fewer past events than the minimum" },
};

export function VerdictPill({ v, className }: { v: Verdict; className?: string }) {
  const s = VERDICT[v];
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide whitespace-nowrap", s.cls, className)}>
      <span aria-hidden>{s.glyph}</span>{s.label}
    </span>
  );
}

const edgeColor = (e: number | null | undefined) => (e == null ? C.muted2 : e >= 0 ? C.success : C.danger);
export const signedText = (e: number | null | undefined) => (e == null || e === 0 ? "text-text" : e > 0 ? "text-success" : "text-danger");

export function useIndex(d: SectorSignals) {
  return useMemo(() => {
    const tests = new Map<string, SignalTest>();
    for (const t of d.tests) tests.set(`${t.etf}|${t.signal}|${t.h}`, t);
    const sig = new Map<string, CatalogSignal>(d.catalog.map((c) => [c.id, c]));
    return { test: (etf: string, s: string, h: number) => tests.get(`${etf}|${s}|${h}`), sig };
  }, [d]);
}

// ── 01 · today's signals ─────────────────────────────────────────────────────

const when = (n: number) => (n === 0 ? "today's close" : n === 1 ? "1 session ago" : `${n} sessions ago`);

export function LiveList({ d, sel, onPick }: { d: SectorSignals; sel: Sel | null; onPick: (s: Sel) => void }) {
  const ix = useIndex(d);
  const [all, setAll] = useState(false);
  if (!d.live.length) return <p className="text-sm text-muted">No signal fired on any sector in the last {d.params.live_lookback_days} sessions.</p>;
  const worth = d.live.filter((e) => e.verdict === "signal" || e.verdict === "weak");
  const shown = all || worth.length === 0 ? d.live : worth;
  const hidden = d.live.length - shown.length;
  return (
    <div>
    <ul className="divide-y divide-border border-y border-border">
      {shown.map((e) => {
        const t = ix.test(e.etf, e.signal, e.best_h);
        const s = ix.sig.get(e.signal);
        const on = sel?.etf === e.etf && sel.signal === e.signal;
        return (
          <li key={`${e.etf}${e.signal}${e.date}`}>
            <button type="button" onClick={() => onPick({ etf: e.etf, signal: e.signal })} aria-pressed={on}
              className={cn("w-full text-left grid gap-x-4 gap-y-1 py-2.5 px-2 md:grid-cols-[96px_minmax(0,1.1fr)_minmax(0,1.6fr)] items-center hover:bg-surface-2 rounded-md",
                on && "bg-accent-soft/60")}>
              <VerdictPill v={e.verdict} className="justify-self-start" />
              <div className="min-w-0">
                <div className="text-sm font-semibold text-text truncate">{e.sector} <span className="font-mono text-xs text-muted">{e.etf}</span></div>
                <div className="text-xs text-text-2">{s?.label ?? e.signal} · {when(e.sessions_ago)}</div>
              </div>
              {t && t.mean != null ? (
                <div className="text-xs text-text-2 leading-[18px]">
                  After the last <b className="text-text">{t.n}</b> times, {e.sector} moved{" "}
                  <b className={signedText(t.mean)}>{pct(t.mean)}</b> over {t.h} days on average, vs{" "}
                  <b className="text-text">{pct(t.null_mean)}</b> usually ({pct(t.edge)} edge, up {pct(t.hit, 0, false)} of the time).
                  {t.textbook === false && <span className="text-muted"> Opposite of the textbook reading.</span>}
                </div>
              ) : (
                <div className="text-xs text-muted">Too little history to judge.</div>
              )}
            </button>
          </li>
        );
      })}
    </ul>
    {(hidden > 0 || all) && worth.length > 0 && (
      <button type="button" onClick={() => setAll(!all)} className="mt-2 text-xs font-semibold text-accent hover:underline">
        {all ? "Show only signal and weak" : `Show ${hidden} more that look like noise or have too few events`}
      </button>
    )}
    </div>
  );
}

// ── 02 · the map ─────────────────────────────────────────────────────────────

// only cells with evidence get color: noise stays neutral so it can't read as a faint signal
const ALPHA: Record<Verdict, number> = { signal: 1, weak: 0.45, noise: 0, few: 0 };

export function Heatmap({ d, h, sel, onPick }: { d: SectorSignals; h: number; sel: Sel | null; onPick: (s: Sel) => void }) {
  const ix = useIndex(d);
  const cells = d.sectors.flatMap((s) => d.catalog.map((c) => ({ s, c, t: ix.test(s.etf, c.id, h) })));
  const tips: Tip[] = cells.map(({ s, c, t }) => ({
    title: `${s.sector} · ${c.label}`,
    lines: t
      ? [`${VERDICT[t.verdict].label}: ${t.n} past events`, `${h}d after: ${pct(t.mean)} vs ${pct(t.null_mean)} usual`, `edge ${pct(t.edge)} · p ${pval(t.p)} · q ${pval(t.q)}`]
      : ["no data"],
  }));
  const hv = useHover(tips);
  const families = d.catalog.reduce<{ name: string; n: number }[]>((a, c) => {
    if (a.length && a[a.length - 1].name === c.family) a[a.length - 1].n++;
    else a.push({ name: c.family, n: 1 });
    return a;
  }, []);
  const cols = `minmax(118px,150px) repeat(${d.catalog.length}, minmax(30px,1fr))`;
  return (
    <div>
      <div className="overflow-x-auto -mx-1 px-1 pb-1">
        <div {...hv.chart} className={cn(hv.chart.className, "min-w-[640px]")} role="grid" aria-label={`Signal significance by sector, ${h}-day horizon`}>
          <div className="grid gap-[2px] text-[10.5px] text-muted mb-1" style={{ gridTemplateColumns: cols }}>
            <span />
            {families.map((f) => (
              <span key={f.name} className="border-b border-border-strong pb-0.5 truncate font-semibold" style={{ gridColumn: `span ${f.n}` }}>{f.name}</span>
            ))}
          </div>
          <div className="grid gap-[2px] mb-1" style={{ gridTemplateColumns: cols }}>
            <span />
            {d.catalog.map((c) => (
              <span key={c.id} className="h-[118px] flex items-end justify-center overflow-hidden" title={c.description}>
                <span className="text-[10.5px] leading-none text-text-2 whitespace-nowrap [writing-mode:vertical-rl] rotate-180">{c.label}</span>
              </span>
            ))}
          </div>
          {d.sectors.map((s, r) => (
            <div key={s.etf} className="grid gap-[2px] mb-[2px]" style={{ gridTemplateColumns: cols }} role="row">
              <span className="text-xs text-text truncate pr-2 self-center" title={s.sector}>{s.sector} <span className="font-mono text-[10px] text-muted">{s.etf}</span></span>
              {d.catalog.map((c, k) => {
                const i = r * d.catalog.length + k;
                const t = cells[i].t;
                const on = sel?.etf === s.etf && sel.signal === c.id;
                const v = t?.verdict ?? "few";
                return (
                  <button key={c.id} type="button" role="gridcell" {...hv.item(i)} onClick={() => onPick({ etf: s.etf, signal: c.id })}
                    aria-label={tips[i].title} aria-pressed={on}
                    className={cn("relative h-7 rounded-[4px] border flex items-center justify-center text-[11px] leading-none",
                      v === "few" ? "border-dashed border-border-strong" : v === "noise" ? "border-transparent bg-surface-2" : "border-transparent",
                      on && "ring-2 ring-text ring-offset-1 ring-offset-surface")}
                    style={{ opacity: hv.dim(hv.active === i) }}>
                    {ALPHA[v] > 0 && (
                      <span aria-hidden className="absolute inset-0 rounded-[3px]" style={{ background: edgeColor(t?.edge), opacity: ALPHA[v] }} />
                    )}
                    <span aria-hidden className={cn("relative", v === "signal" ? "text-white text-[13px]" : v === "weak" ? "text-text text-[13px]" : "text-muted-2")}>
                      {VERDICT[v].glyph}
                    </span>
                  </button>
                );
              })}
            </div>
          ))}
        </div>
        {hv.node}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-2 mt-2.5">
        <span className="flex items-center gap-1.5"><i className="inline-block w-3 h-3 rounded-[3px]" style={{ background: C.success }} />Rose more than usual after</span>
        <span className="flex items-center gap-1.5"><i className="inline-block w-3 h-3 rounded-[3px]" style={{ background: C.danger }} />Rose less / fell</span>
        <span className="text-muted">Faded = weak · neutral = noise</span>
        {(["signal", "weak", "noise", "few"] as Verdict[]).map((v) => (
          <span key={v} className="flex items-center gap-1"><span aria-hidden>{VERDICT[v].glyph}</span>{VERDICT[v].label}</span>
        ))}
      </div>
    </div>
  );
}

// ── 03 · drilldown ───────────────────────────────────────────────────────────

function Tile({ k, v, tone, sub }: { k: string; v: string; tone?: string; sub?: string }) {
  return (
    <div className="rounded-lg bg-surface-2 px-3 py-2 min-w-0">
      <div className="text-[11px] text-muted">{k}</div>
      <div className={cn("font-mono text-[15px] font-semibold num", tone ?? "text-text")}>{v}</div>
      {sub && <div className="text-[11px] text-muted truncate">{sub}</div>}
    </div>
  );
}

function PathChart({ d, sel, h }: { d: SectorSignals; sel: Sel; h: number }) {
  const p = d.paths[`${sel.etf}|${sel.signal}`];
  if (!p) return <p className="text-sm text-muted">No past events to chart.</p>;
  const rows = p.mean.map((m, i) => ({ day: i, mean: m, band: [p.null_lo[i], p.null_hi[i]] as [number | null, number | null], mid: p.null_mid[i] }));
  const end = p.mean[p.mean.length - 1];
  return (
    <div>
      <div className="text-xs font-semibold text-text mb-0.5">Average path after the signal vs random dates</div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-text-2 mb-1">
        <span className="flex items-center gap-1.5"><i className="inline-block w-4 h-[2px]" style={{ background: C.text }} />After the signal ({p.n} events)</span>
        <span className="flex items-center gap-1.5"><i className="inline-block w-4 h-[2px] border-t-2 border-dashed" style={{ borderColor: C.muted }} />Random dates, median</span>
        <span className="flex items-center gap-1.5"><i className="inline-block w-3 h-3 rounded-[2px]" style={{ background: C.grid }} />Random dates, 90% range</span>
      </div>
      <div className="h-[220px]">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 8, right: 44, left: 0, bottom: 4 }}>
            <CartesianGrid stroke={C.grid} vertical={false} />
            <XAxis dataKey="day" tickLine={false} axisLine={{ stroke: C.border }} tick={{ fontSize: 11 }} ticks={[0, 5, 10, 15, 20]}
              label={{ value: "trading days after", position: "insideBottomRight", offset: -2, fontSize: 10, fill: C.muted }} />
            <YAxis tickFormatter={(v: number) => pct(v, Math.abs(v) < 0.1 ? 1 : 0)} tickLine={false} axisLine={false} tick={{ fontSize: 11 }} width={44} />
            <Tooltip formatter={(v: number | [number, number], name: string) => [Array.isArray(v) ? `${pct(v[0])} to ${pct(v[1])}` : pct(v), name]}
              labelFormatter={(l) => `Day ${l}`} contentStyle={{ fontSize: 12 }} />
            <Area dataKey="band" name="Random dates, 90%" stroke="none" fill={C.grid} fillOpacity={1} isAnimationActive={false} />
            <Line dataKey="mid" name="Random dates, median" stroke={C.muted} strokeDasharray="4 3" strokeWidth={1.5} dot={false} isAnimationActive={false} />
            <ReferenceLine x={h} stroke={C.borderStrong} strokeDasharray="2 2" />
            <Line dataKey="mean" name="After the signal" stroke={C.text} strokeWidth={2} dot={false} isAnimationActive={false} />
            {end != null && (
              <ReferenceDot x={rows.length - 1} y={end} r={4} fill={C.text} stroke={C.surface} strokeWidth={2}
                label={{ value: pct(end), position: "right", fontSize: 11, fill: C.text }} />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function PriceChart({ d, sel }: { d: SectorSignals; sel: Sel }) {
  const ch = d.charts[sel.etf];
  if (!ch) return null;
  const marks = new Set(ch.events[sel.signal] ?? []);
  const rows = ch.dates.map((dt, i) => ({ dt, close: ch.close[i], mark: marks.has(dt) ? ch.close[i] : null }));
  const label = d.catalog.find((c) => c.id === sel.signal)?.label ?? sel.signal;
  return (
    <div>
      <div className="text-xs font-semibold text-text mb-0.5">{sel.etf}, last 6 months · <span className="font-normal text-text-2">● = {label} fired ({marks.size})</span></div>
      <div className="h-[160px]">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid stroke={C.grid} vertical={false} />
            <XAxis dataKey="dt" tickFormatter={short} tickLine={false} axisLine={{ stroke: C.border }} tick={{ fontSize: 11 }} minTickGap={40} />
            <YAxis domain={["auto", "auto"]} tickLine={false} axisLine={false} tick={{ fontSize: 11 }} width={44} tickFormatter={(v: number) => `$${v.toFixed(0)}`} />
            <Tooltip formatter={(v: number) => `$${v.toFixed(2)}`} labelFormatter={(l) => day(String(l))} contentStyle={{ fontSize: 12 }} />
            <Line dataKey="close" name="Close" stroke={C.accent} strokeWidth={2} dot={false} isAnimationActive={false} />
            <Line dataKey="mark" name={label} stroke="none" isAnimationActive={false} legendType="none"
              dot={{ r: 5, fill: C.text, stroke: C.surface, strokeWidth: 2 }} activeDot={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export function RegimeSplit({ d, t }: { d: SectorSignals; t: SignalTest }) {
  const now = d.sectors.find((s) => s.etf === t.etf)?.regime_now;
  const rows = [
    { name: `VIX < ${d.params.vix_stressed}`, r: t.regimes.vix.calm, now: now?.vix === "calm" },
    { name: `VIX ≥ ${d.params.vix_stressed}`, r: t.regimes.vix.stressed, now: now?.vix === "stressed" },
    { name: "SPY above 200d", r: t.regimes.trend.up, now: now?.trend === "up" },
    { name: "SPY below 200d", r: t.regimes.trend.down, now: now?.trend === "down" },
  ].map((x) => ({ name: x.now ? `${x.name} · now` : x.name, edge: x.r.edge ?? 0, has: x.r.edge != null, n: x.r.n, p: x.r.p, now: x.now }));
  return (
    <div>
      <div className="text-xs font-semibold text-text mb-0.5">Edge by market regime, {t.h} days</div>
      <div className="h-[150px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" margin={{ top: 2, right: 92, left: 0, bottom: 0 }} barCategoryGap={7}>
            <XAxis type="number" hide domain={["dataMin", "dataMax"]} />
            <YAxis type="category" dataKey="name" width={124} tickLine={false} axisLine={false} tick={{ fontSize: 11 }} />
            <ReferenceLine x={0} stroke={C.borderStrong} />
            <Tooltip formatter={(v: number) => pct(v)} contentStyle={{ fontSize: 12 }} />
            <Bar dataKey="edge" name="Edge vs usual" radius={4} isAnimationActive={false}>
              {rows.map((r) => <Cell key={r.name} fill={r.has ? edgeColor(r.edge) : C.grid} fillOpacity={r.now ? 1 : 0.55} />)}
              <LabelList dataKey="edge" content={(p) => {
                  const r = rows[Number(p.index)];
                  const x = Number(p.x ?? 0) + Math.max(Number(p.width ?? 0), 0) + 6;
                  const y = Number(p.y ?? 0) + Number(p.height ?? 0) / 2 + 4;
                  return <text x={x} y={y} fontSize={11} fill={C.text2}>{r.has ? `${pct(r.edge)} · n=${r.n}` : `n=${r.n}`}</text>;
                }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export function Drilldown({ d, sel, h }: { d: SectorSignals; sel: Sel; h: number }) {
  const ix = useIndex(d);
  const t = ix.test(sel.etf, sel.signal, h);
  const s = ix.sig.get(sel.signal);
  const info = d.sectors.find((x) => x.etf === sel.etf);
  const past = d.recent[`${sel.etf}|${sel.signal}`] ?? [];
  if (!t || !s || !info) return <p className="text-sm text-muted">Pick a cell on the map or a signal above.</p>;
  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[15px] font-semibold text-text">{info.sector} · {s.label}</span>
        <VerdictPill v={t.verdict} />
        <span className="text-xs text-muted">{h}-day horizon · {VERDICT[t.verdict].blurb}</span>
      </div>
      <p className="text-[13px] text-text-2 -mt-2">{s.description} Textbook reading: {s.expected > 0 ? "rises after" : "falls after"}.
        {t.textbook === false && <b className="text-text"> On {info.etf} it has done the opposite.</b>}
      </p>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <Tile k="Past events" v={String(t.n)} sub={`since ${day(info.start)}`} />
        <Tile k={`Avg ${h}d after`} v={pct(t.mean)} tone={signedText(t.mean)} sub={`usual ${pct(t.null_mean)}`} />
        <Tile k="Edge" v={pct(t.edge)} tone={signedText(t.edge)} sub={t.z != null ? `z = ${t.z.toFixed(1)} (vol-adjusted)` : undefined} />
        <Tile k="Up after" v={pct(t.hit, 0, false)} sub={`usual ${pct(t.base_hit, 0, false)}`} />
        <Tile k="p-value" v={pval(t.p)} sub="vs shifted calendars" />
        <Tile k="q-value (FDR)" v={pval(t.q)} sub={`signal if ≤ ${d.params.fdr}`} />
        <Tile k="First 70% said" v={VERDICT[t.is.verdict].label} sub={`edge ${pct(t.is.edge)}`} />
        <Tile k={`Since ${short(info.oos_from)}`} v={t.oos.held == null ? "—" : t.oos.held ? "Held" : "Flipped"}
          tone={t.oos.held == null ? undefined : t.oos.held ? "text-success" : "text-danger"} sub={`${t.oos.n} events, edge ${pct(t.oos.edge)}`} />
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <PathChart d={d} sel={sel} h={h} />
        <div className="grid gap-3">
          <PriceChart d={d} sel={sel} />
          <RegimeSplit d={d} t={t} />
        </div>
      </div>
      {past.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs min-w-[420px]">
            <caption className="text-left text-xs font-semibold text-text mb-1">Most recent events</caption>
            <thead>
              <tr className="text-muted text-left">
                <th className="font-normal py-1">Date</th><th className="font-normal text-right">Close</th>
                {d.params.horizons.map((x) => <th key={x} className="font-normal text-right">{x}d after</th>)}
              </tr>
            </thead>
            <tbody className="font-mono num">
              {past.map((e) => (
                <tr key={e.date} className="border-t border-border">
                  <td className="py-1 font-sans">{day(e.date)}</td>
                  <td className="text-right">${e.close.toFixed(2)}</td>
                  {d.params.horizons.map((x) => {
                    const v = e[`r${x}`];
                    return <td key={x} className={cn("text-right", v == null ? "text-muted-2" : signedText(v))}>{v == null ? "pending" : pct(v)}</td>;
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── 04 · does it hold? ───────────────────────────────────────────────────────

export function HoldChart({ d }: { d: SectorSignals }) {
  const o = d.summary.oos;
  const rows = ([["signal", "Called a signal"], ["weak", "Called weak"], ["noise", "Called noise"]] as const)
    .map(([k, name]) => ({ name, rate: o[k].rate, n: o[k].n }))
    .filter((r) => r.rate != null);
  if (!rows.length) return <p className="text-sm text-muted">Not enough history to run the check.</p>;
  return (
    <div className="h-[150px]">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 96, left: 0, bottom: 0 }} barCategoryGap={8}>
          <XAxis type="number" domain={[0, 1]} hide />
          <YAxis type="category" dataKey="name" width={112} tickLine={false} axisLine={false} tick={{ fontSize: 12 }} />
          <ReferenceLine x={0.5} stroke={C.muted} strokeDasharray="4 3" label={{ value: "coin flip", position: "top", fontSize: 10, fill: C.muted }} />
          <Bar dataKey="rate" radius={4} isAnimationActive={false}>
            {rows.map((r, i) => <Cell key={r.name} fill={i === 0 ? C.accent : C.muted2} />)}
            <LabelList dataKey="rate" content={(p) => {
              const r = rows[Number(p.index)];
              return <text x={Number(p.x ?? 0) + Number(p.width ?? 0) + 6} y={Number(p.y ?? 0) + Number(p.height ?? 0) / 2 + 4} fontSize={11} fill={C.text2}>
                {pct(r.rate, 0, false)} of {r.n}
              </text>;
            }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function useDefaultSel(d: SectorSignals | null | undefined): Sel | null {
  return useMemo(() => {
    if (!d) return null;
    const live = d.live.find((e) => e.verdict !== "few") ?? d.live[0];
    if (live) return { etf: live.etf, signal: live.signal };
    const h = Math.max(...d.params.horizons);
    const best = [...d.tests].filter((t) => t.h === h && t.z != null).sort((a, b) => Math.abs(b.z!) - Math.abs(a.z!))[0];
    return best ? { etf: best.etf, signal: best.signal } : null;
  }, [d]);
}

