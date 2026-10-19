import { useMemo, type ReactNode } from "react";
import { LAT0, LON0, STEP, WORLD_ROWS } from "@/components/worldMap";

// The home splash art, shared by the home page and the admin sign-in page: circuit traces,
// a line-drawn world skyline under a dotted world map, floating chips and walking robots (animations in index.css).

// Circuit-board trace bundles behind the hero (after semianalysis.com). Each bundle is one
// route copied 7 times, shifted by (d, -d): perpendicular to every horizontal, vertical and
// ↘ segment, so routes may only use those directions (a ↗ segment would collapse the bundle).
// The splash plays logo first, then name and button; the background (traces, skyline, chips,
// robots) starts BG seconds in.
const BG = 1.2;
const ROUTES = [
  "-20,60 180,60 300,180 520,180 620,280 620,440",
  "760,-20 760,90 880,210 1220,210",
  "-20,330 240,330 340,430",
  "1220,350 1040,350 960,270 960,-20",
];

export function CircuitTraces() {
  return (
    <svg aria-hidden viewBox="0 0 1200 400" preserveAspectRatio="xMidYMid slice" className="pointer-events-none absolute inset-0 h-full w-full" fill="none" stroke="currentColor" strokeWidth={1}>
      {ROUTES.map((pts, r) =>
        Array.from({ length: 7 }, (_, k) => (
          <polyline key={`${r}-${k}`} points={pts} pathLength={1} transform={`translate(${k * 6} ${-k * 6})`} className="trace text-accent" strokeOpacity={0.22} style={{ animationDelay: `${BG + r * 0.15 + k * 0.04}s` }} />
        )),
      )}
    </svg>
  );
}

