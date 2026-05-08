import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/cn";
import type { KpiTile } from "@/api/types";

export function KpiCard({ tile }: { tile: KpiTile }) {
  const delta = tile.delta || "";
  const isPositive = delta.startsWith("+");
  const isNegative = delta.startsWith("-");
  return (
    <Card className="hover:shadow-card-hover transition-shadow">
      <CardContent className="p-5">
        <div className="text-xs uppercase tracking-wider text-muted font-medium mb-2">
          {tile.label}
        </div>
        <div className="text-2xl font-semibold font-mono num text-text">{tile.value}</div>
        <div className="flex items-center gap-2 mt-2 text-xs">
          {delta && (
            <span
              className={cn(
                "font-semibold px-1.5 py-0.5 rounded",
                isPositive && "text-success bg-success-soft",
                isNegative && "text-danger bg-danger-soft",
                !isPositive && !isNegative && "text-muted bg-surface-3",
              )}
            >
              {delta}
            </span>
          )}
          {tile.subvalue && <span className="text-muted">{tile.subvalue}</span>}
        </div>
      </CardContent>
    </Card>
  );
}
