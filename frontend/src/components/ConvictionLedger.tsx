import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/cn";

interface Props {
  growthBullish?: number;
  growthBearish?: number;
  inflationBullish?: number;
  inflationBearish?: number;
  fireThreshold?: number;
}

export function ConvictionLedger({
  growthBullish = 0,
  growthBearish = 0,
  inflationBullish = 0,
  inflationBearish = 0,
  fireThreshold = 2.5,
}: Props) {
  const max = Math.max(growthBullish, growthBearish, inflationBullish, inflationBearish, fireThreshold);

  const rows: Array<{ label: string; value: number; color: string }> = [
    { label: "Growth ↑", value: growthBullish, color: "bg-success" },
    { label: "Growth ↓", value: growthBearish, color: "bg-danger" },
    { label: "Inflation ↑", value: inflationBullish, color: "bg-warning" },
    { label: "Inflation ↓", value: inflationBearish, color: "bg-info" },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Conviction Ledger</CardTitle>
        <div className="text-xs text-muted-2 mt-0.5">Decayed signal sums (12h half-life)</div>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {rows.map((r) => {
            const pct = max > 0 ? (r.value / max) * 100 : 0;
            const pastThreshold = r.value >= fireThreshold;
            return (
              <div key={r.label}>
                <div className="flex justify-between items-baseline text-xs mb-1">
                  <span className="text-muted">{r.label}</span>
                  <span className={cn("font-mono num font-semibold", pastThreshold ? "text-accent" : "text-text")}>
                    {r.value.toFixed(2)}
                  </span>
                </div>
                <div className="h-2 bg-surface-2 rounded-full overflow-hidden">
                  <div
                    className={cn("h-full transition-all duration-300", r.color, pastThreshold && "animate-pulse-slow")}
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
        <div className="mt-4 pt-3 border-t border-border flex justify-between items-center text-xs">
          <span className="text-muted">Fire threshold</span>
          <span className="font-mono num text-muted-2">{fireThreshold}</span>
        </div>
      </CardContent>
    </Card>
  );
}
