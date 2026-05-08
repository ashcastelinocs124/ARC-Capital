import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/cn";

interface QuadrantCell {
  label: string;
  growth: "up" | "down";
  inflation: "up" | "down";
  blurb: string;
  instruments: string[];
}

const QUADRANTS: QuadrantCell[] = [
  {
    label: "Goldilocks",
    growth: "up",
    inflation: "down",
    blurb: "Growth + cooling inflation",
    instruments: ["XLK", "QQQ", "SPY"],
  },
  {
    label: "Reflation",
    growth: "up",
    inflation: "up",
    blurb: "Risk-on + real assets",
    instruments: ["XLE", "XLI", "GLD", "IBIT"],
  },
  {
    label: "Disinflation",
    growth: "down",
    inflation: "down",
    blurb: "Long duration + defensives",
    instruments: ["TLT", "IEF", "LQD", "XLV"],
  },
  {
    label: "Stagflation",
    growth: "down",
    inflation: "up",
    blurb: "Real assets + healthcare",
    instruments: ["XLE", "GLD", "USO", "XLV"],
  },
];

interface Props {
  growthUp?: boolean | null;
  inflationUp?: boolean | null;
  growthProb?: number | null;
  inflationProb?: number | null;
}

export function RegimeQuadrant({ growthUp, inflationUp, growthProb, inflationProb }: Props) {
  const noData = growthUp == null || inflationUp == null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Regime Nowcast</CardTitle>
        <div className="text-xs text-muted-2 mt-0.5">Growth × Inflation (XGBoost)</div>
      </CardHeader>
      <CardContent>
        {noData ? (
          <div className="h-48 flex items-center justify-center text-sm text-muted">
            <div className="text-center">
              <div>No regime forecast loaded.</div>
              <div className="text-xs mt-1 font-mono">Run: castelino forecast-regime</div>
            </div>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-2 mb-3 relative">
              {/* Y-axis label */}
              <div className="absolute -left-6 top-1/2 -translate-y-1/2 -rotate-90 text-xs text-muted-2 uppercase tracking-wider">
                Growth
              </div>
              {QUADRANTS.map((q) => {
                const active = q.growth === (growthUp ? "up" : "down") && q.inflation === (inflationUp ? "up" : "down");
                return (
                  <div
                    key={q.label}
                    className={cn(
                      "p-3 rounded-lg border transition-colors",
                      active
                        ? "bg-accent-soft border-accent"
                        : "bg-surface-2 border-border opacity-60",
                    )}
                  >
                    <div className={cn("text-sm font-semibold mb-1", active ? "text-accent" : "text-muted")}>
                      {q.label}
                    </div>
                    <div className="text-xs text-muted leading-relaxed mb-2">{q.blurb}</div>
                    <div className="flex flex-wrap gap-1">
                      {q.instruments.map((i) => (
                        <span key={i} className="text-xs font-mono px-1.5 py-0.5 rounded bg-surface text-muted-2">
                          {i}
                        </span>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="text-center text-xs text-muted-2 uppercase tracking-wider mb-3">
              Inflation →
            </div>

            <div className="flex justify-around text-xs">
              <ProbabilityIndicator label="Growth↑" prob={growthProb ?? null} positive={!!growthUp} />
              <ProbabilityIndicator label="Inflation↑" prob={inflationProb ?? null} positive={!!inflationUp} />
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function ProbabilityIndicator({ label, prob, positive }: { label: string; prob: number | null; positive: boolean }) {
  if (prob == null) return null;
  return (
    <div className="text-center">
      <div className="text-xs text-muted mb-1">{label}</div>
      <div className={cn("font-mono num text-sm font-semibold", positive ? "text-success" : "text-danger")}>
        P = {(prob * 100).toFixed(1)}%
      </div>
    </div>
  );
}