// A line-drawn world skyline along the bottom of the splash (global macro: one landmark per
// financial centre), in map order west → east, below a dotted
// world map; a dashed line ties each landmark to its city, and planes fly between the cities. Outlines draw in like the traces,
// then the map fades in and a few windows twinkle. Landmarks are hand-drawn in a 1200×300 box
// (ground at y=300) and placed at `x`; the filler blocks come from a seeded random so the skyline
// is the same on every load. Circles use ry = rx / 1.4 so they come out round after the 1.4×
// vertical stretch.
const ring = (cx: number, cy: number, r: number) => `M${cx + r},${cy} a${r},${r / 1.4} 0 1 0 ${-2 * r},0 a${r},${r / 1.4} 0 1 0 ${2 * r},0`;
const TAIPEI = Array.from({ length: 8 }, (_, k) => `M906,${200 - 12 * k} L902,${188 - 12 * k} H948 L944,${200 - 12 * k}`).join(" ");
type Landmark = { l: number; r: number; top: number; d: string; x: number; city: string; lon: number; lat: number };
const LANDMARKS: Landmark[] = [
  // l, r, top = the drawing's span and highest y; x = where its centre stands on the ground
  { l: 512, r: 608, top: 44, x: 70, city: "NEW YORK", lon: -73.99, lat: 40.75, d: "M515,300 V185 H530 V135 H543 V105 H553 V88 H557 V58 L560,44 L563,58 V88 H567 V105 H577 V135 H590 V185 H605 V300" }, // Empire State
  { l: 766, r: 834, top: 30, x: 175, city: "NEW YORK", lon: -74.01, lat: 40.71, d: "M770,300 V245 L784,92 H816 L830,245 V300 M800,92 V30" }, // One World Trade Center
  { l: 44, r: 76, top: 90, x: 300, city: "LONDON", lon: -0.12, lat: 51.5, d: `M48,300 V150 H72 V300 M46,150 H74 M48,150 V128 H72 V150 M52,128 L60,98 L68,128 M60,98 V90 ${ring(60, 139, 6)}` }, // Big Ben
  { l: 1000, r: 1050, top: 60, x: 370, city: "LONDON", lon: -0.09, lat: 51.5, d: "M1002,300 L1024,72 M1048,300 L1028,72 M1024,72 L1030,60 M1012,200 H1038" }, // The Shard
  { l: 130, r: 210, top: 48, x: 465, city: "PARIS", lon: 2.35, lat: 48.86, d: "M132,300 Q160,230 166,170 L168,120 L170,70 M208,300 Q180,230 174,170 L172,120 L170,70 V48 M150,255 H190 M161,210 H179 M165,170 H175 M150,300 Q170,268 190,300" }, // Eiffel Tower
  { l: 270, r: 330, top: 12, x: 590, city: "DUBAI", lon: 55.27, lat: 25.2, d: "M272,300 V230 H280 V170 H288 V120 H294 V80 H298 V40 L300,12 L302,40 V80 H306 V120 H312 V170 H320 V230 H328 V300" }, // Burj Khalifa
  { l: 370, r: 440, top: 75, x: 705, city: "KUALA LUMPUR", lon: 101.71, lat: 3.16, d: "M374,300 V130 L378,118 L385,105 L392,118 L396,130 V300 M385,105 V75 M414,300 V130 L418,118 L425,105 L432,118 L436,130 V300 M425,105 V75 M396,200 H414 M396,206 H414" }, // Petronas Towers
  { l: 668, r: 712, top: 50, x: 830, city: "SHANGHAI", lon: 121.5, lat: 31.24, d: `M672,300 L682,226 M708,300 L698,226 M690,300 V50 ${ring(690, 218, 12)} ${ring(690, 130, 7)} ${ring(690, 82, 3)}` }, // Oriental Pearl
  { l: 900, r: 950, top: 58, x: 935, city: "TAIPEI", lon: 121.56, lat: 25.03, d: `M904,300 V200 H946 V300 ${TAIPEI} M914,104 V92 H936 V104 M925,92 V58` }, // Taipei 101
  { l: 1090, r: 1160, top: 30, x: 1080, city: "TOKYO", lon: 139.75, lat: 35.66, d: "M1092,300 L1118,140 L1122,60 M1158,300 L1132,140 L1128,60 M1122,60 H1128 V30 M1105,220 H1145 M1112,180 H1138 M1116,140 H1134 M1092,300 L1145,220 M1158,300 L1105,220" }, // Tokyo Tower
];
const S = 1.3; // landmark size, on top of the 1.4× vertical stretch
const place = (m: Landmark) => `translate(${m.x} 300) scale(${S} ${S * 1.4}) translate(${-(m.l + m.r) / 2} -300)`;
// the map: 100°W–150°E (the Americas to Japan) across the width, 75°N–45°S in the band y = -300…-40
const mx = (lon: number) => ((lon - LON0) / 250) * 1200;
const my = (lat: number) => -300 + ((75 - lat) / 120) * 260;
const DOTS = WORLD_ROWS.flatMap((row, i) =>
  [...row].flatMap((h, j) => [0, 1, 2, 3].filter((b) => (parseInt(h, 16) >> (3 - b)) & 1).map((b) => {
    const k = j * 4 + b;
    return `M${mx(LON0 + STEP * k).toFixed(1)} ${my(LAT0 - STEP * i).toFixed(1)}h0`;
  })),
).join("");

