import { type AiCapex } from "@/api/aiCapex";
import { C } from "@/lib/theme";
import { Chapter, SourceLink, Unavailable } from "./Chapter";
import { ChartTitle, HBars, PowerBars, Spark } from "./charts";

const MIN_DAYS = 14; // our own daily readings; Silicon Data's page shows no history
const GPU_NAME: Record<string, string> = { MI300X: "AMD MI300X" };
const day = (d: string) => new Date(`${d}T12:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });

export function Compute({ data }: { data: AiCapex }) {
  const neo = data.companies.filter((c) => c.kind === "neocloud");
  const power = [
    ...neo.filter((c) => c.power?.online_gw && c.power?.contracted_gw)
      .map((c) => ({ name: c.name, online: c.power!.online_gw!, contracted: c.power!.contracted_gw!, color: C.co[c.ticker] ?? C.muted })),
    ...data.private.filter((p) => p.online_gw && p.contracted_gw)
      .map((p) => ({ name: p.name, online: p.online_gw!, contracted: p.contracted_gw!, color: C.co.private, cited: true })),
  ];
  const years = neo
    .filter((c) => c.backlog && c.ttm?.revenue)
    .map((c) => ({ name: c.name, value: Math.round((c.backlog!.value / c.ttm.revenue!) * 10) / 10, color: C.co[c.ticker] ?? C.muted }));
  const gpu = data.gpu;
  const dates = gpu ? [...new Set(gpu.history.map((h) => h.date))].sort() : [];
  const h100 = gpu?.history.filter((h) => h.gpu === "H100").map((h) => h.price) ?? [];
  const events = neo.flatMap((c) => (c.events ?? []).map((e) => ({ ...e, name: c.name }))).sort((a, b) => b.date.localeCompare(a.date));
  return (
    <Chapter
      id="compute" n="04" tag="COMPUTE" question="Is compute the bottleneck?" sentence={data.sentences.compute}
      note="Rental prices that rise while supply grows mean demand is outrunning supply."
    >
      <div className="grid gap-5 lg:grid-cols-2">
        <div className="min-w-0">
          <ChartTitle>Power online vs contracted, GW</ChartTitle>
          {power.length ? (
            <PowerBars rows={power} label={`Power online versus contracted: ${power.map((p) => `${p.name} ${p.online} of ${p.contracted} gigawatts`).join(", ")}`} />
          ) : <Unavailable what="earnings releases" />}
        </div>
        <div className="min-w-0">
          <ChartTitle>Years of backlog at today's revenue</ChartTitle>
          {years.length ? (
            <HBars rows={years} max={Math.max(...years.map((y) => y.value)) * 1.15} fmt={(v) => `${v} yrs`}
              label={`Years of backlog at current revenue: ${years.map((y) => `${y.name} ${y.value}`).join(", ")}`} />
          ) : <Unavailable what="earnings releases" />}
        </div>
        <div className="min-w-0">
          <ChartTitle>GPU rental price, $ per GPU-hour</ChartTitle>
          {gpu?.rows.length ? (
            <>
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="text-[11px] uppercase tracking-[0.05em] text-muted">
                    <th scope="col" className="text-left font-semibold py-1">GPU</th>
                    <th scope="col" className="text-right font-semibold">Price</th>
                    <th scope="col" className="text-right font-semibold">vs a week ago</th>
                  </tr>
                </thead>
                <tbody>
                  {gpu.rows.map((r) => (
                    <tr key={r.gpu} className="border-t border-border">
                      <td className="py-1.5">{GPU_NAME[r.gpu] ?? `Nvidia ${r.gpu}`}</td>
                      <td className="num text-right">${r.price.toFixed(2)}</td>
                      <td className={`num text-right ${r.change_7d_pct < 0 ? "text-danger" : "text-success"}`}>
                        {r.change_7d_pct < 0 ? "▼" : "▲"} {Math.abs(r.change_7d_pct)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {dates.length >= MIN_DAYS && h100.length >= 2 && (
                <div className="mt-3">
                  <div className="text-xs text-muted mb-1">H100, since {day(dates[0])}</div>
                  <Spark values={h100} label={`H100 rental price from $${h100[0]} to $${h100[h100.length - 1]} per GPU-hour`} />
                </div>
              )}
              <p className="text-xs text-muted mt-2">
                Source: <SourceLink title="Silicon Data index" url={gpu.source.url} />, read daily from its public page
                {dates.length < MIN_DAYS ? `. The chart appears after ${MIN_DAYS} days of readings; history started ${dates[0] ? day(dates[0]) : "today"}.` : "."}
              </p>
            </>
          ) : <Unavailable what="Silicon Data" />}
        </div>
        <div className="min-w-0">
          <div className="eyebrow">When supply ran late</div>
          {events.length ? (
            <ul className="mt-1 text-[12.5px] leading-[18px] text-text-2">
              {events.map((e, i) => (
                <li key={i} className="border-t border-border py-2">
                  <span className="font-mono text-[11px] text-warning mr-1.5">{e.date}</span>
                  <b className="text-text">{e.name}</b> {e.text} <SourceLink title="source" url={e.source.url} />
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-muted mt-1">No cited delays this week.</p>}
        </div>
      </div>
    </Chapter>
  );
}
