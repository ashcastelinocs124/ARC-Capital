import { useEffect, useState } from "react";
import { cn } from "@/lib/cn";
import { C } from "@/lib/theme";
import { PageIntro } from "@/components/layout/PageIntro";
import { call } from "@/components/admin/DailyDesk";

// Admin Costs: every logged model call's tokens × that model's list price (src/castelino/costs.py),
// read live from the call logs on the Fly machine, plus the Fly server itself at list price. The
// server sends one row per (day, agent, model), the Fly server as provider "fly" with no calls;
// the tiles, chart and tables are sums of those rows.
type Provider = "openai" | "anthropic" | "openrouter" | "fly";
type Row = {
  day: string;
  agent: string;
  model: string;
  provider: Provider;
  calls: number;
  tokens_in: number;
  tokens_out: number;
  usd: number | null; // null = no price for this model
};
type Summary = {
  days: number;
  today: string;
  prices_as_of: string;
  prices: Record<string, [number, number]>;
  search_fee: number;
  fly_usd_month: number;
  rows: Row[];
};

const PROVIDERS: [Provider, string, string][] = [
  ["openai", "OpenAI", C.accent],
  ["anthropic", "Anthropic", C.inflation],
  ["openrouter", "OpenRouter", C.ai],
  ["fly", "Fly.io", C.jobs],
];
const RANGES = [7, 30, 90];
const DAY = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
const fmtDay = (d: string) => DAY.format(new Date(`${d}T00:00:00Z`));
const money = (x: number) => (x >= 10 ? `$${x.toFixed(1)}` : x >= 0.01 || x === 0 ? `$${x.toFixed(2)}` : "<$0.01");
const big = (n: number) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${Math.round(n / 1e3)}k` : String(n));
const usd = (rows: Row[]) => rows.reduce((a, r) => a + (r.usd ?? 0), 0);
const sum = (rows: Row[], k: "calls" | "tokens_in" | "tokens_out") => rows.reduce((a, r) => a + r[k], 0);
const niceTop = (max: number) => {
  if (max <= 0) return 1;
  const step = 10 ** Math.floor(Math.log10(max));
  return Math.ceil(max / step) * step;
};

function daysBack(today: string, n: number) {
  const t = new Date(`${today}T00:00:00Z`).getTime();
  return Array.from({ length: n }, (_, i) => new Date(t - (n - 1 - i) * 864e5).toISOString().slice(0, 10));
}

// Sum rows by one key, priciest first. A group is unpriced only if none of its rows has a price.
function group(rows: Row[], key: "model" | "agent") {
  const m = new Map<string, { k: string; provider: Provider; calls: number; tin: number; tout: number; usd: number | null }>();
  for (const r of rows) {
    const g = m.get(r[key]) ?? { k: r[key], provider: r.provider, calls: 0, tin: 0, tout: 0, usd: null };
    g.calls += r.calls;
    g.tin += r.tokens_in;
    g.tout += r.tokens_out;
    if (r.usd !== null) g.usd = (g.usd ?? 0) + r.usd;
    m.set(r[key], g);
  }
  return [...m.values()].sort((a, b) => (b.usd ?? -1) - (a.usd ?? -1));
}

function Chip({ p }: { p: Provider }) {
  const [, name, color] = PROVIDERS.find(([id]) => id === p)!;
  return (
    <span className="ml-1.5 rounded-full px-2 py-0.5 text-[10.5px] font-bold" style={{ color, background: `color-mix(in srgb, ${color} 14%, transparent)` }}>
      {name}
    </span>
  );
}

function Tile({ label, value, sub }: { label: string; value: React.ReactNode; sub: string }) {
  return (
    <div className="card px-4 py-4">
      <div className="eyebrow">{label}</div>
      <div className="num mt-1.5 text-[28px] font-bold leading-tight text-text">{value}</div>
      <div className="mt-1 text-xs text-muted">{sub}</div>
    </div>
  );
}

export default function Costs() {
  const [range, setRange] = useState(30);
  const [data, setData] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [picked, setPicked] = useState<string | null>(null);
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    setPicked(null);
    setError(null);
    call<Summary>(`/costs?days=${range}`).then(setData, (e: Error) => setError(e.message));
  }, [range]);

  const intro = (
    <PageIntro kicker="Admin · Model costs" title="What the models cost">
      Every model call&apos;s tokens × that model&apos;s list price, from the call logs on the Fly server, plus the Fly server
      itself. OpenAI, Anthropic, OpenRouter and Fly.io, by day, model and agent. An estimate, not your invoice.
    </PageIntro>
  );
  const rangeSwitch = (
    <div className="flex w-fit rounded-full border border-border bg-surface-2 p-[3px]">
      {RANGES.map((d) => (
        <button key={d} onClick={() => setRange(d)}
          className={cn("rounded-full px-3.5 py-1.5 text-[13px] font-semibold",
            d === range ? "bg-surface text-text ring-1 ring-border" : "text-text-2 hover:text-text")}>
          {d} days
        </button>
      ))}
    </div>
  );
  if (error) {
    return (
      <div className="space-y-4 px-4 pb-8 md:px-8">
        {intro}
        <div className="card p-6 text-sm text-danger">Couldn&apos;t load costs: {error}</div>
      </div>
    );
  }
  if (!data || data.days !== range) {
    return (
      <div className="space-y-4 px-4 pb-8 md:px-8">
        {intro}
        <div className="text-sm text-muted">Loading costs…</div>
      </div>
    );
  }

  const days = daysBack(data.today, range);
  const byDay = new Map(days.map((d) => [d, data.rows.filter((r) => r.day === d)]));
  const top = niceTop(Math.max(0, ...days.map((d) => usd(byDay.get(d)!))));
  const week = data.rows.filter((r) => r.day >= days[days.length - 7]);
  const todayRows = byDay.get(data.today)!;
  const shown = picked ? byDay.get(picked)! : data.rows;
  const total = usd(shown);
  const models = group(shown, "model");
  const agents = group(shown, "agent");
  const topAgent = group(data.rows, "agent")[0];
  const first = data.rows.reduce<string | null>((a, r) => (r.provider === "fly" || (a !== null && r.day >= a) ? a : r.day), null);
  const fly = (p: Provider) => p === "fly";
  const unpriced = group(data.rows, "model").filter((g) => g.usd === null);
  // Chart segments: one per provider, except OpenRouter, which gets one per model (priciest first) in
  // shades of its purple, so the models stay readable as one provider.
  const orModels = group(data.rows.filter((r) => r.provider === "openrouter"), "model").map((g) => g.k);
  const segs = PROVIDERS.flatMap(([p, name, color]) =>
    p !== "openrouter"
      ? [{ key: p, name, color, rows: (rs: Row[]) => rs.filter((r) => r.provider === p) }]
      : orModels.map((m, i) => ({
          key: m,
          name: m.split("/").pop()!,
          color: `color-mix(in srgb, ${color} ${100 - (i * 55) / Math.max(1, orModels.length - 1)}%, white)`,
          rows: (rs: Row[]) => rs.filter((r) => r.model === m),
        })),
  );
  const every = range > 30 ? 14 : range > 7 ? 5 : 1;
  const filter = (
    <button onClick={() => setPicked(null)} disabled={!picked} className="text-xs font-semibold text-accent disabled:cursor-default">
      {picked ? `Showing ${fmtDay(picked)} only · clear ✕` : `All ${range} days`}
    </button>
  );

  return (
    <div className="space-y-5 px-4 pb-8 md:px-8">
      <div className="grid gap-4 md:grid-cols-[1fr_auto] md:items-center">
        {intro}
        {rangeSwitch}
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Tile label="Today" value={money(usd(todayRows))}
          sub={`${sum(todayRows, "calls")} calls · ${big(sum(todayRows, "tokens_in") + sum(todayRows, "tokens_out"))} tokens`} />
        <Tile label="Last 7 days" value={money(usd(week))} sub={`≈ ${money(usd(week) / 7)} a day`} />
        <Tile label={`Last ${range} days`} value={money(usd(data.rows))}
          sub={PROVIDERS.filter(([p]) => p !== "openai")
            .map(([p, name]) => `${name} ${Math.round((usd(data.rows.filter((r) => r.provider === p)) / (usd(data.rows) || 1)) * 100)}%`)
            .join(" · ")} />
        <Tile label="Biggest line"
          value={topAgent ? <span className="font-mono text-[17px]">{topAgent.k}</span> : "—"}
          sub={topAgent ? `${money(topAgent.usd ?? 0)} · ${Math.round(((topAgent.usd ?? 0) / (usd(data.rows) || 1)) * 100)}% of the ${range} days` : "No calls logged yet"} />
      </div>

      <div className="card relative p-4 md:p-5">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <h2 className="text-[15px] font-semibold text-text">Spend per day</h2>
          <div className="flex flex-wrap gap-x-3.5 gap-y-1 text-xs text-text-2">
            {segs.map((g) => (
              <span key={g.key} className="inline-flex items-center gap-1.5">
                <i className="h-2.5 w-2.5 rounded-sm" style={{ background: g.color }} />
                {g.key.includes("/") ? <span className="font-mono">{g.name}</span> : g.name}
              </span>
            ))}
          </div>
        </div>
        <div className="relative mt-3.5 flex h-[210px] items-end gap-1 border-b border-border pl-10">
          {[0, 0.5, 1].map((f) => (
            <div key={f} className="absolute left-0 right-0" style={{ bottom: `${f * 100}%` }}>
              <span className="absolute w-9 translate-y-1/2 text-right text-[10.5px] text-muted-2">{money(top * f)}</span>
              {f > 0 && <div className="ml-10 border-t border-dashed border-border" />}
            </div>
          ))}
          {days.map((d, i) => {
            const rows = byDay.get(d)!;
            const dayUsd = usd(rows);
            return (
              <button key={d} type="button" aria-label={`${fmtDay(d)}: ${money(dayUsd)}`}
                onClick={() => rows.length && setPicked(picked === d ? null : d)}
                onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}
                className={cn("relative z-[1] flex h-full min-w-[4px] flex-1 flex-col-reverse",
                  picked && picked !== d && "opacity-35")}>
                <div className={cn("flex w-full flex-col-reverse overflow-hidden rounded-t-[3px]", dayUsd > 0 && (picked === d || hover === i) && "ring-2 ring-text")}
                  style={{ height: `${(dayUsd / top) * 100}%` }}>
                  {segs.map((g) => {
                    const v = usd(g.rows(rows));
                    return v > 0 && <div key={g.key} style={{ height: `${(v / dayUsd) * 100}%`, background: g.color }} />;
                  })}
                </div>
              </button>
            );
          })}
        </div>
        <div className="mt-1.5 flex gap-1 pl-10 text-[10.5px] text-muted-2">
          {days.map((d, i) => (
            <span key={d} className="min-w-[4px] flex-1 whitespace-nowrap text-center">{(days.length - 1 - i) % every === 0 ? fmtDay(d) : ""}</span>
          ))}
        </div>
        {hover !== null && (() => {
          const d = days[hover];
          const rows = byDay.get(d)!;
          return (
            <div className="pointer-events-none absolute top-12 z-10 whitespace-nowrap rounded-lg border border-border-strong bg-surface-3 px-2.5 py-2 text-xs text-text"
              style={{ left: `clamp(8px, calc(${((hover + 0.5) / days.length) * 100}% - 110px), calc(100% - 300px))` }}>
              <div><b>{fmtDay(d)}</b> · {money(usd(rows))}</div>
              {segs.map((g) => [g, usd(g.rows(rows))] as const).filter(([, v]) => v > 0).map(([g, v]) => (
                <div key={g.key} className="flex items-center gap-1.5">
                  <i className="h-2 w-2 rounded-sm" style={{ background: g.color }} />
                  <span className={g.key.includes("/") ? "font-mono" : ""}>{g.name}</span>
                  <span className="ml-auto pl-3">{money(v)}</span>
                </div>
              ))}
              <div className="mt-0.5 text-muted">{rows.length ? `${sum(rows, "calls")} calls · click to filter` : "No calls logged"}</div>
            </div>
          );
        })()}
        {first && first > days[0] && (
          <p className="mt-2 text-xs text-muted">Call logging began on {fmtDay(first)}, so earlier days are empty.</p>
        )}
      </div>

      <div className="grid items-start gap-4 xl:grid-cols-[1.15fr_1fr]">
        <div className="card p-4 md:p-5">
          <div className="flex items-baseline justify-between"><h2 className="text-[15px] font-semibold text-text">By model</h2>{filter}</div>
          <table className="num mt-2.5 w-full text-[13px]">
            <thead>
              <tr className="border-b border-border text-left text-[11px] uppercase tracking-[0.04em] text-muted">
                <th className="px-2 py-1.5 font-semibold">Model</th>
                <th className="px-2 py-1.5 text-right font-semibold">Calls</th>
                <th className="px-2 py-1.5 text-right font-semibold">Tokens in</th>
                <th className="px-2 py-1.5 text-right font-semibold">Tokens out</th>
                <th className="px-2 py-1.5 text-right font-semibold">$ / M in · out</th>
                <th className="px-2 py-1.5 text-right font-semibold">Cost</th>
              </tr>
            </thead>
            <tbody>
              {models.map((g) => {
                const price = data.prices[g.k];
                return (
                  <tr key={g.k} className="border-b border-border/60">
                    <td className="px-2 py-2"><span className="font-mono text-xs">{g.k}</span><Chip p={g.provider} /></td>
                    <td className="px-2 py-2 text-right">{fly(g.provider) ? "—" : g.calls}</td>
                    <td className="px-2 py-2 text-right">{fly(g.provider) ? "—" : big(g.tin)}</td>
                    <td className="px-2 py-2 text-right">{fly(g.provider) ? "—" : big(g.tout)}</td>
                    <td className="px-2 py-2 text-right text-muted">
                      {fly(g.provider) ? `$${data.fly_usd_month.toFixed(2)} / month` : price ? `${price[0]} · ${price[1]}` : "no price"}
                    </td>
                    <td className="px-2 py-2 text-right font-bold">{g.usd === null ? "—" : money(g.usd)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {models.length === 0 && <p className="py-4 text-sm text-muted">No model calls logged in this range.</p>}
        </div>

        <div className="card p-4 md:p-5">
          <div className="flex items-baseline justify-between"><h2 className="text-[15px] font-semibold text-text">By agent</h2>{filter}</div>
          <table className="num mt-2.5 w-full text-[13px]">
            <thead>
              <tr className="border-b border-border text-left text-[11px] uppercase tracking-[0.04em] text-muted">
                <th className="px-2 py-1.5 font-semibold">Agent</th>
                <th className="px-2 py-1.5 text-right font-semibold">Calls</th>
                <th className="px-2 py-1.5 text-right font-semibold">Cost</th>
                <th className="px-2 py-1.5 font-semibold">Share</th>
              </tr>
            </thead>
            <tbody>
              {agents.map((g) => (
                <tr key={g.k} className="border-b border-border/60">
                  <td className="px-2 py-2">
                    <span className="font-mono text-xs">{g.k}</span>
                    {g.k === "web_search" && <span className="ml-1.5 text-[11px] text-muted">(shared by every searching agent)</span>}
                    {fly(g.provider) && <span className="ml-1.5 text-[11px] text-muted">(machine + volume, list price)</span>}
                  </td>
                  <td className="px-2 py-2 text-right">{fly(g.provider) ? "—" : g.calls}</td>
                  <td className="px-2 py-2 text-right font-bold">{g.usd === null ? "—" : money(g.usd)}</td>
                  <td className="px-2 py-2">
                    {g.usd !== null && total > 0 && (
                      <span className="inline-flex items-center gap-1.5 text-muted">
                        <i className="h-1.5 rounded-full bg-accent" style={{ width: `${Math.max(2, (g.usd / (agents[0].usd || 1)) * 90)}px` }} />
                        {Math.round((g.usd / total) * 100)}%
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {agents.length === 0 && <p className="py-4 text-sm text-muted">No model calls logged in this range.</p>}
        </div>
      </div>

      <p className="text-xs leading-relaxed text-muted">
        <b className="text-text-2">How it&apos;s counted.</b> Tokens come from each call&apos;s log row; prices are list prices as of{" "}
        {fmtDay(data.prices_as_of)}, {data.prices_as_of.slice(0, 4)}, kept in one table in the code (src/castelino/costs.py). Each OpenAI web
        search also adds an assumed <b className="text-text-2">${data.search_fee.toFixed(2)} call fee</b>. Cached-input discounts aren&apos;t
        counted, so the real bill can be slightly lower. <b className="text-text-2">Fly.io</b> has no billing API, so its line is the
        list price of the server in fly.toml (shared-cpu-2x, 2 GB, plus the 3 GB volume) at ${data.fly_usd_month.toFixed(2)} a month
        from Oct 13, when the free trial ended; bandwidth isn&apos;t counted.{" "}
        <span className="text-warning">
          Not priced: {unpriced.length ? unpriced.map((g) => `${g.k} (${g.calls} calls)`).join(", ") : "none"}.
        </span>{" "}
        A model with no price shows its tokens here with &ldquo;—&rdquo; instead of a made-up $0.
      </p>
    </div>
  );
}
