// Line art for the home page's "Browse by section" cards (after semianalysis.com's tool cards):
// thin isometric drawings and a glowing dot-matrix number. When their card (a `group`) has `.sec-lit`
// the lines turn green and redraw (index.css). Strokes are inherited from the <svg>, so each shape
// sets only its fill; every stroked shape has pathLength={1} for the redraw.

type Pt = [number, number];
type Iso = (x: number, y: number, z?: number) => Pt;
// x runs down-right, y down-left, z up
const iso = (cx: number, cy: number, s: number): Iso => (x, y, z = 0) => [cx + (x - y) * 0.866 * s, cy + (x + y) * 0.5 * s - z * s];
const pts = (a: Pt[]) => a.map((p) => p.map((v) => v.toFixed(1)).join(",")).join(" ");

function Art({ children }: { children: React.ReactNode }) {
  return (
    <svg viewBox="0 0 300 300" className="sec-art h-full w-full fill-none stroke-muted-2 transition-[stroke] duration-300 group-[.sec-lit]:stroke-accent" strokeLinejoin="round" aria-hidden>
      {children}
    </svg>
  );
}

// A box: the two front faces and the top, filled so a layer drawn later hides the one below.
function Slab({ P, x = 0, y = 0, w, d, z, h }: { P: Iso; x?: number; y?: number; w: number; d: number; z: number; h: number }) {
  const faces = [
    [P(x + w, y, z + h), P(x + w, y + d, z + h), P(x + w, y + d, z), P(x + w, y, z)],
    [P(x, y + d, z + h), P(x + w, y + d, z + h), P(x + w, y + d, z), P(x, y + d, z)],
    [P(x, y, z + h), P(x + w, y, z + h), P(x + w, y + d, z + h), P(x, y + d, z + h)],
  ];
  return <>{faces.map((f, i) => <polygon key={i} points={pts(f)} pathLength={1} className="fill-surface-2" strokeWidth={1.1} />)}</>;
}

const Line = ({ a, b, w = 1 }: { a: Pt; b: Pt; w?: number }) => <line x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} pathLength={1} strokeWidth={w} />;

// Memo: five sheets, the top one with a chart line and three rows of text.
export function MemoArt() {
  const P = iso(150, 118, 52), z = 0.84;
  const chart: Pt[] = [[0.3, 0.25], [0.6, 0.5], [0.9, 0.35], [1.2, 0.7], [1.5, 0.6], [1.9, 0.95]];
  return (
    <Art>
      {[0, 1, 2, 3, 4].map((i) => <Slab key={i} P={P} w={2.2} d={1.6} z={i * 0.2} h={0.04} />)}
      <polyline points={pts(chart.map(([x, h]) => P(x, 0.3 + h * 0.6, z)))} pathLength={1} strokeWidth={1.4} />
      {[1.0, 1.2, 1.4].map((y) => <Line key={y} a={P(0.3, y, z)} b={P(y === 1.4 ? 1.2 : 1.9, y, z)} />)}
    </Art>
  );
}

// Deep Research: five desks stacked, three lights on each.
export function DeepArt() {
  const P = iso(150, 140, 40);
  return (
    <Art>
      {[0, 1, 2, 3, 4].map((i) => (
        <g key={i}>
          <Slab P={P} w={2.4} d={2.4} z={i * 0.5} h={0.32} />
          {[0, 1, 2].map((k) => { const c = P(2.4, 0.5 + k * 0.55, i * 0.5 + 0.16); return <circle key={k} cx={c[0]} cy={c[1]} r={2.6} pathLength={1} />; })}
        </g>
      ))}
      {[[0.9, 0.6], [1.4, 0.6], [0.9, 1.1], [1.4, 1.1]].map(([x, y]) => (
        <polygon key={`${x}${y}`} points={pts([P(x, y, 2.32), P(x + 0.38, y, 2.32), P(x + 0.38, y + 0.38, 2.32), P(x, y + 0.38, 2.32)])} pathLength={1} />
      ))}
    </Art>
  );
}

