import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { DailyRecord } from "@/api/endpoints";
import { ACTIVE_STAGES, useLatestUpdate, useUpdateByDate, useUpdateHistory, useUpdateStatus } from "@/hooks/useUpdate";
import { cn } from "@/lib/cn";

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

function Briefing({ rec }: { rec: DailyRecord }) {
  const { snapshot: s, update: u } = rec;
  const reads = Object.fromEntries(u.sector_reads.map((r) => [r.sector.toUpperCase(), r.text]));
  return (
    <>
      <Card className="mb-4"><CardContent className="pt-5">
        <div className="text-xl font-semibold mb-1.5">{u.headline}</div>
        <div className="text-sm text-muted">{u.economy}</div>
      </CardContent></Card>

      <div className="grid lg:grid-cols-2 gap-4 mb-4">
        <Card>
          <CardHeader><CardTitle>Prediction changes</CardTitle></CardHeader>
          <CardContent>
            {Object.entries(s.prediction).map(([m, p]) => (
              <div key={m} className="flex items-center gap-3 py-2.5 border-t border-border first:border-0">
                <div className="w-28 text-sm capitalize">{m} ↑</div>
                <span className="font-mono text-lg font-semibold">{prob(p.old)}</span>
                <span className="text-muted-2">→</span>
                <span className="font-mono text-lg font-semibold">{prob(p.new)}</span>
                <span className={cn("text-xs font-semibold px-2 py-0.5 rounded-full",
                  p.gate === "promoted" ? "bg-success-soft text-success" : "bg-warning-soft text-warning")}>{p.gate}</span>
              </div>
            ))}
            {s.model_note && <div className="text-xs text-warning mt-2">{s.model_note}</div>}
            <div className="text-xs text-muted mt-2">{u.predictions_changed}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Economic releases</CardTitle></CardHeader>
          <CardContent className="p-0">
            <table className="w-full text-sm">
              <thead className="text-xs uppercase text-muted bg-surface-2">
                <tr><th className="text-left px-3 py-2">Series</th><th className="text-right px-3">Latest</th><th className="text-right px-3">Prior</th><th className="text-right px-3">Change</th></tr>
              </thead>
              <tbody>
                {s.releases.map((r) => (
                  <tr key={r.series} className="border-t border-border">
                    <td className="px-3 py-2">{r.name}</td>
                    <td className="text-right px-3 num">{r.latest.toFixed(1)}</td>
                    <td className="text-right px-3 num">{r.prior == null ? "—" : r.prior.toFixed(1)}</td>
                    <td className={cn("text-right px-3 num", tone(r.change))}>{r.change == null ? "—" : `${r.change > 0 ? "+" : ""}${r.change.toFixed(1)}`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      </div>

      <Card className="mb-4">
        <CardHeader><CardTitle>Across asset classes</CardTitle></CardHeader>
        <CardContent className="text-sm text-muted">{u.asset_classes}</CardContent>
      </Card>

      <Card className="mb-4">
        <CardHeader><CardTitle>Sector trend</CardTitle><span className="text-xs text-muted">rel = vs SPY</span></CardHeader>
        <CardContent className="p-0 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase text-muted bg-surface-2">
              <tr>
                <th className="text-left px-3 py-2">Sector</th><th className="text-right px-3">1w</th><th className="text-right px-3">1m</th>
                <th className="text-right px-3">rel 1m</th><th className="text-left px-3">Short trend</th><th className="text-right px-3">12m</th>
                <th className="text-left px-3">Long trend</th><th className="text-left px-3">Read</th>
              </tr>
            </thead>
            <tbody>
              {s.sectors.map((t) => (
                <tr key={t.sector} className="border-t border-border">
                  <td className="px-3 py-2 font-medium">{t.sector}</td>
                  <td className={cn("text-right px-3 num", tone(t.r1w))}>{pct(t.r1w)}</td>
                  <td className={cn("text-right px-3 num", tone(t.r1m))}>{pct(t.r1m)}</td>
                  <td className={cn("text-right px-3 num", tone(t.rel1m))}>{pct(t.rel1m, "pp")}</td>
                  <td className="px-3">{t.short_label}</td>
                  <td className={cn("text-right px-3 num", tone(t.r12m))}>{pct(t.r12m)}</td>
                  <td className="px-3">{t.long_label}</td>
                  <td className="px-3 text-xs text-muted">{reads[t.sector.toUpperCase()] ?? ""}</td>
                </tr>
              ))}
              {s.sectors.length === 0 && <tr><td colSpan={8} className="px-3 py-3 text-center text-muted">No sector data today.</td></tr>}
            </tbody>
          </table>
        </CardContent>
      </Card>

      {s.data_gaps.length > 0 && (
        <Card>
          <CardHeader><CardTitle>Data gaps <span className="ml-1 text-xs text-warning">{s.data_gaps.length}</span></CardTitle></CardHeader>
          <CardContent className="text-xs text-muted">{s.data_gaps.join(" · ")}</CardContent>
        </Card>
      )}
    </>
  );
}

export default function UpdatesPage() {
  const { data: status } = useUpdateStatus();
  const stage = status?.stage;
  const { data: latest, isError } = useLatestUpdate(stage);
  const { data: history } = useUpdateHistory(stage);
  const [picked, setPicked] = useState<string | null>(null);
  const { data: other } = useUpdateByDate(picked && picked !== latest?.date ? picked : null);
  const rec = picked && picked !== latest?.date ? other : latest;
  const running = !!stage && (ACTIVE_STAGES.has(stage) || stage === "failed");

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="flex items-baseline justify-between mb-3">
        <div className="text-xs text-muted">{rec ? `Briefing for ${rec.date} · generated ${rec.generated_at.replace("T", " ").slice(0, 16)}` : "Daily Update"}</div>
        <div className="flex gap-1.5 flex-wrap">
          {(history?.dates ?? []).slice(0, 8).map((d) => (
            <button key={d} onClick={() => setPicked(d)}
              className={cn("font-mono text-xs px-2 py-0.5 rounded-md border",
                d === (rec?.date ?? "") ? "bg-accent-soft text-accent border-accent" : "bg-white border-border")}>{d.slice(5)}</button>
          ))}
        </div>
      </div>
      {running && <Banner stage={stage as string} error={status?.error} />}
      {rec ? <Briefing rec={rec} /> : !running && isError && (
        <Card><CardContent className="py-12 text-center text-sm text-muted">
          No briefing yet. It builds automatically when the dashboard starts.
        </CardContent></Card>
      )}
    </div>
  );
}
