import type { Fill } from "@/api/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { fmtSignedUSD, fmtUSD, pnlColor } from "@/lib/format";

const TYPE_COLORS = {
  open: "default",
  close: "muted",
  trim: "warning",
  stop_loss: "danger",
} as const;

export function RecentFills({ fills }: { fills: Fill[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Recent Fills</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {fills.length === 0 ? (
          <div className="px-5 py-12 text-center text-sm text-muted">No fills yet.</div>
        ) : (
          <div className="divide-y divide-border">
            {fills.slice(0, 12).map((f, i) => (
              <div key={i} className="px-5 py-2.5 flex items-center gap-3 hover:bg-surface-2">
                <Badge variant={TYPE_COLORS[f.type] || "muted"}>{f.type}</Badge>
                <span className="font-mono font-semibold text-sm w-16">{f.instrument_id}</span>
                <span className="text-xs text-muted font-mono num w-24 text-right">
                  {f.quantity.toFixed(2)} @ {fmtUSD(f.fill_price)}
                </span>
                <span className={`flex-1 text-right text-xs font-mono num ${pnlColor(f.realized_pnl)}`}>
                  {f.realized_pnl !== 0 ? fmtSignedUSD(f.realized_pnl) : ""}
                </span>
                <span className="text-xs text-muted-2 shrink-0">{f.timestamp}</span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
