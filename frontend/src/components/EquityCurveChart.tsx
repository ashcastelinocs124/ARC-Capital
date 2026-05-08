import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { PlotlyChart } from "@/api/types";

interface DataPoint {
  date: string;
  nav: number;
}

export function EquityCurveChart({ data: chartData }: { data: PlotlyChart | undefined }) {
  // The backend returns Plotly format. Extract x/y from the first trace.
  const trace = chartData?.data?.[0];
  let points: DataPoint[] = [];

  if (trace) {
    const x = (trace as { x?: string[] }).x;
    const y = (trace as { y?: number[] }).y;
    if (Array.isArray(x) && Array.isArray(y)) {
      points = x.map((d, i) => ({ date: d, nav: y[i] }));
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Equity Curve</CardTitle>
      </CardHeader>
      <CardContent>
        {points.length === 0 ? (
          <div className="h-64 flex items-center justify-center text-sm text-muted">
            No NAV history yet.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={points}>
              <defs>
                <linearGradient id="navFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#0a0a0a" stopOpacity={0.18} />
                  <stop offset="100%" stopColor="#0a0a0a" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="date"
                stroke="#9ca3af"
                fontSize={11}
                tickLine={false}
                axisLine={false}
                minTickGap={40}
              />
              <YAxis
                stroke="#9ca3af"
                fontSize={11}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) =>
                  v >= 1_000_000 ? `$${(v / 1_000_000).toFixed(1)}M` : `$${(v / 1_000).toFixed(0)}K`
                }
              />
              <Tooltip
                contentStyle={{
                  background: "#ffffff",
                  border: "1px solid #e5e7eb",
                  borderRadius: "8px",
                  fontSize: "12px",
                  boxShadow: "0 4px 12px -2px rgb(0 0 0 / 0.08)",
                }}
                labelStyle={{ color: "#6b7280" }}
              />
              <Area
                type="monotone"
                dataKey="nav"
                stroke="#0a0a0a"
                strokeWidth={2}
                fill="url(#navFill)"
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}
