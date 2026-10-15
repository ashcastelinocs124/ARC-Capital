import { cn } from "@/lib/cn";
import { C } from "@/lib/theme";

// CNN's zones (same edges as ZONES in signals/fear_greed.py). ARC colours: fear = green (the contrarian
// read, as on Sector Sentiment's divergence chips), greed = red.
export const ZONES = [
  { to: 25, name: "Extreme fear", tok: "success", opacity: 1, cls: "bg-success-soft text-success" },
  { to: 45, name: "Fear", tok: "success", opacity: 0.5, cls: "bg-success-soft text-success" },
  { to: 55, name: "Neutral", tok: "muted-2", opacity: 0.7, cls: "bg-surface-3 text-muted" },
  { to: 75, name: "Greed", tok: "danger", opacity: 0.5, cls: "bg-danger-soft text-danger" },
  { to: 101, name: "Extreme greed", tok: "danger", opacity: 1, cls: "bg-danger-soft text-danger" },
] as const;

// the zone's colour at its own opacity, for SVG fills and gradients
export const zoneColor = (z: (typeof ZONES)[number]) => `rgb(var(--c-${z.tok}) / ${z.opacity})`;

export const zoneOf = (score: number) => ZONES.find((z) => score < z.to) ?? ZONES[4];

export function ZonePill({ score, className }: { score: number; className?: string }) {
  const z = zoneOf(score);
  return <span className={cn("whitespace-nowrap rounded-full px-2 py-0.5 text-[10.5px] font-semibold", z.cls, className)}>{z.name}</span>;
}

// A linear 0-100 bar painted with the zones, and a tick at `score`.
export function ZoneBar({ score }: { score: number }) {
  return (
    <span className="relative block h-1.5 rounded-full"
      style={{ background: `linear-gradient(90deg, ${ZONES.map((z, i) => `${zoneColor(z)} ${i ? ZONES[i - 1].to : 0}% ${Math.min(z.to, 100)}%`).join(", ")})` }}>
      <i className="absolute -top-[3px] h-3 w-[3px] rounded-sm bg-text" style={{ left: `calc(${score}% - 1.5px)` }} />
    </span>
  );
}

const W = 400, H = 222, CX = 200, CY = 178, R = 140, SW = 24;
const pt = (s: number, r: number) => {
  const a = Math.PI * (1 - s / 100);
  return [CX + r * Math.cos(a), CY - r * Math.sin(a)] as const;
};
const arc = (a: number, b: number) => {
  const [x0, y0] = pt(a, R), [x1, y1] = pt(b, R);
  return `M${x0} ${y0} A${R} ${R} 0 0 1 ${x1} ${y1}`;
};

// Semicircle dial, 0 (extreme fear) on the left to 100 (extreme greed) on the right. `ghost` leaves a dashed
// needle at another reading (today's, while a past one is shown).
export function FearGreedGauge({ score, ghost, labels = true }: { score: number; ghost?: number | null; labels?: boolean }) {
  const needle = (s: number) => ({ transform: `rotate(${s * 1.8}deg)`, transformOrigin: `${CX}px ${CY}px` });
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block w-full overflow-visible" role="img" aria-label={`Fear & Greed ${score}: ${zoneOf(score).name}`}>
      {ZONES.map((z, i) => (
        <path key={z.name} d={arc((i ? ZONES[i - 1].to : 0) + 0.6, Math.min(z.to, 100) - 0.6)} stroke={zoneColor(z)} strokeWidth={SW} fill="none" />
      ))}
      {[0, 25, 50, 75, 100].map((t) => {
        const [x, y] = pt(t, R + SW / 2 + 11);
        return <text key={t} x={x} y={y + 4} textAnchor="middle" fontSize={10.5} fill={C.muted2}>{t}</text>;
      })}
      {labels && ZONES.map((z, i) => {
        const [x, y] = pt(Math.min(88, Math.max(12, ((i ? ZONES[i - 1].to : 0) + Math.min(z.to, 100)) / 2)), R - SW / 2 - 28);
        const words = z.name.toUpperCase().split(" ");
        return (
          <text key={z.name} x={x} y={y - (words.length - 1) * 5} textAnchor="middle" fontSize={8.5} fontWeight={600} letterSpacing=".04em" fill={C.muted}>
            {words.map((w, j) => <tspan key={w} x={x} dy={j ? 10 : 0}>{w}</tspan>)}
          </text>
        );
      })}
      {ghost != null && (
        <line x1={CX - R + SW / 2 + 4} y1={CY} x2={CX} y2={CY} stroke={C.muted2} strokeWidth={2} strokeDasharray="3 3" style={needle(ghost)} />
      )}
      <g className="transition-transform duration-500 motion-reduce:transition-none" style={needle(score)}>
        <line x1={CX - R + SW / 2 + 4} y1={CY} x2={CX} y2={CY} stroke={C.text} strokeWidth={3.5} strokeLinecap="round" />
      </g>
      <circle cx={CX} cy={CY} r={8} fill={C.text} />
      <text x={CX} y={CY + 38} textAnchor="middle" fontSize={28} fontWeight={700} fill={C.text}>{score}</text>
    </svg>
  );
}
