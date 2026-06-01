import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type ChartPoint = { x: string; y: number };
type ChartSeries = { name: string; points: ChartPoint[] };
export type ResolvedChart = {
  type: "price_history" | "yield_curve" | "econ_indicator" | "comparison";
  title: string;
  rationale?: string;
  series: ChartSeries[];
  y_label?: string;
  source?: string;
};

const COLORS = ["#2563eb", "#16a34a", "#dc2626", "#9333ea", "#ea580c"];

// Merge N series into recharts row format: [{ x, <seriesName>: y, ... }]
function toRows(series: ChartSeries[]): Record<string, string | number>[] {
  const byX = new Map<string, Record<string, string | number>>();
  series.forEach((s) => {
    s.points.forEach((p) => {
      const row = byX.get(p.x) ?? { x: p.x };
      row[s.name] = p.y;
      byX.set(p.x, row);
    });
  });
  return Array.from(byX.values());
}

function ChartCard({ chart }: { chart: ResolvedChart }) {
  const rows = toRows(chart.series);
  if (rows.length === 0) return null;

  return (
    <div className="border border-slate-300 rounded p-3 bg-white">
      <h4 className="font-medium text-black">{chart.title}</h4>
      {chart.rationale && (
        <p className="text-xs text-slate-600 mb-2">{chart.rationale}</p>
      )}
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={rows}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis dataKey="x" fontSize={11} stroke="#6b7280" minTickGap={32} />
          <YAxis fontSize={11} stroke="#6b7280" domain={["auto", "auto"]} />
          <Tooltip
            contentStyle={{
              background: "#ffffff",
              border: "1px solid #e5e7eb",
              borderRadius: 8,
              fontSize: 12,
            }}
          />
          {chart.series.length > 1 && <Legend />}
          {chart.series.map((s, i) => (
            <Line
              key={s.name}
              type="monotone"
              dataKey={s.name}
              stroke={COLORS[i % COLORS.length]}
              strokeWidth={2}
              dot={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
      <p className="text-[10px] text-slate-400 mt-1">
        Source: {chart.source ?? "OpenBB"}
      </p>
    </div>
  );
}

export function ThesisCharts({ charts }: { charts?: ResolvedChart[] }) {
  if (!charts || charts.length === 0) return null;
  return (
    <div className="space-y-3">
      <h3 className="font-medium">Supporting charts</h3>
      {charts.map((c, i) => (
        <ChartCard key={`${c.title}-${i}`} chart={c} />
      ))}
    </div>
  );
}
