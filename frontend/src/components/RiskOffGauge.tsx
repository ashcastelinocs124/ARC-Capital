import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/cn";

interface Props {
  prob?: number; // 0..1
}

export function RiskOffGauge({ prob }: Props) {
  if (prob == null) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Risk-Off Gate</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-32 flex items-center justify-center text-sm text-muted text-center">
            <div>
              <div>No risk-off forecast.</div>
              <div className="text-xs font-mono mt-1">ckm forecast-risk</div>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  const tier =
    prob < 0.3 ? { name: "Calm", color: "text-success", bg: "bg-success", desc: "Pass — full size" }
    : prob < 0.6 ? { name: "Caution", color: "text-warning", bg: "bg-warning", desc: "50% cut on risk-on" }
    : prob < 0.85 ? { name: "Danger", color: "text-danger", bg: "bg-danger", desc: "Veto risk-on equity" }
    : { name: "Capitulation", color: "text-accent", bg: "bg-accent", desc: "Contrarian: 1.3× amplify" };

  // Half-circle gauge calculation
  const angle = prob * 180; // 0..180 degrees
  const r = 60;
  const cx = 75;
  const cy = 80;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Risk-Off Probability</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col items-center">
          <div className="relative">
            <svg width="150" height="100" viewBox="0 0 150 100">
              {/* Background arc */}
              <path
                d={`M ${cx - r},${cy} A ${r},${r} 0 0,1 ${cx + r},${cy}`}
                fill="none"
                stroke="#e5e7eb"
                strokeWidth="10"
                strokeLinecap="round"
              />
              {/* Filled arc */}
              <path
                d={`M ${cx - r},${cy} A ${r},${r} 0 0,1 ${cx + r * Math.cos(Math.PI - (angle * Math.PI) / 180)},${cy - r * Math.sin(Math.PI - (angle * Math.PI) / 180)}`}
                fill="none"
                stroke="currentColor"
                className={tier.color}
                strokeWidth="10"
                strokeLinecap="round"
              />
              {/* Tier markers */}
              {[0.3, 0.6, 0.85].map((t) => {
                const a = t * 180;
                const x = cx - r * Math.cos((a * Math.PI) / 180);
                const y = cy - r * Math.sin((a * Math.PI) / 180);
                return <circle key={t} cx={x} cy={y} r="2" fill="#9ca3af" />;
              })}
            </svg>
            <div className="absolute inset-0 flex items-end justify-center pb-2">
              <span className={cn("text-2xl font-bold font-mono num", tier.color)}>
                {(prob * 100).toFixed(0)}%
              </span>
            </div>
          </div>

          <div className={cn("text-sm font-semibold mt-2 px-3 py-1 rounded-full", tier.bg + "/15", tier.color)}>
            {tier.name}
          </div>
          <div className="text-xs text-muted mt-1">{tier.desc}</div>
        </div>
      </CardContent>
    </Card>
  );
}
