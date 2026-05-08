import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { usePositions } from "@/hooks/usePortfolio";
import { useWarnings } from "@/hooks/useRisk";
import { fmtPct, fmtUSD } from "@/lib/format";

// Monochrome ramp — black through grays
const COLORS = ["#0a0a0a", "#404040", "#737373", "#a3a3a3", "#d4d4d4", "#e5e5e5", "#f0f0f0"];

export default function RiskPage() {
  const { data: positions = [] } = usePositions();
  const { data: warnings = [] } = useWarnings();

  // Build exposure by asset class from positions
  const byClass = positions.reduce<Record<string, number>>((acc, p) => {
    acc[p.asset_class] = (acc[p.asset_class] || 0) + Math.abs(p.market_value);
    return acc;
  }, {});
  const classData = Object.entries(byClass).map(([name, value]) => ({ name, value }));

  // Build exposure by instrument
  const instrumentData = [...positions]
    .sort((a, b) => Math.abs(b.market_value) - Math.abs(a.market_value))
    .slice(0, 10)
    .map((p) => ({ name: p.instrument_id, value: Math.abs(p.market_value), pct: p.pct_nav }));

  return (
    <div className="p-8 space-y-6 max-w-7xl mx-auto">
      <div className="grid lg:grid-cols-2 gap-6">
        {/* Exposure by class — donut */}
        <Card>
          <CardHeader>
            <CardTitle>Exposure by Asset Class</CardTitle>
          </CardHeader>
          <CardContent>
            {classData.length === 0 ? (
              <div className="h-64 flex items-center justify-center text-sm text-muted">
                No positions.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={260}>
                <PieChart>
                  <Pie
                    data={classData}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={95}
                    paddingAngle={2}
                  >
                    {classData.map((_, i) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]} stroke="#ffffff" strokeWidth={2} />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(v: number) => fmtUSD(v)}
                    contentStyle={{
                      background: "#ffffff",
                      border: "1px solid #e5e7eb",
                      borderRadius: "8px",
                      fontSize: "12px",
                      boxShadow: "0 4px 12px -2px rgb(0 0 0 / 0.08)",
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            )}
            <div className="grid grid-cols-2 gap-2 mt-3">
              {classData.map((d, i) => (
                <div key={d.name} className="flex items-center gap-2 text-xs">
                  <div className="w-3 h-3 rounded-sm" style={{ background: COLORS[i % COLORS.length] }} />
                  <span className="text-muted uppercase">{d.name}</span>
                  <span className="ml-auto font-mono num">{fmtUSD(d.value, { compact: true })}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Top 10 instruments */}
        <Card>
          <CardHeader>
            <CardTitle>Top 10 Instruments by Exposure</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {instrumentData.length === 0 ? (
              <div className="px-5 py-12 text-center text-sm text-muted">No positions.</div>
            ) : (
              <div className="divide-y divide-border">
                {instrumentData.map((d) => (
                  <div key={d.name} className="px-5 py-2.5 flex items-center gap-3">
                    <span className="font-mono font-semibold text-sm w-16">{d.name}</span>
                    <div className="flex-1 h-1.5 bg-surface-2 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-accent"
                        style={{ width: `${(d.value / instrumentData[0].value) * 100}%` }}
                      />
                    </div>
                    <span className="font-mono num text-xs text-muted w-20 text-right">
                      {fmtUSD(d.value, { compact: true })}
                    </span>
                    <span className="font-mono num text-xs text-muted-2 w-12 text-right">
                      {fmtPct(d.pct / 100)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Warnings */}
      <Card>
        <CardHeader>
          <CardTitle>Principle Warnings</CardTitle>
          <Badge variant={warnings.length > 0 ? "warning" : "success"}>
            {warnings.length} {warnings.length === 1 ? "warning" : "warnings"}
          </Badge>
        </CardHeader>
        <CardContent>
          {warnings.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted">
              No active principle warnings. ✅
            </div>
          ) : (
            <pre className="text-xs text-muted bg-surface-2 p-3 rounded-md overflow-auto">
              {JSON.stringify(warnings, null, 2)}
            </pre>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
