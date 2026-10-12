import type { SectorRow } from "@/api/types";
import { C } from "@/lib/theme";
import { useTip } from "./Tooltip";

const pct = (v: number) => `${v > 0 ? "+" : ""}${v}%`;

/** Each sector by trailing P/E (x) and YTD return (y); the S&P 500 crosshair splits the quadrants. */
export function SectorValuation({ rows }: { rows: SectorRow[] }) {
  const { show, hide, node } = useTip();
  const bench = rows.find((r) => r.etf === "SPY");
  const pts = rows.filter((r) => r.etf !== "SPY" && r.pe != null);
  if (!pts.length) return <p className="text-sm text-muted">Sector data unavailable.</p>;
  const all = bench?.pe != null ? [...pts, bench] : pts;
  const pes = all.map((r) => r.pe!), ytds = all.map((r) => r.ytd);
  const x0 = Math.floor(Math.min(...pes) / 2) * 2 - 2, x1 = Math.ceil(Math.max(...pes) / 2) * 2 + 2;
  const y0 = Math.floor(Math.min(0, ...ytds) / 10) * 10, y1 = Math.ceil(Math.max(...ytds) / 10) * 10;
  const W = 1100, L = 60, R = 1060, T = 16, B = 380;
  const x = (v: number) => L + ((v - x0) / (x1 - x0)) * (R - L), y = (v: number) => B - ((v - y0) / (y1 - y0)) * (B - T);
  const yTicks = Array.from({ length: (y1 - y0) / 10 + 1 }, (_, i) => y0 + i * 10);
  const xStep = Math.max(2, Math.round((x1 - x0) / 6 / 2) * 2);
  const xTicks = Array.from({ length: Math.floor((x1 - x0) / xStep) + 1 }, (_, i) => x0 + i * xStep);
  // nudge a label down when it would sit on one already placed
  const placed: [number, number][] = [];
  const labelY = (X: number, Y: number) => {
    let ly = Y + 4;
    while (placed.some(([px, py]) => Math.abs(px - X) < 120 && Math.abs(py - ly) < 13)) ly += 13;
    placed.push([X, ly]);
    return ly;
  };
  return (
    <>
      <svg viewBox={`0 0 ${W} ${B + 44}`} className="w-full h-auto overflow-visible" role="img" aria-label="Sectors: year-to-date return versus trailing P/E">
        {yTicks.map((v) => (
          <g key={v}>
            <line x1={L} x2={R} y1={y(v)} y2={y(v)} stroke={v === 0 ? C.muted2 : C.grid} />
            <text x={L - 8} y={y(v) + 4} textAnchor="end" fontSize={11} fill={C.muted}>{pct(v)}</text>
          </g>
        ))}
        {xTicks.map((v) => <text key={v} x={x(v)} y={B + 18} textAnchor="middle" fontSize={11} fill={C.muted}>{v}×</text>)}
        <text x={(L + R) / 2} y={B + 38} textAnchor="middle" fontSize={11} fill={C.muted}>Trailing P/E</text>
        {bench?.pe != null && (
          <>
            <line x1={x(bench.pe)} x2={x(bench.pe)} y1={T} y2={B} stroke={C.muted2} strokeDasharray="4 4" />
            <line x1={L} x2={R} y1={y(bench.ytd)} y2={y(bench.ytd)} stroke={C.muted2} strokeDasharray="4 4" />
            <text x={L + 8} y={T + 12} fontSize={10.5} fill={C.muted2}>Ran up · cheaper than market</text>
            <text x={R - 8} y={T + 12} textAnchor="end" fontSize={10.5} fill={C.muted2}>Ran up · pricier than market</text>
            <text x={L + 8} y={B - 8} fontSize={10.5} fill={C.muted2}>Lagged · cheaper</text>
            <text x={R - 8} y={B - 8} textAnchor="end" fontSize={10.5} fill={C.muted2}>Lagged · pricier</text>
          </>
        )}
        {[...pts].sort((a, b) => b.ytd - a.ytd).map((r) => {
          const X = x(r.pe!), Y = y(r.ytd), g = r.earnings_growth;
          return (
            <g key={r.etf} onMouseLeave={hide}
              onMouseMove={(ev) => show(ev, <><b>{r.sector} ({r.etf})</b><div>YTD {pct(r.ytd)} · P/E {r.pe}×</div><div>Earnings growth {g == null ? "–" : pct(g)} (median, top 10)</div></>)}>
              <circle cx={X} cy={Y} r={8} fill={g == null ? C.muted2 : g >= 0 ? C.earnings : C.danger} stroke={C.surface} strokeWidth={2} />
              <text x={X + 12} y={labelY(X, Y)} fontSize={12} fontWeight={600} fill={C.text}>{r.sector}</text>
              <circle cx={X} cy={Y} r={14} fill="transparent" />
            </g>
          );
        })}
        {bench?.pe != null && (
          <g onMouseLeave={hide} onMouseMove={(ev) => show(ev, <><b>S&amp;P 500 (SPY)</b><div>YTD {pct(bench.ytd)} · P/E {bench.pe}×</div></>)}>
            <circle cx={x(bench.pe)} cy={y(bench.ytd)} r={8} fill={C.surface} stroke={C.text} strokeWidth={2.5} />
            <text x={x(bench.pe) + 12} y={labelY(x(bench.pe), y(bench.ytd))} fontSize={12} fontWeight={700} fill={C.text}>S&amp;P 500</text>
            <circle cx={x(bench.pe)} cy={y(bench.ytd)} r={14} fill="transparent" />
          </g>
        )}
      </svg>
      {node}
    </>
  );
}
