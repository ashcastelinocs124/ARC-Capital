import type { WeekAhead, WeekEvent } from "@/api/types";
import { C } from "@/lib/theme";
import { company } from "@/lib/company";
import { COUNTRY, fmt, releaseLine, useTip } from "./Tooltip";

const ROWS = ["US", "CN", "DE", "JP", "IN", "earnings", "ai"] as const;
const LABEL: Record<string, string> = { ...COUNTRY, earnings: "Earnings", ai: "AI launches" };
const W = 1200, L = 120, R = 1185, T = 34, ROW_H = 50;
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"];

const dayIdx = (start: string, d: string) => Math.round((Date.parse(d) - Date.parse(start)) / 864e5);
const hours = (t: string | null) => (t ? +t.slice(0, 2) + +t.slice(3) / 60 : 12);
const x = (d: number, h: number) => L + ((d + h / 24) * (R - L)) / 5;
const cy = (row: number) => T + ROW_H * row + ROW_H / 2;
const rowOf = (c: string) => ROWS.indexOf(c as (typeof ROWS)[number]);

function nowX(start: string): number | null {
  const ny = new Date(new Date().toLocaleString("en-US", { timeZone: "America/New_York" }));
  const d = Math.floor((ny.getTime() - Date.parse(start + "T00:00:00")) / 864e5);
  return d >= 0 && d < 5 ? x(d, ny.getHours() + ny.getMinutes() / 60) : null;
}

