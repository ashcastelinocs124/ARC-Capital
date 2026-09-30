import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { DailyRecord } from "@/api/endpoints";
import { ACTIVE_STAGES, useLatestUpdate, useUpdateByDate, useUpdateHistory, useUpdateStatus } from "@/hooks/useUpdate";
import { cn } from "@/lib/cn";
import { EconomicReleasesTable, isRecord } from "@/components/EconomicReleasesCard";

const STEPS: [string, string][] = [
  ["checking", "checking for new data"], ["refitting", "refitting models"], ["gating", "gate: challenger vs champion"],
  ["collecting", "collecting market data"], ["writing", "writing briefing"], ["guarding", "checking numbers"],
];

const pct = (x: number | null | undefined, unit = "%") =>
  x == null ? "—" : `${x > 0 ? "+" : ""}${x.toFixed(1)}${unit}`;
const tone = (x: number | null | undefined) => (x == null || x === 0 ? "" : x > 0 ? "text-success" : "text-danger");
const prob = (x: number | null | undefined) => (x == null ? "—" : `${Math.round(x * 100)}%`);

function Banner({ stage, error }: { stage: string; error?: string | null }) {
  if (stage === "failed") {
    return (
      <div className="rounded-xl border border-danger bg-danger-soft px-5 py-4 mb-4 text-sm">
        <b>Today's briefing failed:</b> {error || "unknown error"}. It will retry the next time the dashboard starts.
      </div>
    );
  }
  if (!ACTIVE_STAGES.has(stage)) return null;
  const at = STEPS.findIndex(([s]) => s === stage);
  return (
    <div className="rounded-xl border border-warning bg-warning-soft px-5 py-4 mb-4">
      <div className="text-sm font-semibold">Building today's briefing… <span className="text-xs font-normal text-muted">this takes a minute or two and updates itself</span></div>
      <div className="flex flex-wrap gap-1.5 mt-2.5">
        {STEPS.map(([s, label], i) => (
          <span key={s} className={cn("text-xs px-2.5 py-1 rounded-full border",
            i < at ? "bg-accent-soft text-accent border-accent/30" : i === at ? "bg-white font-semibold text-warning border-warning" : "bg-surface-2 text-muted border-border")}>
            {i === at ? "● " : ""}{label}
          </span>
        ))}
      </div>
    </div>
  );
}

const CLASS_LABELS: Record<string, string> = {
  equities: "Equities", rates_credit: "Rates & credit", commodities: "Commodities", fx: "FX",
};
// ponytail: yields (FRED DGS*) are reported in bp by the collector; everything else in %
const unitFor = (id: string) => (id.startsWith("DGS") ? "bp" : "%");
const fmt = (x: number | null | undefined, unit: string) =>
  x == null ? "—" : `${x > 0 ? "+" : ""}${unit === "bp" ? x.toFixed(0) : x.toFixed(1)}${unit}`;