// Planes fly the routes between the financial centres, arcing over the map (SVG motion, so it runs in
// every browser; left out for prefers-reduced-motion, which keeps only the dashed routes).
const AIR: [string, string, number, number][] = [
  // from, to, seconds per flight, start (after BG); return legs reuse the same arc
  ["NEW YORK", "LONDON", 5.5, 2], ["LONDON", "NEW YORK", 6, 4.5], ["NEW YORK", "PARIS", 5.5, 7],
  ["PARIS", "NEW YORK", 6, 3.2], ["LONDON", "DUBAI", 4.5, 2.6], ["DUBAI", "LONDON", 4.5, 5.4],
  ["PARIS", "DUBAI", 4.2, 6.3], ["DUBAI", "KUALA LUMPUR", 4, 3.6], ["KUALA LUMPUR", "DUBAI", 4, 6.8],
  ["KUALA LUMPUR", "SHANGHAI", 3.6, 2.9], ["SHANGHAI", "TOKYO", 3, 3.9], ["TOKYO", "SHANGHAI", 3, 5.7],
  ["TAIPEI", "TOKYO", 2.8, 4.4], ["LONDON", "SHANGHAI", 6.5, 5],
  // the Americas, west of New York, through hubs that have no landmark
  ["CHICAGO", "NEW YORK", 2.6, 2.3], ["NEW YORK", "CHICAGO", 2.6, 5.1], ["HOUSTON", "NEW YORK", 3.4, 3.3],
  ["NEW YORK", "SÃO PAULO", 4.5, 2.5], ["SÃO PAULO", "NEW YORK", 4.5, 5.8], ["HOUSTON", "SÃO PAULO", 4.8, 4.2],
  ["SÃO PAULO", "LONDON", 5.5, 3.6], ["CHICAGO", "LONDON", 5.5, 6.1],
  // flights out of Asia, including hubs that have no landmark
  ["TOKYO", "NEW YORK", 7, 2.7], ["TOKYO", "LONDON", 6.5, 4.8], ["SHANGHAI", "LONDON", 6.5, 3.1],
  ["SHANGHAI", "DUBAI", 4.5, 5.9], ["TAIPEI", "KUALA LUMPUR", 3, 2.4], ["KUALA LUMPUR", "LONDON", 5.5, 4.6],
  ["HONG KONG", "LONDON", 6, 2.2], ["HONG KONG", "DUBAI", 4.2, 6.6], ["SINGAPORE", "PARIS", 5.8, 3.4],
  ["SINGAPORE", "DUBAI", 4, 5.2], ["SEOUL", "NEW YORK", 7, 4], ["TOKYO", "SINGAPORE", 3.4, 6.2],
  ["MUMBAI", "LONDON", 4.5, 2.8], ["MUMBAI", "NEW YORK", 6, 5.6],
];
const HUBS: Record<string, { lon: number; lat: number }> = {
  CHICAGO: { lon: -87.63, lat: 41.88 }, HOUSTON: { lon: -95.37, lat: 29.76 }, "SÃO PAULO": { lon: -46.63, lat: -23.55 },
  "HONG KONG": { lon: 114.17, lat: 22.32 }, SINGAPORE: { lon: 103.82, lat: 1.35 }, SEOUL: { lon: 126.98, lat: 37.57 },
  MUMBAI: { lon: 72.88, lat: 19.08 },
};
const at = (city: string) => HUBS[city] ?? LANDMARKS.find((m) => m.city === city)!;
const FLIGHTS = AIR.map(([a, b, dur, start]) => {
  const x1 = mx(at(a).lon), y1 = my(at(a).lat), x2 = mx(at(b).lon), y2 = my(at(b).lat);
  const cy = Math.min(y1, y2) - Math.abs(x2 - x1) * 0.22 - 10; // arc up, higher for longer hops
  return { d: `M${x1.toFixed(1)},${y1.toFixed(1)} Q${((x1 + x2) / 2).toFixed(1)},${cy.toFixed(1)} ${x2.toFixed(1)},${y2.toFixed(1)}`, dur, start };
});
// top view, nose along +x, about 15 units long (drawn at 1.5×)
const PLANE = "M7.5,0 L2,-1.1 L-1,-6.5 L-3,-6.5 L-1.2,-1.1 L-5,-1.1 L-6.6,-3.4 L-7.8,-3.4 L-6.8,0 L-7.8,3.4 L-6.6,3.4 L-5,1.1 L-1.2,1.1 L-3,6.5 L-1,6.5 L2,1.1 Z";

