import { useState } from "react";
import type { AiSentiment } from "@/api/types";
import { C } from "@/lib/theme";
import { useTip } from "./Tooltip";

const sgn = (v: number | null) => (v == null ? "–" : `${v > 0 ? "+" : ""}${v}`);
const tone = (v: number) => (v >= 0 ? C.earnings : C.danger);
const THIN = 10; // fewer posts than this in 7 days = hatched

/** Post text with the scoring words marked, so every score can be checked by eye. */
function Marked({ text, hits }: { text: string; hits: string[] }) {
  if (!hits.length) return <>{text}</>;
  const re = new RegExp(`\\b(${hits.map((h) => h.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})\\b`, "gi");
  return <>{text.split(re).map((part, i) => (i % 2 ? <mark key={i} className="bg-warning-soft text-text rounded px-0.5">{part}</mark> : part))}</>;
}

/** AI Model Sentiment: where each provider stands, how fast it is moving, and how they compare. */
export function AiSentimentCard({ data }: { data: AiSentiment }) {
  const { show, hide, node } = useTip();
  const names = Object.keys(data.providers).sort((a, b) => data.providers[b].level - data.providers[a].level);
  const [sel, setSel] = useState(names[0]);
  const [hov, setHov] = useState<string | null>(null);
  if (!names.length) return <p className="text-sm text-muted">No posts scored yet.</p>;
  const cur = hov ?? (names.includes(sel) ? sel : names[0]);
  const on = (k: string) => k === cur;
  const bind = (k: string) => ({
    onMouseEnter: () => setHov(k),
    onMouseLeave: () => { setHov(null); hide(); },
    onClick: () => setSel(k),
    style: { cursor: "pointer" },
  });
  const P = data.providers;

  // 1 · level bars with Δ7d
  const levels = names.map((k) => P[k].level);
  const lo = Math.min(-20, ...levels), hi = Math.max(20, ...levels);
  const bL = 110, bR = 400, bx = (v: number) => bL + ((v - lo) / (hi - lo)) * (bR - bL), b0 = bx(0), RH = 36;

  // 2 · momentum map
  const withD = names.filter((k) => P[k].delta != null);
  const ds = withD.map((k) => P[k].delta!);
  const dMax = Math.max(10, ...ds.map(Math.abs));
  const mL = 50, mR = 500, mT = 10, mB = 290;
  const mx = (v: number) => mL + ((v - lo) / (hi - lo)) * (mR - mL), my = (v: number) => mB - ((v + dMax) / (2 * dMax)) * (mB - mT);

  // 3 · trend lines on one axis
  const days = [...new Set(names.flatMap((k) => P[k].series.map(([d]) => d)))].sort();
  const all = names.flatMap((k) => P[k].series.map(([, v]) => v));
  const tLo = Math.min(-20, ...all), tHi = Math.max(20, ...all);
  const tL = 40, tR = 960, tT = 10, tB = 220;
  const tx = (d: string) => tL + (days.indexOf(d) / Math.max(1, days.length - 1)) * (tR - tL), ty = (v: number) => tB - ((v - tLo) / (tHi - tLo)) * (tB - tT);
  const ends: number[] = []; // nudge end labels apart
  const endY = (y: number) => { let v = y; while (ends.some((e) => Math.abs(e - v) < 12)) v += 12; ends.push(v); return v; };

  return (
    <>
      <div className="grid gap-6 md:grid-cols-2">
        <div className="min-w-0">
          <h3 className="text-[13px] font-semibold text-text-2 mb-1">Where each provider stands (7-day average, Δ vs last week)</h3>
          <svg viewBox={`0 0 520 ${names.length * RH + 24}`} className="w-full h-auto overflow-visible" role="img" aria-label="Seven-day net sentiment by provider">
            <defs>
              <pattern id="ai-thin" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                <rect width="3" height="6" fill={C.surface} opacity={0.55} />
              </pattern>
            </defs>
            <line x1={b0} x2={b0} y1={0} y2={names.length * RH} stroke={C.muted2} />
            <text x={bR + 50} y={-2} fontSize={10.5} fill={C.muted}>Δ7d</text>
            {names.map((k, i) => {
              const p = P[k], y = i * RH, neg = p.level < 0, w = Math.max(1, Math.abs(bx(p.level) - b0));
              return (
                <g key={k} {...bind(k)} opacity={on(k) ? 1 : 0.6}
                  onMouseMove={(ev) => show(ev, <><b>{k}</b><div>7-day net {sgn(p.level)} · Δ7d {sgn(p.delta)} pts</div><div>{p.n7} posts in the last 7 days</div></>)}>
                  <rect x={0} y={y} width={520} height={RH} fill="transparent" />
                  <text x={bL - 10} y={y + 15} textAnchor="end" fontSize={12} fontWeight={on(k) ? 700 : 600} fill={C.text}>{k}</text>
                  <text x={bL - 10} y={y + 28} textAnchor="end" fontSize={10.5} fill={C.muted}>{p.n7} posts/wk</text>
                  <rect x={neg ? bx(p.level) : b0} y={y + 6} width={w} height={20} rx={4} fill={tone(p.level)} />
                  {p.n7 < THIN && <rect x={neg ? bx(p.level) : b0} y={y + 6} width={w} height={20} rx={4} fill="url(#ai-thin)" />}
                  <text x={neg ? b0 + 6 : bx(p.level) + 6} y={y + 20} fontSize={11.5} fontWeight={600} fill={C.text2}>{sgn(p.level)}</text>
                  <text x={bR + 50} y={y + 20} fontSize={11.5} fontWeight={700} fill={p.delta == null ? C.muted : tone(p.delta)}>
                    {p.delta == null ? "new" : `${p.delta > 0 ? "▲ " : p.delta < 0 ? "▼ " : ""}${sgn(p.delta)}`}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>
        <div className="min-w-0">
          <h3 className="text-[13px] font-semibold text-text-2 mb-1">Momentum: level vs rate of change</h3>
          {withD.length ? (
            <svg viewBox="0 0 520 330" className="w-full h-auto overflow-visible" role="img" aria-label="Sentiment level versus seven-day change by provider">
              <line x1={mx(0)} x2={mx(0)} y1={mT} y2={mB} stroke={C.muted2} />
              <line x1={mL} x2={mR} y1={my(0)} y2={my(0)} stroke={C.muted2} />
              <text x={mR - 6} y={mT + 12} textAnchor="end" fontSize={10.5} fill={C.muted2}>Liked &amp; improving</text>
              <text x={mR - 6} y={mB - 6} textAnchor="end" fontSize={10.5} fill={C.muted2}>Liked &amp; cooling</text>
              <text x={mL + 6} y={mT + 12} fontSize={10.5} fill={C.muted2}>Disliked &amp; recovering</text>
              <text x={mL + 6} y={mB - 6} fontSize={10.5} fill={C.muted2}>Disliked &amp; worsening</text>
              <text x={(mL + mR) / 2} y={mB + 30} textAnchor="middle" fontSize={11} fill={C.muted}>Level: 7-day net sentiment →</text>
              <text x={14} y={(mT + mB) / 2} textAnchor="middle" fontSize={11} fill={C.muted} transform={`rotate(-90 14 ${(mT + mB) / 2})`}>Δ7d rate of change →</text>
              {withD.map((k, i, arr) => {
                const p = P[k], X = mx(p.level), Y = my(p.delta!);
                // a label that would sit on an earlier one moves down a line
                const clash = arr.slice(0, i).filter((o) => Math.abs(mx(P[o].level) - X) < 90 && Math.abs(my(P[o].delta!) - Y) < 13).length;
                return (
                  <g key={k} {...bind(k)} onMouseMove={(ev) => show(ev, <><b>{k}</b><div>level {sgn(p.level)} · Δ7d {sgn(p.delta)} pts</div></>)}>
                    <circle cx={X} cy={Y} r={on(k) ? 9 : 7} fill={tone(p.delta!)} stroke={on(k) ? C.text : C.surface} strokeWidth={2} />
                    <text x={X > mR - 90 ? X - 11 : X + 11} y={Y + 4 + clash * 13} textAnchor={X > mR - 90 ? "end" : "start"} fontSize={12} fontWeight={on(k) ? 700 : 500} fill={C.text}>{k}</text>
                    <circle cx={X} cy={Y} r={14} fill="transparent" />
                  </g>
                );
              })}
            </svg>
          ) : (
            <p className="text-sm text-muted">Rate of change appears once there are 14 days of history.</p>
          )}
        </div>
      </div>
      {days.length > 1 && (
        <>
          <h3 className="text-[13px] font-semibold text-text-2 mt-4 mb-1">Trend: 7-day average net sentiment, all providers</h3>
          <svg viewBox="0 0 1100 250" className="w-full h-auto overflow-visible" role="img" aria-label="Seven-day net sentiment over time, all providers">
            {[tLo, 0, tHi].map((v) => (
              <g key={v}>
                <line x1={tL} x2={tR} y1={ty(v)} y2={ty(v)} stroke={v ? C.grid : C.muted2} />
                <text x={tL - 6} y={ty(v) + 4} textAnchor="end" fontSize={11} fill={C.muted}>{sgn(Math.round(v))}</text>
              </g>
            ))}
            {days.map((d, i) => i % Math.ceil(days.length / 7) === 0 && (
              <text key={d} x={tx(d)} y={tB + 16} textAnchor="middle" fontSize={11} fill={C.muted}>
                {new Date(d + "T12:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" })}
              </text>
            ))}
            {[...names].sort((a, b) => Number(on(a)) - Number(on(b))).map((k) => {
              const pts = P[k].series.map(([d, v]) => `${tx(d)},${ty(v)}`).join(" ");
              const last = P[k].series[P[k].series.length - 1];
              return (
                <g key={k} {...bind(k)}>
                  <polyline points={pts} fill="none" stroke={on(k) ? C.text : C.borderStrong} strokeWidth={on(k) ? 2.5 : 1.5} />
                  <polyline points={pts} fill="none" stroke="transparent" strokeWidth={12} />
                  {last && <text x={tR + 8} y={endY(ty(last[1])) + 4} fontSize={11.5} fontWeight={on(k) ? 700 : 400} fill={on(k) ? C.text : C.muted2}>{k} {sgn(last[1])}</text>}
                </g>
              );
            })}
          </svg>
        </>
      )}
      <div className="border-t border-border mt-3 pt-2 text-[12.5px]">
        <b>{cur}: sample posts</b> <span className="text-muted">(scoring words highlighted)</span>
        {P[cur].samples.map((s) => (
          <div key={s.url} className="my-1.5">
            <span className="font-bold" style={{ color: s.score > 0 ? C.earnings : s.score < 0 ? C.danger : C.muted }}>
              {s.score > 0 ? "+" : s.score < 0 ? "−" : "·"}
            </span>{" "}
            <a className="text-text-2 underline" href={s.url} target="_blank" rel="noreferrer">@{s.author}</a>: “<Marked text={s.text} hits={s.hits} />”
          </div>
        ))}
      </div>
      {node}
    </>
  );
}