// Videos: a screen on a stand with a play button and a part-watched progress bar.
export function VideosArt() {
  const P = iso(150, 150, 46), y = 0.7;
  return (
    <Art>
      <Slab P={P} w={2.6} d={1.4} z={0} h={0.12} />
      <Line a={P(1.3, y, 0.12)} b={P(1.3, y, 0.9)} w={1.1} />
      <polygon points={pts([P(0.2, y, 0.9), P(2.4, y, 0.9), P(2.4, y, 2.4), P(0.2, y, 2.4)])} pathLength={1} className="fill-surface-2" strokeWidth={1.1} />
      <polygon points={pts([P(1.1, y, 1.35), P(1.1, y, 1.95), P(1.6, y, 1.65)])} pathLength={1} strokeWidth={1.3} />
      <Line a={P(0.4, y, 1.05)} b={P(2.2, y, 1.05)} />
      <line x1={P(0.4, y, 1.05)[0]} y1={P(0.4, y, 1.05)[1]} x2={P(1.1, y, 1.05)[0]} y2={P(1.1, y, 1.05)[1]} pathLength={1} className="stroke-accent" strokeWidth={1.6} />
    </Art>
  );
}

// Agents: a board with a grid; agents are pins wired to the orchestrator in the middle.
export function AgentsArt() {
  const P = iso(150, 135, 40), top = 0.14;
  const hub: Pt = [1.6, 1.6];
  const nodes: Pt[] = [hub, [0.5, 0.6], [2.7, 0.5], [2.8, 2.2], [0.6, 2.6], [1.7, 2.9]];
  const tall = [1.6, 1.1, 0.9, 1.0, 0.8, 0.7];
  return (
    <Art>
      <Slab P={P} w={3.2} d={3.2} z={0} h={top} />
      {[1.07, 2.13].map((k) => (
        <g key={k}><Line a={P(k, 0, top)} b={P(k, 3.2, top)} w={0.6} /><Line a={P(0, k, top)} b={P(3.2, k, top)} w={0.6} /></g>
      ))}
      {nodes.slice(1).map(([x, y]) => (
        <path key={`${x}${y}`} d={`M${P(...hub, top)} Q${P((hub[0] + x) / 2 + 0.3, (hub[1] + y) / 2 - 0.3, top)} ${P(x, y, top)}`} pathLength={1} strokeWidth={0.9} />
      ))}
      {nodes.map(([x, y], i) => {
        const b = P(x, y, top), t = P(x, y, top + tall[i]);
        return (
          <g key={i}>
            <Line a={b} b={t} />
            <ellipse cx={b[0]} cy={b[1]} rx={4} ry={2.2} pathLength={1} strokeWidth={0.8} />
            <ellipse cx={t[0]} cy={t[1]} rx={5} ry={3} pathLength={1} className="fill-surface-2" />
          </g>
        );
      })}
    </Art>
  );
}

// 5×7 dot font
const FONT: Record<string, string[]> = {
  "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
  "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
  "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
  "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
  "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
  "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
  "6": ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
  "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
  "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
  "9": ["01110", "10001", "10001", "01111", "00001", "00010", "01100"],
};

// A square field of dim dots fading out from the middle, with `value` lit and glowing in it; under
// `.sec-lit` the lit dots switch on left to right. Without a value (still loading) it's just the field.
export function DotMatrix({ value }: { value?: number }) {
  const digits = value == null ? "" : String(value);
  const width = digits.length * 6 - 1, n = Math.max(22, width + 10), cell = 300 / n;
  const x0 = Math.floor((n - width) / 2), y0 = Math.floor((n - 7) / 2);
  const lit = new Set<number>();
  [...digits].forEach((d, k) => FONT[d].forEach((row, r) => [...row].forEach((b, c) => b === "1" && lit.add((y0 + r) * n + x0 + k * 6 + c))));
  let seed = 7;
  const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647; // fixed seed: the same field every render
  const dots = [];
  for (let r = 0; r < n; r++)
    for (let c = 0; c < n; c++) {
      const on = lit.has(r * n + c), far = Math.hypot(c - n / 2 + 0.5, r - n / 2 + 0.5) / (n / 2);
      const o = on ? 1 : Math.max(0, (1 - far) * 0.32 * (0.35 + rnd()));
      if (o < 0.03) continue;
      dots.push(
        <rect key={r * n + c} x={c * cell + 1.6} y={r * cell + 1.6} width={cell - 3.2} height={cell - 3.2} rx={1.6}
          className={on ? "dot-on fill-accent" : "fill-accent"} opacity={o} filter={on ? "url(#dot-glow)" : undefined}
          style={on ? { animationDelay: `${(c - x0) * 0.025}s` } : undefined} />,
      );
    }
  return (
    <svg viewBox="0 0 300 300" className="h-full w-full" aria-hidden>
      <defs>
        <filter id="dot-glow"><feGaussianBlur stdDeviation="1.6" result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
      </defs>
      {dots}
    </svg>
  );
}