function Flights() {
  const still = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  return (
    <g>
      <g className="rise" style={{ animationDelay: `${BG + 1}s` }}>
        {FLIGHTS.map((f, i) => <path key={i} d={f.d} strokeOpacity={0.22} strokeDasharray="1 5" strokeLinecap="round" />)}
      </g>
      {!still && FLIGHTS.map((f, i) => (
        // opacity 0 until the motion starts, so a plane never sits at the origin
        <g key={i} opacity={0}>
          <animateMotion path={f.d} dur={`${f.dur}s`} begin={`${BG + f.start}s`} repeatCount="indefinite" rotate="auto" />
          <animate attributeName="opacity" values="0;0.95;0.95;0" keyTimes="0;0.12;0.88;1" dur={`${f.dur}s`} begin={`${BG + f.start}s`} repeatCount="indefinite" />
          <path d={PLANE} transform="scale(1.5)" fill="currentColor" stroke="none" />
        </g>
      ))}
    </g>
  );
}

export function Skyline() {
  const { blocks, windows } = useMemo(() => {
    let s = 7;
    const rnd = () => ((s = (s * 16807) % 2147483647) / 2147483647);
    const spans = LANDMARKS.map((m) => [m.x - ((m.r - m.l) / 2) * S - 6, m.x + ((m.r - m.l) / 2) * S + 6]);
    const blocks: string[] = [], windows: [number, number, number][] = [];
    for (let x = 0; x < 1200; ) {
      const hit = spans.find(([l, r]) => x + 16 > l && x < r);
      if (hit) { x = hit[1]; continue; }
      const w = 22 + rnd() * 34, h = 50 + rnd() * 110, top = 300 - h; // low, so the landmarks lead
      blocks.push(`M${x},300 V${top} H${x + w} V300`);
      for (let k = 0; k < 3; k++) if (rnd() < 0.6) windows.push([x + 4 + rnd() * (w - 10), top + 12 + rnd() * (h - 24), rnd()]);
      x += w + 2 + rnd() * 6;
    }
    return { blocks, windows };
  }, []);
  const draw = (i: number) => ({ animationDelay: `${BG + 0.2 + (i % 12) * 0.06}s`, animationDuration: "2.2s" });
  return (
    // As wide as the splash (its height follows the 1200×304 box); on phones the 45% floor makes `slice`
    // show the middle of the skyline, as before. The map and the landmarks' tops overflow upward.
    <svg aria-hidden viewBox="0 0 1200 304" preserveAspectRatio="xMidYMax slice" overflow="visible" className="pointer-events-none absolute inset-x-0 bottom-0 aspect-[1200/304] min-h-[45%] w-full text-accent" fill="none" stroke="currentColor" strokeWidth={1.2}>
      <path d={DOTS} className="rise" strokeWidth={3} strokeLinecap="round" strokeOpacity={0.3} style={{ animationDelay: `${BG + 0.6}s` }} />
      <Flights />
      <g className="rise" style={{ animationDelay: `${BG + 1.8}s` }}>
        {LANDMARKS.map((m, i) => (
          <g key={i}>
            <path d={`M${m.x},${300 - (300 - m.top) * S * 1.4 - 6} L${mx(m.lon)},${my(m.lat)}`} strokeOpacity={0.28} strokeDasharray="2 4" />
            <circle cx={mx(m.lon)} cy={my(m.lat)} r={3.6} fill="currentColor" stroke="none" opacity={0.9} />
          </g>
        ))}
        {Object.values(HUBS).map((h, i) => <circle key={i} cx={mx(h.lon)} cy={my(h.lat)} r={2.6} fill="currentColor" stroke="none" opacity={0.7} />)}
      </g>
      {blocks.map((d, i) => <path key={i} d={d} pathLength={1} className="trace" strokeOpacity={0.2} style={draw(i)} />)}
      {LANDMARKS.map((m, i) => (
        <g key={i} transform={place(m)}><path d={m.d} pathLength={1} vectorEffect="non-scaling-stroke" className="trace" strokeOpacity={0.7} style={draw(i)} /></g>
      ))}
      {windows.map(([x, y, r], i) => (
        <rect key={i} x={x} y={y} width={4} height={5} fill="currentColor" stroke="none" className="twinkle" style={{ animationDelay: `${BG + 2 + r * 6}s`, animationDuration: `${3 + r * 4}s` }} />
      ))}
      {CHIPS.map(([x, y, s], i) => <Chip key={i} x={x} y={y} s={s} delay={BG + 1.4 + i * 0.15} kind={(["cpu", "gpu", "agent"] as const)[i % 3]} />)}
      <g className="rise" style={{ animationDelay: `${BG + 1.6}s` }}>{ROBOTS.map(([dur, delay, scale], i) => <Robot key={i} dur={dur} delay={delay} scale={scale} />)}</g>
      <line x1={0} y1={299.5} x2={1200} y2={299.5} strokeOpacity={0.45} />
    </svg>
  );
}

