import type { WeekEvent } from "@/api/types";
import { C } from "@/lib/theme";
import { COUNTRY, useTip } from "./Tooltip";

/** Dumbbell: previous reading → consensus, for this week's y/y inflation releases. */
export function InflationExpectations({ events }: { events: WeekEvent[] }) {
  const { show, hide, node } = useTip();
  const rows = events
    .filter((e) => e.kind === "inflation" && e.measure !== "m/m" && e.unit === "%" && e.consensus != null && e.previous != null)
    .sort((a, b) => `${a.date}${a.time_et}`.localeCompare(`${b.date}${b.time_et}`));
  if (!rows.length) return <p className="text-sm text-muted">No inflation release with a consensus this week.</p>;
  const vals = rows.flatMap((e) => [e.consensus!, e.previous!]);
  const lo = Math.min(0, Math.floor(Math.min(...vals))), hi = Math.ceil(Math.max(...vals) * 1.1);
  const Lx = 150, Rx = 500, T = 14, RH = 40, x = (v: number) => Lx + ((v - lo) / (hi - lo || 1)) * (Rx - Lx);
  const step = Math.max(1, Math.ceil((hi - lo) / 5));
  const ticks = Array.from({ length: Math.floor((hi - lo) / step) + 1 }, (_, i) => lo + i * step);
  const H = T + RH * rows.length + 22;
  return (
    <>
      <svg viewBox={`0 0 560 ${H}`} className="w-full h-auto overflow-visible" role="img" aria-label="Inflation releases: previous versus consensus">
        {ticks.map((v) => (
          <g key={v}>
            <line x1={x(v)} x2={x(v)} y1={T - 6} y2={T + RH * rows.length} stroke={C.grid} />
            <text x={x(v)} y={H - 4} textAnchor="middle" fontSize={11} fill={C.muted}>{v}%</text>
          </g>
        ))}
        {rows.map((e, i) => {
          const y = T + RH * i + RH / 2, p = e.previous!, c = e.consensus!, d = c - p;
          const day = new Date(e.date + "T12:00:00").toLocaleDateString("en-US", { weekday: "short" });
          return (
            <g key={i} onMouseLeave={hide}
              onMouseMove={(ev) => show(ev, <><b>{COUNTRY[e.country!]} {e.name} {e.measure ?? ""} · {day}</b><div>Previous {p}% → consensus {c}%</div></>)}>
              <rect x={0} y={y - RH / 2} width={560} height={RH} fill="transparent" />
              <text x={Lx - 12} y={y - 2} textAnchor="end" fontSize={12} fontWeight={600} fill={C.text}>{COUNTRY[e.country!]} {e.name}</text>
              <text x={Lx - 12} y={y + 12} textAnchor="end" fontSize={10.5} fill={C.muted}>{day}{e.measure ? ` · ${e.measure}` : ""}</text>
              <line x1={x(p)} x2={x(c)} y1={y} y2={y} stroke={C.inflation} strokeWidth={2.5} strokeOpacity={0.5} />
              <circle cx={x(p)} cy={y} r={6} fill={C.surface} stroke={C.muted} strokeWidth={2} />
              <circle cx={x(c)} cy={y} r={6.5} fill={C.inflation} stroke={C.surface} strokeWidth={2} />
              <text x={x(Math.max(p, c)) + 12} y={y + 4} fontSize={11} fontWeight={600} fill={C.text}>
                {d === 0 ? "unch." : `${d > 0 ? "+" : ""}${+d.toFixed(2)} pp`}
              </text>
            </g>
          );
        })}
      </svg>
      {node}
    </>
  );
}
