import type { Position } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/cn";
import { fmtPct, fmtSignedPct, fmtSignedUSD, fmtUSD, pnlColor } from "@/lib/format";

export function PositionsTable({ positions }: { positions: Position[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Open Positions · {positions.length}</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {positions.length === 0 ? (
          <div className="px-5 py-12 text-center text-sm text-muted">No open positions.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-xs uppercase tracking-wide text-muted bg-surface-2">
                <tr>
                  <Th align="left">Instrument</Th>
                  <Th>Side</Th>
                  <Th>Class</Th>
                  <Th align="right">Qty</Th>
                  <Th align="right">Entry</Th>
                  <Th align="right">Mark</Th>
                  <Th align="right">Mkt Value</Th>
                  <Th align="right">% NAV</Th>
                  <Th align="right">Unrealized</Th>
                  <Th align="right">P&L %</Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {positions.map((p) => (
                  <tr key={p.instrument_id} className="hover:bg-surface-2 transition-colors">
                    <Td align="left">
                      <span className="font-mono font-semibold">{p.instrument_id}</span>
                    </Td>
                    <Td>
                      <Badge variant={p.side === "LONG" ? "success" : "danger"}>{p.side}</Badge>
                    </Td>
                    <Td>
                      <span className="text-muted text-xs uppercase">{p.asset_class}</span>
                    </Td>
                    <Td align="right" mono>
                      {p.quantity.toFixed(2)}
                    </Td>
                    <Td align="right" mono>
                      {fmtUSD(p.entry_price)}
                    </Td>
                    <Td align="right" mono>
                      {fmtUSD(p.mark_price)}
                    </Td>
                    <Td align="right" mono>
                      {fmtUSD(p.market_value)}
                    </Td>
                    <Td align="right" mono>
                      {fmtPct(p.pct_nav / 100)}
                    </Td>
                    <Td align="right" mono className={pnlColor(p.unrealized_pnl)}>
                      {fmtSignedUSD(p.unrealized_pnl)}
                    </Td>
                    <Td align="right" mono className={pnlColor(p.unrealized_pct)}>
                      {fmtSignedPct(p.unrealized_pct / 100)}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Th({ children, align = "center" }: { children: React.ReactNode; align?: "left" | "right" | "center" }) {
  return (
    <th className={cn("px-4 py-2.5 font-medium", align === "left" ? "text-left" : align === "right" ? "text-right" : "text-center")}>
      {children}
    </th>
  );
}

function Td({
  children,
  align = "center",
  mono = false,
  className,
}: {
  children: React.ReactNode;
  align?: "left" | "right" | "center";
  mono?: boolean;
  className?: string;
}) {
  return (
    <td
      className={cn(
        "px-4 py-2.5",
        align === "left" ? "text-left" : align === "right" ? "text-right" : "text-center",
        mono && "font-mono num",
        className,
      )}
    >
      {children}
    </td>
  );
}