// Chips float over the skyline; robots walk along the street (both drawn in the skyline's box).
const CHIPS: [number, number, number][] = [[60, 40, 28], [170, 70, 34], [290, 22, 24], [420, 30, 26], [470, 95, 20], [780, 40, 40], [800, 130, 22], [900, 30, 28], [1010, 92, 30], [1130, 50, 34], [115, 125, 22], [235, 110, 26], [360, 80, 30], [20, 100, 20], [455, -20, 24], [700, 110, 24], [860, 85, 26], [960, -10, 24], [1075, 140, 22], [1180, 115, 26], [340, -30, 22], [1060, 15, 22], [145, -15, 26], [880, 150, 20]]; // x, y, size
const ROBOTS: [number, number, number][] = [[38, 0, 1.1], [52, -20, 0.9], [45, -34, 1.3], [60, -8, 1], [34, -16, 1.05], [48, -42, 1.2], [56, -28, 0.85], [42, -6, 1.15], [64, -50, 0.95], [36, -26, 1.25], [50, -12, 1], [58, -38, 1.1]]; // seconds to cross, delay, scale

// CPU = 2×2 cores under a heat spreader, pins on all sides; GPU = one big die flanked by four
// HBM stacks, edge-connector fingers along the bottom; agent = a chat bubble with a bot face.
function Chip({ x, y, s, delay, kind }: { x: number; y: number; s: number; delay: number; kind: "cpu" | "gpu" | "agent" }) {
  const pins = [0.2, 0.4, 0.6, 0.8].map((f) => f * s);
  const fingers = [0.15, 0.3, 0.45, 0.6, 0.75, 0.9].map((f) => f * s);
  const core = s * 0.17, gap = s * 0.04, c0 = s / 2 - core - gap / 2;
  const hbm = (hx: number, hy: number) => <rect key={`${hx},${hy}`} x={hx} y={hy} width={s * 0.14} height={s * 0.2} rx={1} />;
  return (
    <g className="rise" style={{ animationDelay: `${delay}s` }}>
      <g className="float" style={{ animationDelay: `${delay}s` }}>
        <g transform={`translate(${x - s / 2} ${y - s / 2})`} strokeOpacity={0.6}>
          {kind === "agent" ? (
            <>
              <path d={`M${s * 0.3},${s} H${s * 0.7 - 6} a6,6 0 0 0 6,-6 V${s * 0.22 + 6} a6,6 0 0 0 -6,-6 H6 a6,6 0 0 0 -6,6 V${s - 6} a6,6 0 0 0 6,6 H${s * 0.15} l0,${s * 0.2} Z`} fill="rgb(var(--c-surface))" />
              <rect x={s * 0.15} y={s * 0.4} width={s * 0.4} height={s * 0.36} rx={s * 0.08} />
              <circle cx={s * 0.27} cy={s * 0.58} r={s * 0.05} className="chip-die" fill="currentColor" stroke="none" />
              <circle cx={s * 0.43} cy={s * 0.58} r={s * 0.05} className="chip-die" fill="currentColor" stroke="none" />
              <path d={`M${s * 0.35},${s * 0.4} V${s * 0.3}`} />
              <circle cx={s * 0.35} cy={s * 0.27} r={s * 0.035} fill="currentColor" stroke="none" className="twinkle" />
              <path d={`M${s * 0.85},${s * 0.02} v${s * 0.16} M${s * 0.77},${s * 0.1} h${s * 0.16}`} className="twinkle" />
            </>
          ) : <rect width={s} height={s} rx={3} fill="rgb(var(--c-surface))" />}
          {kind === "agent" ? null : kind === "gpu" ? (
            <>
              <rect x={s * 0.32} y={s * 0.25} width={s * 0.36} height={s * 0.42} rx={1.5} className="chip-die" fill="currentColor" stroke="none" />
              {[hbm(s * 0.12, s * 0.23), hbm(s * 0.12, s * 0.49), hbm(s * 0.74, s * 0.23), hbm(s * 0.74, s * 0.49)]}
              {fingers.map((f) => <path key={f} d={`M${f},${s} v4`} />)}
            </>
          ) : (
            <>
              <rect x={s * 0.2} y={s * 0.2} width={s * 0.6} height={s * 0.6} rx={2} fill="none" />
              {[0, 1].flatMap((i) => [0, 1].map((j) => (
                <rect key={`${i}${j}`} x={c0 + i * (core + gap)} y={c0 + j * (core + gap)} width={core} height={core} rx={0.8} className="chip-die" fill="currentColor" stroke="none" />
              )))}
              {pins.map((p) => <path key={p} d={`M${p},0 v-5 M${p},${s} v5 M0,${p} h-5 M${s},${p} h5`} />)}
            </>
          )}
        </g>
      </g>
    </g>
  );
}

