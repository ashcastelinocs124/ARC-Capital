import { useState } from "react";
import type { WeekAhead } from "@/api/types";
import { C } from "@/lib/theme";
import { useTip } from "./Tooltip";

const SERIES: [string, string, string][] = [
  ["RAMPAIALL", "Any AI", C.text],
  ["RAMPAIANTHROPIC", "Anthropic", C.inflation],
  ["RAMPAIOPENAI", "OpenAI", C.jobs],
  ["RAMPAIXAI", "xAI", C.ai],
];
const LAB: Record<string, string> = {
  deepseek: "DeepSeek", "z-ai": "Z.ai", openai: "OpenAI", anthropic: "Anthropic", google: "Google", "x-ai": "xAI",
  meta: "Meta", "meta-llama": "Meta", xiaomi: "Xiaomi", tencent: "Tencent", stepfun: "StepFun", nvidia: "NVIDIA",
  moonshotai: "Moonshot AI", mistralai: "Mistral", qwen: "Qwen", other: "Other",
};
const labName = (k: string) => LAB[k] ?? k.charAt(0).toUpperCase() + k.slice(1);

/** Ramp AI Index: share of US businesses paying for AI, by provider, monthly. */
export function RampChart({ ramp }: { ramp: WeekAhead["spend"]["ramp"] }) {
  const [hover, setHover] = useState<number | null>(null);
  const all = ramp.RAMPAIALL ?? [];
  const months = all.map(([m]) => m);
  if (!months.length) return <p className="text-sm text-muted">Ramp data unavailable.</p>;
  const val = (sid: string) => new Map(ramp[sid] ?? []);
  const Lx = 34, Rx = 450, T = 10, B = 230, n = months.length;
  const max = Math.ceil(Math.max(...all.map(([, v]) => v)) / 20) * 20;
  const x = (i: number) => Lx + (i * (Rx - Lx)) / Math.max(1, n - 1), y = (v: number) => B - (v / max) * (B - T);
  const years = months.map((m, i) => [m, i] as const).filter(([m]) => m.endsWith("-01"));
  const tx = hover == null ? 0 : Math.min(x(hover) + 8, Rx - 120);
  return (
    <svg viewBox="0 0 560 260" className="w-full h-auto overflow-visible" role="img" aria-label="Share of US businesses paying for AI, by provider"
      onMouseMove={(ev) => {
        const b = (ev.currentTarget as SVGSVGElement).getBoundingClientRect();
        const i = Math.round((((ev.clientX - b.left) * 560) / b.width - Lx) / ((Rx - Lx) / Math.max(1, n - 1)));
        setHover(i >= 0 && i < n ? i : null);
      }}
      onMouseLeave={() => setHover(null)}>
      {[0, 0.25, 0.5, 0.75, 1].map((f) => (
        <g key={f}>
          <line x1={Lx} x2={Rx} y1={y(max * f)} y2={y(max * f)} stroke={C.grid} />
          <text x={Lx - 6} y={y(max * f) + 4} textAnchor="end" fontSize={11} fill={C.muted}>{Math.round(max * f)}%</text>
        </g>
      ))}
      {years.map(([m, i]) => <text key={m} x={x(i)} y={B + 16} fontSize={11} fill={C.muted}>{m.slice(0, 4)}</text>)}
      {SERIES.map(([sid, name, col], k) => {
        const v = val(sid);
        const pts = months.map((m, i) => (v.has(m) ? `${x(i)},${y(v.get(m)!)}` : null)).filter(Boolean);
        const arr = ramp[sid] ?? [], last = arr[arr.length - 1];
        return (
          <g key={sid}>
            <polyline points={pts.join(" ")} fill="none" stroke={col} strokeWidth={2} strokeLinejoin="round" />
            {last && (
              <text x={Rx + 8} y={y(last[1]) + 4 + (k === 2 ? 7 : k === 1 ? -5 : 0)} fontSize={11} fontWeight={600} fill={C.text}>
                {name} {last[1].toFixed(1)}%
              </text>
            )}
          </g>
        );
      })}
      {hover != null && (
        <g>
          <line x1={x(hover)} x2={x(hover)} y1={T} y2={B} stroke={C.muted2} />
          <rect x={tx} y={T} width={128} height={78} rx={6} fill={C.text} />
          <text x={tx + 8} y={T + 16} fontSize={11} fontWeight={700} fill={C.surface}>{months[hover]}</text>
          {SERIES.map(([sid, name], k) => (
            <text key={sid} x={tx + 8} y={T + 32 + k * 13} fontSize={11} fill={C.surface}>
              {name} {val(sid).get(months[hover])?.toFixed(1) ?? "–"}%
            </text>
          ))}
        </g>
      )}
    </svg>
  );
}

/** OpenRouter: share of the week's top-20-model tokens, by lab. */
export function OpenRouterBars({ or }: { or: WeekAhead["spend"]["openrouter"] }) {
  const { show, hide, node } = useTip();
  if (!or?.labs.length) return <p className="text-sm text-muted">OpenRouter data unavailable.</p>;
  const max = Math.max(...or.labs.map((l) => l.share)) * 1.1, Lx = 96, Rx = 500, RH = 28;
  const x = (v: number) => Lx + (v / max) * (Rx - Lx);
  const color = (k: string) => (k === "other" ? C.muted2 : k === "anthropic" ? C.inflation : k === "openai" ? C.jobs : C.ai);
  return (
    <>
      <svg viewBox={`0 0 560 ${RH * or.labs.length + 8}`} className="w-full h-auto overflow-visible" role="img" aria-label="OpenRouter token share by lab">
        {or.labs.map((l, i) => {
          const y = 4 + RH * i;
          return (
            <g key={l.lab} onMouseLeave={hide}
              onMouseMove={(ev) => show(ev, <><b>{labName(l.lab)}</b><div>{l.share}% of tokens · {(l.tokens / 1e12).toFixed(2)}T tokens</div></>)}>
              <rect x={0} y={y} width={560} height={RH} fill="transparent" />
              <text x={Lx - 8} y={y + 17} textAnchor="end" fontSize={12} fill={C.text}>{labName(l.lab)}</text>
              <rect x={Lx} y={y + 5} width={Math.max(1, x(l.share) - Lx)} height={RH - 10} rx={3} fill={color(l.lab)} />
              <text x={x(l.share) + 6} y={y + 17} fontSize={11} fill={C.text2}>{l.share}%</text>
            </g>
          );
        })}
      </svg>
      {node}
    </>
  );
}
