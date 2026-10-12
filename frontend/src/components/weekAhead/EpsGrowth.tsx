import type { WeekEvent } from "@/api/types";
import { C } from "@/lib/theme";
import { company } from "@/lib/company";
import { useTip } from "./Tooltip";

/** Expected EPS growth vs a year ago for this week's reporters. */
export function EpsGrowth({ events }: { events: WeekEvent[] }) {
  const { show, hide, node } = useTip();
  // growth off a zero or negative base is meaningless
  const rows = events
    .filter((e) => e.kind === "earnings" && (e.eps_est ?? 0) > 0 && (e.eps_year_ago ?? 0) > 0)
    .map((e) => ({ e, g: (e.eps_est! / e.eps_year_ago! - 1) * 100 }))
    .sort((a, b) => b.g - a.g);
  if (!rows.length) return <p className="text-sm text-muted">No reporter with an EPS estimate this week.</p>;
  const lo = Math.min(0, ...rows.map((r) => r.g)), hi = Math.max(10, ...rows.map((r) => r.g));
  const Lx = 64, Rx = 510, T = 8, RH = 18, x = (v: number) => Lx + ((v - lo) / (hi - lo)) * (Rx - Lx), x0 = x(0);
  const H = T + RH * rows.length + 20;
  return (
    <>
      <svg viewBox={`0 0 560 ${H}`} className="w-full h-auto overflow-visible" role="img" aria-label="Expected EPS growth versus a year ago">
        <line x1={x0} x2={x0} y1={T} y2={T + RH * rows.length} stroke={C.muted2} />
        {rows.map(({ e, g }, i) => {
          const y = T + RH * i, neg = g < 0;
          return (
            <g key={e.ticker} onMouseLeave={hide}
              onMouseMove={(ev) => show(ev, <><b>{company(e.company ?? e.name, e.ticker ?? "")}</b><div>{e.date} · EPS est ${e.eps_est!.toFixed(2)} vs ${e.eps_year_ago!.toFixed(2)} a year ago</div></>)}>
              <rect x={0} y={y} width={560} height={RH} fill="transparent" />
              <text x={Lx - 8} y={y + 12.5} textAnchor="end" fontSize={11} fill={C.text}>{e.ticker}</text>
              <rect x={neg ? x(g) : x0} y={y + 3} width={Math.max(1, Math.abs(x(g) - x0))} height={RH - 6} rx={3} fill={neg ? C.muted2 : C.earnings} />
              <text x={neg ? x0 + 5 : x(g) + 5} y={y + 12.5} fontSize={10.5} fill={C.text2}>
                {g > 0 ? "+" : ""}{g.toFixed(0)}%
              </text>
            </g>
          );
        })}
      </svg>
      {node}
    </>
  );
}