// A line-drawn humanoid walking right: visor head, tapered torso, arms and legs that swing
// from shoulder and hip in opposite phase. Feet on y=0, about 56 units tall before scale.
function Robot({ dur, delay, scale }: { dur: number; delay: number; scale: number }) {
  const limb = (cls: string, x: number, y: number, d: string, extra?: ReactNode) => (
    <g transform={`translate(${x} ${y})`}><g className={cls}><path d={d} />{extra}</g></g>
  );
  return (
    <g transform="translate(0 299)">
      <g className="walk" style={{ animationDuration: `${dur}s`, animationDelay: `${delay}s` }}>
        <g transform={`scale(${scale * 1.4})`} strokeOpacity={0.75} strokeLinecap="round" strokeLinejoin="round" fill="rgb(var(--c-surface))">
          {limb("leg-b", 2.5, -22, "M0,0 L1,11 L0,21 H4")}
          {limb("leg-a", -10, -40, "M0,0 L-1.5,9 L0,17", <circle cx={0} cy={18.6} r={1.4} />)}
          <g className="bob">
            <path d="M-10,-41 H10 L6.5,-25 H-6.5 Z" />
            <path d="M-4.5,-25 H4.5 V-21.5 H-4.5 Z" />
            <circle cx={0} cy={-35} r={1.6} fill="currentColor" stroke="none" className="twinkle" />
            <path d="M0,-41 V-44" />
            <rect x={-6} y={-56} width={12} height={12} rx={4} />
            <rect x={-1} y={-52.5} width={6.5} height={3.2} rx={1.6} fill="currentColor" stroke="none" opacity={0.7} />
          </g>
          {limb("leg-a", -2.5, -22, "M0,0 L1,11 L0,21 H4")}
          {limb("leg-b", 10, -40, "M0,0 L1.5,9 L0,17", <circle cx={0} cy={18.6} r={1.4} />)}
        </g>
      </g>
    </g>
  );
}
