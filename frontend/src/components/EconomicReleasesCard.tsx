import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { DailyRecord, ReleaseRow } from "@/api/endpoints";
import { useLatestUpdate } from "@/hooks/useUpdate";
import { cn } from "@/lib/cn";

// the shared API client maps 404 to [] (see api/client.ts), so "no briefing" arrives as an array
export const isRecord = (r: unknown): r is DailyRecord =>
  !!r && !Array.isArray(r) && typeof (r as DailyRecord).date === "string";

const INFLATION = /^(Core )?(CPI|PCE) /;
// m/m inflation moves are small (e.g. 0.29%), so they get two decimals
const dp = (name: string) => (name.endsWith("m/m") ? 2 : 1);
const tone = (x: number | null) => (x == null || x === 0 ? "" : x > 0 ? "text-success" : "text-danger");

// round first so a -0.03 change shows as a neutral 0.0, not a red "-0.0"
function Change({ value, decimals }: { value: number | null; decimals: number }) {
  const v = value == null ? null : Number(value.toFixed(decimals)) || 0;
  return (
    <td className={cn("text-right px-3 num", tone(v))}>
      {v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(decimals)}`}
    </td>
  );
}

function Rows({ label, rows }: { label: string; rows: ReleaseRow[] }) {
  if (rows.length === 0) return null;
  return (
    <>
      <tr className="border-t border-border bg-surface-2/60">
        <td colSpan={5} className="px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-muted">{label}</td>
      </tr>
      {rows.map((r) => (
        <tr key={r.series + r.name} className="border-t border-border">
          <td className="px-3 py-2">{r.name}</td>
          <td className="px-3 font-mono text-xs text-muted">{r.series}</td>
          <td className="text-right px-3 num">{r.latest.toFixed(dp(r.name))}</td>
          <td className="text-right px-3 num">{r.prior == null ? "—" : r.prior.toFixed(dp(r.name))}</td>
          <Change value={r.change} decimals={dp(r.name)} />
        </tr>
      ))}
    </>
  );
}

export function EconomicReleasesTable({ releases }: { releases: ReleaseRow[] }) {
  return (
    <table className="w-full text-sm">
      <thead className="text-xs uppercase text-muted bg-surface-2">
        <tr>
          <th className="text-left px-3 py-2">Series</th><th className="text-left px-3">FRED id</th>
          <th className="text-right px-3">Latest</th><th className="text-right px-3">Prior</th><th className="text-right px-3">Change</th>
        </tr>
      </thead>
      <tbody>
        <Rows label="Inflation" rows={releases.filter((r) => INFLATION.test(r.name))} />
        <Rows label="Labour & activity" rows={releases.filter((r) => !INFLATION.test(r.name))} />
        {releases.length === 0 && (
          <tr><td colSpan={5} className="px-3 py-3 text-center text-muted">No releases today.</td></tr>
        )}
      </tbody>
    </table>
  );
}

/** Self-fetching card for pages outside Daily Update (Macro & Signals, Models). */
export function EconomicReleasesCard({ subtitle }: { subtitle?: string }) {
  const { data } = useLatestUpdate(undefined);
  const rec = isRecord(data) ? data : undefined;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Economic releases</CardTitle>
        <span className="text-xs text-muted">
          {subtitle ?? "from the latest Daily Update"}{rec ? ` · ${rec.date}` : ""}
        </span>
      </CardHeader>
      <CardContent className="p-0">
        {rec ? (
          <EconomicReleasesTable releases={rec.snapshot.releases} />
        ) : (
          <div className="py-8 text-center text-sm text-muted">No briefing yet. It builds on the next dashboard start.</div>
        )}
      </CardContent>
    </Card>
  );
}