function AssetClassTable({ name, rows }: { name: string; rows: Record<string, Record<string, number | null>> }) {
  const ids = Object.keys(rows);
  return (
    <Card>
      <CardHeader><CardTitle>{CLASS_LABELS[name] ?? name}</CardTitle></CardHeader>
      <CardContent className="p-0">
        <table className="w-full text-sm">
          <thead className="text-xs uppercase text-muted bg-surface-2">
            <tr><th className="text-left px-3 py-2"></th><th className="text-right px-3">1d</th><th className="text-right px-3">1w</th><th className="text-right px-3">1m</th></tr>
          </thead>
          <tbody>
            {ids.map((id) => (
              <tr key={id} className="border-t border-border">
                <td className="px-3 py-1.5 font-mono text-xs">{id}</td>
                {(["1d", "1w", "1m"] as const).map((w) => (
                  <td key={w} className={cn("text-right px-3 num", tone(rows[id][w]))}>{fmt(rows[id][w], unitFor(id))}</td>
                ))}
              </tr>
            ))}
            {ids.length === 0 && <tr><td colSpan={4} className="px-3 py-3 text-center text-muted">No data</td></tr>}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}

function Briefing({ rec }: { rec: DailyRecord }) {
  const { snapshot: s, update: u } = rec;
  const reads = Object.fromEntries(u.sector_reads.map((r) => [r.sector.toUpperCase(), r.text]));
  const classes = Object.entries(s.asset_returns ?? {});
  const themes = [
    ...(u.themes_touched ?? []).map((t) => ({ ...t, tag: "updated" })),
    ...(u.new_themes ?? []).map((t) => ({ ...t, tag: "new" })),
  ];
  return (
    <div className="space-y-4">
      <Card><CardContent className="pt-5">
        <div className="text-xl font-semibold mb-1.5">{u.headline}</div>
        <div className="text-sm text-muted">{u.economy}</div>
      </CardContent></Card>

      <div className="grid lg:grid-cols-3 gap-4 items-start">
        <div className="space-y-4">
        <Card>
          <CardHeader><CardTitle>Prediction changes</CardTitle></CardHeader>
          <CardContent>
            {Object.entries(s.prediction).map(([m, p]) => (
              <div key={m} className="flex items-center gap-3 py-2.5 border-t border-border first:border-0">
                <div className="w-24 text-sm capitalize">{m} ↑</div>
                <span className="font-mono text-lg font-semibold">{prob(p.old)}</span>
                <span className="text-muted-2">→</span>
                <span className="font-mono text-lg font-semibold">{prob(p.new)}</span>
                <span className={cn("text-xs font-semibold px-2 py-0.5 rounded-full",
                  p.gate === "promoted" ? "bg-success-soft text-success"
                    : p.gate === "kept" ? "bg-warning-soft text-warning" : "bg-surface-2 text-muted")}>{p.gate}</span>
              </div>
            ))}
            {s.model_note && <div className="text-xs text-warning mt-2">{s.model_note}</div>}
            <div className="text-xs text-muted mt-2">{u.predictions_changed}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Data gaps <span className="ml-1 text-xs text-muted">{s.data_gaps.length}</span></CardTitle></CardHeader>
          <CardContent className="text-xs text-muted">
            {s.data_gaps.length ? s.data_gaps.map((g) => <div key={g} className="py-1">{g}</div>) : "All sources returned data."}
          </CardContent>
        </Card>
        </div>
        <Card className="lg:col-span-2">
          <CardHeader><CardTitle>Economic releases</CardTitle></CardHeader>
          <CardContent className="p-0">
            <EconomicReleasesTable releases={s.releases} />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle>Across asset classes</CardTitle></CardHeader>
        <CardContent className="text-sm text-muted leading-relaxed">{u.asset_classes}</CardContent>
      </Card>

      {classes.length > 0 && (
        <div className="grid md:grid-cols-2 xl:grid-cols-4 gap-4 items-start">
          {classes.map(([name, rows]) => <AssetClassTable key={name} name={name} rows={rows} />)}
        </div>
      )}

      <Card>
        <CardHeader><CardTitle>Sector trend</CardTitle><span className="text-xs text-muted">short-term 1w/1m · long-term 3m/6m/12m · rel = vs SPY</span></CardHeader>
        <CardContent className="p-0 overflow-x-auto">
          <table className="w-full text-base">
            <thead className="text-sm uppercase text-muted bg-surface-2">
              <tr>
                <th className="text-left px-3 py-2">Sector</th><th className="text-right px-3">1w</th><th className="text-right px-3">1m</th>
                <th className="text-right px-3">rel 1m</th><th className="text-left px-3">Short trend</th>
                <th className="text-right px-3">3m</th><th className="text-right px-3">6m</th><th className="text-right px-3">12m</th>
                <th className="text-right px-3">rel 12m</th><th className="text-left px-3">Long trend</th><th className="text-left px-3">Read</th>
              </tr>
            </thead>
            <tbody>
              {s.sectors.map((t) => (
                <tr key={t.sector} className="border-t border-border">
                  <td className="px-3 py-3 font-medium">{t.sector}</td>
                  <td className={cn("text-right px-3 num", tone(t.r1w))}>{pct(t.r1w)}</td>
                  <td className={cn("text-right px-3 num", tone(t.r1m))}>{pct(t.r1m)}</td>
                  <td className={cn("text-right px-3 num", tone(t.rel1m))}>{pct(t.rel1m, "pp")}</td>
                  <td className="px-3 whitespace-nowrap">{t.short_label}</td>
                  <td className={cn("text-right px-3 num", tone(t.r3m))}>{pct(t.r3m)}</td>
                  <td className={cn("text-right px-3 num", tone(t.r6m))}>{pct(t.r6m)}</td>
                  <td className={cn("text-right px-3 num", tone(t.r12m))}>{pct(t.r12m)}</td>
                  <td className={cn("text-right px-3 num", tone(t.rel12m))}>{pct(t.rel12m, "pp")}</td>
                  <td className="px-3 whitespace-nowrap">{t.long_label}</td>
                  <td className="px-3 py-2 text-sm text-muted">{reads[t.sector.toUpperCase()] ?? ""}</td>
                </tr>
              ))}
              {s.sectors.length === 0 && <tr><td colSpan={11} className="px-3 py-3 text-center text-muted">No sector data today.</td></tr>}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <div>
        <Card>
          <CardHeader><CardTitle>Themes</CardTitle><span className="text-xs text-muted">written to the agent's memory</span></CardHeader>
          <CardContent>
            {themes.map((t) => (
              <div key={t.tag + t.title} className="py-2.5 border-t border-border first:border-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{t.title}</span>
                  <span className={cn("text-xs font-semibold px-2 py-0.5 rounded-full",
                    t.tag === "new" ? "bg-accent-soft text-accent" : "bg-surface-2 text-muted")}>{t.tag}</span>
                </div>
                <div className="text-xs text-muted mt-1">{t.text}</div>
              </div>
            ))}
            {themes.length === 0 && <div className="text-sm text-muted">No themes touched today.</div>}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export default function UpdatesPage() {
  const { data: status } = useUpdateStatus();
  const stage = status?.stage;
  // the shared API client maps 404 to [] (see api/client.ts), so "no briefing" arrives as an array
  const { data: latestRaw } = useLatestUpdate(stage);
  const latest = isRecord(latestRaw) ? latestRaw : undefined;
  const { data: history } = useUpdateHistory(stage);
  const [picked, setPicked] = useState<string | null>(null);
  const { data: other } = useUpdateByDate(picked && picked !== latest?.date ? picked : null);
  const picked_ = picked && picked !== latest?.date ? other : latest;
  const rec = isRecord(picked_) ? picked_ : undefined;
  const running = !!stage && (ACTIVE_STAGES.has(stage) || stage === "failed");

  return (
    <div className="p-8">
      <div className="flex items-baseline justify-between mb-3">
        <div className="text-xs text-muted">{rec ? `Briefing for ${rec.date} · generated ${rec.generated_at.replace("T", " ").slice(0, 16)}` : "Daily Update"}</div>
        <div className="flex gap-1.5 flex-wrap">
          {(Array.isArray(history?.dates) ? history!.dates : []).slice(0, 8).map((d) => (
            <button key={d} onClick={() => setPicked(d)}
              className={cn("font-mono text-xs px-2 py-0.5 rounded-md border",
                d === (rec?.date ?? "") ? "bg-accent-soft text-accent border-accent" : "bg-white border-border")}>{d.slice(5)}</button>
          ))}
        </div>
      </div>
      {running && <Banner stage={stage as string} error={status?.error} />}
      {rec ? <Briefing rec={rec} /> : !running && (
        <Card><CardContent className="py-12 text-center text-sm text-muted">
          No briefing yet. It builds automatically when the dashboard starts.
        </CardContent></Card>
      )}
    </div>
  );
}