/** The week on one timeline: a row per economy, then earnings and AI launches. */
export function WeekMap({ data }: { data: WeekAhead }) {
  const { show, hide, node } = useTip();
  const start = data.week_start;
  const H = T + ROW_H * ROWS.length + 26;
  const marks: React.ReactElement[] = [];
  const under: React.ReactElement[] = []; // grey dots sit beneath the tier-1 marks

  // Tier-1 releases: one mark per country + day + time + kind (m/m and y/y pairs, CN CPI+PPI merge).
  const groups = new Map<string, WeekEvent[]>();
  for (const e of data.events) {
    if (!e.date || !e.country || (e.kind !== "inflation" && e.kind !== "jobs")) continue;
    const k = `${e.country}|${e.date}|${e.time_et}|${e.kind}`;
    groups.set(k, [...(groups.get(k) ?? []), e]);
  }
  const lastLabel: Record<string, number> = {};
  [...groups.values()]
    .sort((a, b) => (a[0].date! + (a[0].time_et ?? "")).localeCompare(b[0].date! + (b[0].time_et ?? "")))
    .forEach((g, i) => {
      const e = g[0], X = x(dayIdx(start, e.date!), hours(e.time_et)), Y = cy(rowOf(e.country!));
      const names = [...new Set(g.map((v) => v.name))];
      const joined = names.join(" · ");
      const label = joined.length <= 16 ? joined : `${names[0].length > 18 ? `${names[0].slice(0, 17)}…` : names[0]}${names.length > 1 ? ` +${names.length - 1}` : ""}`;
      const below = X - (lastLabel[e.country!] ?? -1e9) < 90;
      lastLabel[e.country!] = below ? -1e9 : X;
      const tip = (ev: React.MouseEvent) =>
        show(ev, <><b>{COUNTRY[e.country!]} · {e.date} {e.time_et ?? ""} ET</b>{g.map((v, j) => <div key={j}>{releaseLine(v)}</div>)}</>);
      marks.push(
        <g key={`t${i}`} onMouseMove={tip} onMouseLeave={hide}>
          {e.kind === "jobs"
            ? <rect x={X - 7} y={Y - 7} width={14} height={14} rx={2} fill={C.jobs} stroke={C.surface} strokeWidth={2} />
            : <circle cx={X} cy={Y} r={8} fill={C.inflation} stroke={C.surface} strokeWidth={2} />}
          <text x={X} y={below ? Y + 21 : Y - 13} textAnchor="middle" fontSize={10.5} fontWeight={600} fill={C.text}>{label}</text>
          <circle cx={X} cy={Y} r={13} fill="transparent" />
        </g>,
      );
    });

  // Other releases: small grey dots.
  data.events.filter((e) => e.kind === "other" && e.date && e.country).forEach((e, i) => {
    const X = x(dayIdx(start, e.date!), hours(e.time_et)), Y = cy(rowOf(e.country!));
    under.push(
      <g key={`o${i}`} onMouseMove={(ev) => show(ev, <><b>{COUNTRY[e.country!]} · {e.time_et ?? "all day"} ET</b><div>{releaseLine(e)}</div></>)} onMouseLeave={hide}>
        <circle cx={X} cy={Y} r={3.5} fill={C.muted2} />
        <circle cx={X} cy={Y} r={8} fill="transparent" />
      </g>,
    );
  });

  // Earnings: per day, biggest first, packed left to right, sized by market cap.
  const byDay = new Map<number, WeekEvent[]>();
  data.events.filter((e) => e.kind === "earnings" && e.date).forEach((e) => {
    const d = dayIdx(start, e.date!);
    byDay.set(d, [...(byDay.get(d) ?? []), e]);
  });
  byDay.forEach((list, d) => {
    list.sort((a, b) => (b.market_cap ?? 0) - (a.market_cap ?? 0));
    let cur = x(d, 1.5), hidden = 0;
    const end = x(d + 1, 0) - 26;
    list.forEach((e, j) => {
      const r = Math.max(4, Math.sqrt((e.market_cap ?? 0) / 1e9) * 0.55);
      if (cur + 2 * r > end) { hidden++; return; }
      const X = cur + r, Y = cy(5);
      cur = X + r + 3;
      // growth off a zero or negative base is meaningless (same rule as EpsGrowth)
      const g = (e.eps_est ?? 0) > 0 && (e.eps_year_ago ?? 0) > 0 ? ((e.eps_est! / e.eps_year_ago! - 1) * 100).toFixed(1) : null;
      const session = e.session === "pre" ? "pre-market" : e.session === "post" ? "after the close" : "time not given";
      marks.push(
        <g key={`e${d}-${j}`} onMouseLeave={hide} onMouseMove={(ev) => show(ev, <>
          <b>{company(e.company ?? e.name, e.ticker ?? "")}</b>
          <div>{e.date} · {session}</div>
          <div>EPS est {fmt(e.eps_est)} vs {fmt(e.eps_year_ago)} a year ago{g ? ` (${+g > 0 ? "+" : ""}${g}%)` : ""}</div>
        </>)}>
          <circle cx={X} cy={Y} r={r} fill={C.earnings} fillOpacity={0.85} stroke={C.surface} strokeWidth={2} />
          {r >= 12 && <text x={X} y={Y + 3.5} textAnchor="middle" fontSize={r > 13 ? 10 : 8.5} fontWeight={700} fill={C.surface}>{e.ticker}</text>}
          <circle cx={X} cy={Y} r={r + 3} fill="transparent" />
        </g>,
      );
    });
    if (hidden) marks.push(<text key={`h${d}`} x={cur + 2} y={cy(5) + 4} fontSize={10} fill={C.muted}>+{hidden}</text>);
  });

  // AI: pre-week launches pack into Monday's left strip, in-week ones pack from midday on their day;
  // each slot is ~2.6 h (one diamond wide) and overflow becomes "+N".
  const aiSlots = new Map<number, WeekEvent[]>(); // -1 = before the week
  data.events.filter((e) => e.kind === "ai" && e.date && e.date <= data.week_end).forEach((e) => {
    const d = e.date! < start ? -1 : dayIdx(start, e.date!);
    aiSlots.set(d, [...(aiSlots.get(d) ?? []), e]);
  });
  aiSlots.forEach((list, d) => {
    const [day, h0, cap] = d < 0 ? [0, 0.8, 3] : [d, 12, 4];
    list.slice(0, cap).forEach((e, j) => {
      const X = x(day, h0 + j * 2.6), Y = cy(6);
      const reported = e.status === "reported";
      marks.push(
        <g key={`a${d}-${j}`} onMouseLeave={hide}
          onMouseMove={(ev) => show(ev, <><b>{e.name}</b><div>{e.lab} · {reported ? `reported for ${e.when}` : `launched ${e.date} on OpenRouter`}</div></>)}>
          <a href={e.source_url} target="_blank" rel="noreferrer">
            <rect x={X - 7} y={Y - 7} width={14} height={14} transform={`rotate(45 ${X} ${Y})`}
              fill={reported ? C.surface : C.ai} stroke={C.ai} strokeWidth={2} strokeDasharray={reported ? "3 2" : undefined} />
            <circle cx={X} cy={Y} r={12} fill="transparent" />
          </a>
        </g>,
      );
    });
    if (list.length > cap) {
      const more = list.slice(cap).map((e) => e.name).join(", ");
      marks.push(
        <text key={`ah${d}`} x={x(day, h0 + cap * 2.6) - 4} y={cy(6) + 4} fontSize={10} fill={C.muted}
          onMouseMove={(ev) => show(ev, <>{more}</>)} onMouseLeave={hide}>+{list.length - cap}</text>,
      );
    }
  });
  const nx = nowX(start);

  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} className="min-w-[760px] w-full h-auto overflow-visible" role="img"
        aria-label="This week's releases, earnings and AI launches on a timeline">
        {DAYS.map((d, i) => (
          <g key={d}>
            <rect x={x(i, 0)} y={T} width={(R - L) / 5} height={ROW_H * ROWS.length} fill={i % 2 ? C.soft : C.surface} />
            <line x1={x(i, 8.5)} x2={x(i, 8.5)} y1={T} y2={T + ROW_H * 5} stroke={C.grid} strokeDasharray="3 3" />
            <text x={x(i, 12)} y={T - 12} textAnchor="middle" fontWeight={600} fontSize={12} fill={C.text}>
              {d} {new Date(Date.parse(start + "T12:00:00") + i * 864e5).getDate()}
            </text>
          </g>
        ))}
        {ROWS.map((r, i) => (
          <g key={r}>
            <line x1={L} x2={R} y1={T + ROW_H * (i + 1)} y2={T + ROW_H * (i + 1)} stroke={C.grid} />
            <text x={L - 10} y={cy(i) + 4} textAnchor="end" fontSize={12} fontWeight={i > 4 ? 600 : 500} fill={C.text}>{LABEL[r]}</text>
          </g>
        ))}
        <text x={x(4, 8.5)} y={H - 6} textAnchor="middle" fontSize={10} fill={C.muted}>08:30 ET</text>
        {nx != null && (
          <>
            <line x1={nx} x2={nx} y1={T - 4} y2={T + ROW_H * ROWS.length} stroke={C.accent} strokeWidth={2} />
            <text x={nx + 4} y={H - 6} fontSize={10} fontWeight={700} fill={C.accent}>now</text>
          </>
        )}
        {under}
        {marks}
      </svg>
      {node}
    </div>
  );
}
