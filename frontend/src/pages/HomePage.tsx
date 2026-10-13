import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, ArrowUpRight, Play, Search } from "lucide-react";
import { useDailyPosts } from "@/hooks/useDailyPosts";
import { useWeekly, useWeeklyPosts } from "@/hooks/useWeekly";
import { useSectionPosts } from "@/hooks/useSectionPosts";
import { useVideos } from "@/hooks/useVideos";
import { useModels } from "@/hooks/useModels";
import { useWeekAhead } from "@/hooks/useWeekAhead";
import type { WeekKind } from "@/api/types";
import { isWeekly } from "@/api/endpoints";
import { clock } from "@/pages/VideosPage";
import { C } from "@/lib/theme";
import { cn } from "@/lib/cn";

// The home page: an overview of everything on the site (layout after map.damnang.com).
// Built only from data the other pages already fetch, so the static site needs no new exports.

const SUBSTACK = "https://archresearch.substack.com/";
const isPost = (url: string) => url.startsWith(`${SUBSTACK}p/`); // every rendered feed link must be a post
const short = (d: string) => new Date(`${d}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });
const weekNo = (w: string) => `Week ${Number(w.split("W")[1])}`;
const pct = (p: number | undefined) => (p == null ? "–" : `${Math.round(p * 100)}%`);

// ── small drawing helpers ────────────────────────────────────────────────
function Big({ value, label }: { value: string; label: string }) {
  return (
    <div className="absolute bottom-2.5 left-3 rounded bg-surface-2/85 px-1.5 py-0.5">
      <div className="num text-[22px] font-bold leading-tight text-text">{value}</div>
      <div className="text-[10.5px] text-muted">{label}</div>
    </div>
  );
}

const Cover = ({ src }: { src: string | null | undefined }) =>
  src ? <img src={src} alt="" loading="lazy" className="h-full w-full object-cover" /> : <div className="h-full w-full bg-gradient-to-br from-accent-soft-2 via-accent to-accent-hover" />;

// ── section visuals ───────────────────────────────────────────────────────
function ModelsVis() {
  const pulse = useModels().data?.find((m) => m.id === "growth");
  return (
    <>
      <img src="/thumbs/models-cover.jpg" alt="" loading="lazy" className="h-full w-full object-cover object-top" />
      <Big value={pct(pulse?.prob)} label={`Pulse · ${pulse?.prob_label ?? "P(expansion)"}`} />
    </>
  );
}

function MemoVis() {
  const p = useDailyPosts().data?.[0];
  return (
    <>
      <img src="/thumbs/memo-cover.jpg" alt="" loading="lazy" className="h-full w-full object-cover" />
      {p && <Big value={short(p.date)} label="Latest daily note" />}
    </>
  );
}

// this week's calendar: one stacked bar per weekday, coloured by release type (same colours as /macro)
const WEEK_KINDS: [WeekKind, string][] = [["other", C.muted2], ["jobs", C.jobs], ["inflation", C.inflation], ["earnings", C.earnings], ["ai", C.ai]];
function MacroVis() {
  const wa = useWeekAhead().data;
  if (!wa) return null;
  const days = Array.from({ length: 5 }, (_, i) => {
    const d = new Date(`${wa.week_start}T12:00:00`);
    d.setDate(d.getDate() + i);
    return d.toISOString().slice(0, 10);
  });
  const counts = days.map((d) => WEEK_KINDS.map(([k]) => wa.events.filter((e) => e.date === d && e.kind === k).length));
  const max = Math.max(1, ...counts.map((c) => c.reduce((a, b) => a + b, 0)));
  const total = counts.flat().reduce((a, b) => a + b, 0);
  return (
    <>
      <svg viewBox="0 0 300 180" className="block h-full w-full">
        {counts.map((c, i) => {
          let y = 150;
          return (
            <g key={i}>
              {c.map((n, k) => {
                const h = (n / max) * 120;
                y -= h;
                return n ? <rect key={k} x={118 + i * 36} y={y} width={24} height={h} fill={WEEK_KINDS[k][1]} rx={2} /> : null;
              })}
              <text x={130 + i * 36} y={166} textAnchor="middle" fontSize={10} fill={C.muted}>{"MTWTF"[i]}</text>
            </g>
          );
        })}
      </svg>
      <Big value={`${total} events`} label={`Week of ${short(wa.week_start)}`} />
    </>
  );
}

function DeepVis() {
  const p = useWeeklyPosts().data?.[0];
  const rec = useWeekly(null).data;
  const counts = isWeekly(rec) ? rec.counts : null;
  const trends = isWeekly(rec) ? rec.report.sections.length : p?.takeaways.length;
  return (
    <>
      <img src="/thumbs/deep-research-desk.jpg" alt="" loading="lazy" className="h-full w-full object-cover object-top" />
      {p && (
        <Big
          value={weekNo(p.week)}
          label={[trends && `${trends} trends`, counts && `${counts.figures_checked} figures checked`].filter(Boolean).join(" · ") || "Weekly Deep Dive"}
        />
      )}
    </>
  );
}

function VideosVis() {
  const vids = (useVideos().data ?? []).filter((v) => isPost(v.url)).slice(0, 3);
  if (!vids.length) return null;
  const Thumb = ({ v, big }: { v: (typeof vids)[number]; big?: boolean }) => (
    <div className="relative overflow-hidden rounded">
      <Cover src={v.thumbnail} />
      {big && <span className="absolute inset-0 grid place-items-center"><span className="grid h-8 w-8 place-items-center rounded-full bg-black/55 text-white"><Play className="h-3.5 w-3.5 fill-current" /></span></span>}
      {v.duration ? <span className="absolute bottom-1 right-1 rounded bg-black/70 px-1 text-[9.5px] font-semibold text-white">{clock(v.duration)}</span> : null}
    </div>
  );
  return (
    <div className="grid h-full grid-cols-[1.4fr_1fr] gap-1 p-2">
      <Thumb v={vids[0]} big />
      <div className="grid grid-rows-2 gap-1">{vids.slice(1).map((v) => <Thumb key={v.url} v={v} />)}</div>
    </div>
  );
}

function AgentsVis() {
  return <img src="/thumbs/agents-cover.jpg" alt="" loading="lazy" className="h-full w-full object-cover object-top" />;
}

// The hero's green line rolls through these. All sit in one grid cell, so the
// longest sets the size and nothing below jumps.
const TAGLINES = ["explained for everyone.", "charted every day.", "checked against the data."];

function RotatingTagline() {
  const [i, setI] = useState(0);
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const t = setInterval(() => setI((n) => (n + 1) % TAGLINES.length), 1800);
    return () => clearInterval(t);
  }, []);
  return (
    <span className="grid overflow-hidden text-accent">
      <span className="sr-only">{TAGLINES[0]}</span>
      {TAGLINES.map((line, n) => (
        <span
          key={line}
          aria-hidden
          className={cn(
            "col-start-1 row-start-1 transition-all duration-300 ease-out motion-reduce:transition-none",
            n === i ? "translate-y-0 opacity-100" : n === (i + TAGLINES.length - 1) % TAGLINES.length ? "-translate-y-full opacity-0" : "translate-y-full opacity-0",
          )}
        >
          {line}
        </span>
      ))}
    </span>
  );
}

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

function CircuitTraces() {
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

// ── page sections ─────────────────────────────────────────────────────────
// Full-screen opener (after semianalysis.com): traces draw, the logo and name rise, and the
// hero card waits below the fold. 10rem ≈ top bar + tabs + page padding.
// A line-drawn New York skyline along the bottom of the splash: outlines draw in like the
// traces, then a few windows twinkle. Landmarks are hand-placed; the filler blocks come from a
// seeded random so the skyline is the same on every load.
const LANDMARKS: [number, number, string][] = [
  // [left, right, path] in a 1200×300 box, ground at y=300
  [328, 372, "M330,300 V130 H338 V112 L344,104 L350,88 L356,104 L362,112 V130 H370 V300 M350,88 V52"], // Chrysler
  [512, 608, "M515,300 V185 H530 V135 H543 V105 H553 V88 H557 V58 L560,44 L563,58 V88 H567 V105 H577 V135 H590 V185 H605 V300"], // Empire State
  [766, 834, "M770,300 V245 L784,92 H816 L830,245 V300 M800,92 V30"], // One World Trade Center
];

function Skyline() {
  const { blocks, windows } = useMemo(() => {
    let s = 7;
    const rnd = () => ((s = (s * 16807) % 2147483647) / 2147483647);
    const blocks: string[] = [], windows: [number, number, number][] = [];
    for (let x = 0; x < 1200; ) {
      const hit = LANDMARKS.find(([l, r]) => x + 20 > l && x < r);
      if (hit) { x = hit[1] + 4; continue; }
      const w = 30 + rnd() * 50, h = 100 + rnd() * 180, top = 300 - h;
      blocks.push(rnd() < 0.3 ? `M${x},300 V${top + 10} H${x + w * 0.3} V${top} H${x + w * 0.7} V${top + 10} H${x + w} V300` : `M${x},300 V${top} H${x + w} V300`);
      for (let k = 0; k < 5; k++) if (rnd() < 0.6) windows.push([x + 5 + rnd() * (w - 12), top + 16 + rnd() * (h - 30), rnd()]);
      x += w + 2 + rnd() * 6;
    }
    return { blocks, windows };
  }, []);
  const draw = (i: number) => ({ animationDelay: `${BG + 0.2 + (i % 12) * 0.06}s`, animationDuration: "2.2s" });
  return (
    <svg aria-hidden viewBox="0 0 1200 300" preserveAspectRatio="xMidYMax slice" overflow="visible" className="pointer-events-none absolute inset-x-0 bottom-0 h-[68%] w-full text-accent" fill="none" stroke="currentColor" strokeWidth={1.2}>
      {blocks.map((d, i) => <path key={i} d={d} pathLength={1} className="trace" strokeOpacity={0.28} style={draw(i)} />)}
      {/* landmarks stretched 1.4× up from the ground line (y' = 1.4y − 120 keeps y=300 fixed) */}
      <g transform="translate(0 -120) scale(1 1.4)">
        {LANDMARKS.map(([, , d], i) => <path key={i} d={d} pathLength={1} vectorEffect="non-scaling-stroke" className="trace" strokeOpacity={0.55} style={draw(i)} />)}
      </g>
      {windows.map(([x, y, r], i) => (
        <rect key={i} x={x} y={y} width={4} height={5} fill="currentColor" stroke="none" className="twinkle" style={{ animationDelay: `${BG + 2 + r * 6}s`, animationDuration: `${3 + r * 4}s` }} />
      ))}
      {CHIPS.map(([x, y, s], i) => <Chip key={i} x={x} y={y} s={s} delay={BG + 1.4 + i * 0.15} />)}
      <g className="rise" style={{ animationDelay: `${BG + 1.6}s` }}>{ROBOTS.map(([dur, delay, scale], i) => <Robot key={i} dur={dur} delay={delay} scale={scale} />)}</g>
      <line x1={0} y1={299.5} x2={1200} y2={299.5} strokeOpacity={0.4} />
    </svg>
  );
}

// Chips float over the skyline; robots walk along the street (both drawn in the skyline's box).
const CHIPS: [number, number, number][] = [[60, 40, 28], [170, 70, 34], [290, 22, 24], [420, 30, 26], [470, 95, 20], [780, 40, 40], [800, 130, 22], [900, 30, 28], [1010, 92, 30], [1130, 50, 34]]; // x, y, size
const ROBOTS: [number, number, number][] = [[38, 0, 1.1], [52, -20, 0.9], [45, -34, 1.3], [60, -8, 1], [34, -16, 1.05], [48, -42, 1.2], [56, -28, 0.85], [42, -6, 1.15], [64, -50, 0.95], [36, -26, 1.25], [50, -12, 1], [58, -38, 1.1]]; // seconds to cross, delay, scale

function Chip({ x, y, s, delay }: { x: number; y: number; s: number; delay: number }) {
  const pins = [0.2, 0.4, 0.6, 0.8].map((f) => f * s);
  return (
    <g className="rise" style={{ animationDelay: `${delay}s` }}>
      <g className="float" style={{ animationDelay: `${delay}s` }}>
        <g transform={`translate(${x - s / 2} ${y - s / 2})`} strokeOpacity={0.6}>
          <rect width={s} height={s} rx={3} fill="rgb(var(--c-surface))" />
          <rect x={s * 0.28} y={s * 0.28} width={s * 0.44} height={s * 0.44} rx={1.5} className="chip-die" fill="currentColor" stroke="none" />
          {pins.map((p) => (
            <path key={p} d={`M${p},0 v-5 M${p},${s} v5 M0,${p} h-5 M${s},${p} h5`} />
          ))}
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
        <g transform={`scale(${scale})`} strokeOpacity={0.75} strokeLinecap="round" strokeLinejoin="round" fill="rgb(var(--c-surface))">
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

function Splash() {
  return (
    <section className="card relative flex min-h-[calc(100svh-10rem)] lg:min-h-[calc(100svh-9rem)] flex-col items-center justify-center gap-2 overflow-hidden">
      <CircuitTraces />
      <Skyline />
      <img src="/arc-logo.png" alt="" className="logo-in logo-img relative splash-logo h-48 w-auto md:h-72" style={{ animationDelay: "0.1s" }} />
      <span className="rise relative text-xl font-semibold tracking-[-0.02em] text-text md:text-2xl" style={{ animationDelay: "0.7s" }}>
        ARC <span className="text-accent">Research</span>
      </span>
      <a href={SUBSTACK} target="_blank" rel="noopener noreferrer" className="rise relative mt-5 inline-flex items-center gap-1.5 rounded-full bg-text px-7 py-3 text-base font-semibold text-surface hover:bg-text-2" style={{ animationDelay: "0.9s" }}>
        Newsletter <ArrowUpRight className="h-4 w-4" />
      </a>
      <a href="#hero" className="rise absolute bottom-6 text-[12px] font-semibold uppercase tracking-[0.08em] text-muted hover:text-text" style={{ animationDelay: "2.6s" }}>
        Scroll <span className="inline-block animate-bounce">↓</span>
      </a>
    </section>
  );
}

function Hero() {
  const daily = useDailyPosts().data?.[0];
  const weekly = useWeeklyPosts().data?.[0];
  const video = useVideos().data?.find((v) => isPost(v.url));
  const models = useModels().data;
  const prob = (id: string) => pct(models?.find((m) => m.id === id)?.prob);
  const entries: [string, string, string, ReactNode][] = [
    ["/updates", "Daily Memo", "The day's macro in five items, with charts.", <Cover src={daily?.image} />],
    ["/deep-research", "Weekly Deep Dive", "Every Sunday: 10–12 trends, checked against the data.", <Cover src={weekly?.image} />],
    ["/models", "Live models", `Pulse ${prob("growth")} · Pressure ${prob("inflation")} · Sector Sentiment · Cross-Asset`, <Cover src="/thumbs/live-models.jpg" />],
    ["/videos", "Videos", "AI updates and special topics, explained on camera.", <Cover src={video?.thumbnail} />],
  ];
  return (
    <section id="hero" className="card grid scroll-mt-4 items-center gap-8 px-6 py-10 md:grid-cols-2 md:gap-12 md:px-14 md:py-16">
      <div className="min-w-0">
        <div className="eyebrow">ARC Research</div>
        <h1 className="mt-4 text-4xl font-semibold leading-[1.03] tracking-[-0.035em] text-text md:text-6xl">
          Macro and AI,<br /><RotatingTagline />
        </h1>
        <p className="mt-5 max-w-xl text-base leading-relaxed text-muted md:text-lg">
          A daily memo, a Sunday deep dive and live models on the economy, markets and the AI stack.
        </p>
        <div className="mt-7 flex flex-wrap gap-3">
          {daily && isPost(daily.url) ? (
            <a href={daily.url} target="_blank" rel="noopener noreferrer" className="rounded-full bg-accent px-6 py-2.5 text-sm font-semibold text-on-accent hover:bg-accent-hover">Start reading</a>
          ) : (
            <Link to="/updates" className="rounded-full bg-accent px-6 py-2.5 text-sm font-semibold text-on-accent hover:bg-accent-hover">Start reading</Link>
          )}
          <a href={SUBSTACK} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 rounded-full border border-border px-6 py-2.5 text-sm font-semibold text-text hover:border-text">
            Subscribe <ArrowUpRight className="h-3.5 w-3.5" />
          </a>
        </div>
        {video && (
          <a href={video.url} target="_blank" rel="noopener noreferrer" className="group mt-8 flex items-center gap-3.5 text-sm">
            <span className="aspect-video w-28 shrink-0 overflow-hidden rounded-md"><Cover src={video.thumbnail} /></span>
            <span>
              <span className="block font-semibold text-text group-hover:text-accent">{video.title}</span>
              <span className="text-muted">Latest video{video.duration ? ` · ${clock(video.duration)}` : ""} ↗</span>
            </span>
          </a>
        )}
      </div>
      <div className="flex flex-col gap-3.5">
        {entries.map(([to, title, blurb, thumb]) => (
          <Link key={to} to={to} className="card group flex items-center gap-3 px-3 py-3 transition-shadow md:gap-4 md:px-4 md:py-3.5 hover:shadow-card-hover">
            <span className="h-[54px] w-[84px] shrink-0 md:h-[68px] md:w-[112px] overflow-hidden rounded-md border border-border bg-surface-2">{thumb}</span>
            <span className="min-w-0 flex-1">
              <span className="block text-base font-semibold text-text">{title}</span>
              <span className="block text-[13.5px] leading-snug text-muted">{blurb}</span>
            </span>
            <ArrowRight className="h-4 w-4 shrink-0 text-muted group-hover:text-text" />
          </Link>
        ))}
      </div>
    </section>
  );
}

function Heading({ n, kicker, title }: { n?: string; kicker: string; title: string }) {
  return (
    <div>
      <div className="eyebrow">{n && <span className="mr-2 font-bold text-accent">{n}</span>}{kicker}</div>
      <h2 className="mt-2 text-2xl font-semibold tracking-[-0.025em] text-text md:text-[28px]">{title}</h2>
    </div>
  );
}

function StartHere() {
  const daily = useDailyPosts().data?.[0];
  const weekly = useWeeklyPosts().data?.[0];
  const video = useVideos().data?.find((v) => isPost(v.url));
  const reads = [
    daily && { url: daily.url, img: daily.image, tag: `Memo · ${short(daily.date)}`, title: daily.title },
    weekly && { url: weekly.url, img: weekly.image, tag: `Deep Dive · ${weekNo(weekly.week)}`, title: weekly.title },
    video && { url: video.url, img: video.thumbnail, tag: "Video", title: video.title },
  ].filter((r): r is { url: string; img: string | null; tag: string; title: string } => !!r && isPost(r.url));
  if (!reads.length) return null;
  return (
    <section>
      <Heading kicker="Your first three reads" title="Start with the latest." />
      <div className="mt-4 grid gap-4 md:grid-cols-3">
        {reads.map((r) => (
          <a key={r.url} href={r.url} target="_blank" rel="noopener noreferrer" className="card flex flex-col overflow-hidden transition-shadow hover:shadow-card-hover">
            <span className="aspect-video"><Cover src={r.img} /></span>
            <span className="px-4 pb-4 pt-3">
              <span className="pill">{r.tag}</span>
              <span className="mt-2 block text-base font-semibold leading-snug text-text">{r.title}</span>
            </span>
          </a>
        ))}
      </div>
    </section>
  );
}

// Pinned tab panel (after semianalysis.com): the panel sticks while you scroll through a tall
// track, each step of the scroll selects the next tab, and the bar under it fills.
interface Pane { to: string; title: string; sub: string; blurb: string; points: [string, string][]; vis: ReactNode }

function Sections() {
  const n = useVideos().data?.length;
  const panes: Pane[] = [
    { to: "/macro", title: "Radar", sub: "The week ahead", vis: <MacroVis />,
      blurb: "What's coming: data releases, earnings and AI launches on one timeline, with the consensus for each print.",
      points: [["Data releases", "US, China, Germany, Japan, India"], ["Earnings", "S&P 500 + AI names"], ["AI launches", "New models and reported releases"], ["AI spend", "Ramp AI Index, token share"]] },
    { to: "/models", title: "Models", sub: "Live nowcasts", vis: <ModelsVis />,
      blurb: "Pulse and Pressure read where growth and inflation are heading next month, next to Sector Sentiment, the AI Adoption Index and Cross-Asset Drivers.",
      points: [["Pulse", "P(expansion next month)"], ["Pressure", "P(CPI accelerates)"], ["Sector Sentiment", "11 GICS sectors"], ["Cross-Asset", "What moved stocks and bonds"]] },
    { to: "/updates", title: "Memo", sub: "Every weekday", vis: <MemoVis />,
      blurb: "The daily note: the day's macro in five ranked items, each with a chart, and every number checked against its source.",
      points: [["Five items", "Ranked by what moved"], ["Exhibits", "One chart per item"], ["Checked", "Every figure traced to data"]] },
    { to: "/deep-research", title: "Deep Research", sub: "Every Sunday", vis: <DeepVis />,
      blurb: "The Sunday deep dive: the week in 10–12 trends, each researched by a desk of agents and grilled by an editor.",
      points: [["Trends", "10–12 a week"], ["Desks", "Five research desks"], ["Checked", "Every %, bp and pp"]] },
    { to: "/videos", title: "Videos", sub: n ? `${n} videos` : "On camera", vis: <VideosVis />,
      blurb: "AI Update and Special Topics, explained on camera.",
      points: [["AI Update", "Models, chips, labs"], ["Special Topics", "One idea, in depth"]] },
    { to: "/agents", title: "Agents", sub: "How it's made", vis: <AgentsVis />,
      blurb: "The AI desk behind every memo: what each agent does and how the systems fit together.",
      points: [["Briefings", "The daily Morning Note desk"], ["Weekly", "Lead, desks and editor"]] },
  ];

  const track = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState(0); // 0..panes.length: integer part = tab, fraction = progress through it
  const geometry = () => {
    const el = track.current!, main = el.closest("main")!;
    const total = el.offsetHeight - (el.firstElementChild as HTMLElement).offsetHeight;
    return { main, total, scrolled: main.getBoundingClientRect().top + 16 - el.getBoundingClientRect().top };
  };
  useEffect(() => {
    const main = track.current?.closest("main");
    if (!main) return;
    const onScroll = () => {
      const { total, scrolled } = geometry();
      setPos(Math.min(Math.max(scrolled / total, 0), 0.9999) * panes.length);
    };
    onScroll();
    main.addEventListener("scroll", onScroll, { passive: true });
    return () => main.removeEventListener("scroll", onScroll);
  }, [panes.length]);
  const go = (i: number) => {
    const { main, total, scrolled } = geometry();
    main.scrollTo({ top: main.scrollTop - scrolled + ((i + 0.05) / panes.length) * total, behavior: "smooth" });
  };
  const active = Math.floor(pos);
  const tabRow = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // on a phone the tabs overflow sideways: keep the active one in view
    const row = tabRow.current, tab = row?.children[active] as HTMLElement | undefined;
    if (row && tab) row.scrollTo({ left: tab.offsetLeft - 16, behavior: "smooth" });
  }, [active]);

  return (
    <section>
      <Heading n="01" kicker="Browse by section" title="Everything on ARC Research, at a glance." />
      <div ref={track} className="relative mt-4" style={{ height: `${panes.length * 55 + 60}vh` }}>
        <div className="card sticky top-4 flex h-[calc(100dvh-9rem)] max-h-[640px] flex-col overflow-hidden">
          <div ref={tabRow} className="no-scrollbar flex shrink-0 overflow-x-auto border-b border-border">
            {panes.map((p, i) => (
              <button key={p.to} onClick={() => go(i)} className={cn("relative shrink-0 border-r border-border px-5 py-3 text-left", i === active ? "bg-surface" : "bg-surface-2")}>
                <span className="absolute left-0 top-0 h-0.5 bg-accent" style={{ width: `${i < active ? 100 : i === active ? (pos - active) * 100 : 0}%` }} />
                <span className={cn("block text-[13px] font-semibold", i === active ? "text-text" : "text-muted")}>{p.title}</span>
                <span className={cn("block text-[11px]", i === active ? "text-accent" : "text-muted")}>{p.sub}</span>
              </button>
            ))}
          </div>
          <div className="grid flex-1 overflow-hidden">
            {panes.map((p, i) => (
              <div
                key={p.to}
                aria-hidden={i !== active}
                className={cn(
                  "col-start-1 row-start-1 grid min-h-0 gap-6 p-6 transition-all duration-500 md:grid-cols-[1.1fr_1fr] md:p-10",
                  i === active ? "translate-y-0 opacity-100" : "pointer-events-none translate-y-3 opacity-0",
                )}
              >
                <div className="min-w-0">
                  <div className="eyebrow">{p.sub}</div>
                  <h3 className="mt-2 text-3xl font-semibold tracking-[-0.03em] text-text">{p.title}</h3>
                  <p className="mt-3 max-w-lg text-[15px] leading-relaxed text-muted">{p.blurb}</p>
                  <dl className="mt-5 max-w-lg divide-y divide-border rounded-lg border border-border">
                    {p.points.map(([k, v]) => (
                      <div key={k} className="flex items-center justify-between gap-4 px-3.5 py-2.5 text-[13px]">
                        <dt className="font-semibold text-text">{k}</dt>
                        <dd className="text-right text-muted">{v}</dd>
                      </div>
                    ))}
                  </dl>
                  <Link to={p.to} tabIndex={i === active ? 0 : -1} className="mt-6 inline-flex items-center gap-1.5 rounded-full bg-accent px-5 py-2 text-[13px] font-semibold text-on-accent hover:bg-accent-hover">
                    Open {p.title} <ArrowRight className="h-3.5 w-3.5" />
                  </Link>
                </div>
                <div className="relative hidden min-h-0 overflow-hidden rounded-lg border border-border bg-surface-2 md:block">{p.vis}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

type Kind = "memo" | "deep" | "ai" | "special" | "video";
const KINDS: [Kind, string][] = [["memo", "Memo"], ["deep", "Deep Dive"], ["ai", "AI Update"], ["special", "Special Topics"], ["video", "Videos"]];
const SECTION_KIND: Record<string, Kind> = { "artificial-intelligence-update": "ai", "special-topics": "special" };
interface Item { url: string; title: string; date: string; when: string; image: string | null; kinds: Set<Kind>; duration: number | null }

function useResearch(): Item[] {
  const daily = useDailyPosts().data, weekly = useWeeklyPosts().data, sections = useSectionPosts().data, videos = useVideos().data;
  return useMemo(() => {
    const byUrl = new Map<string, Item>();
    const add = (it: Omit<Item, "kinds">, ...kinds: Kind[]) => {
      if (!isPost(it.url)) return;
      const cur = byUrl.get(it.url) ?? { ...it, kinds: new Set<Kind>() };
      kinds.forEach((k) => cur.kinds.add(k));
      cur.duration ??= it.duration;
      byUrl.set(it.url, cur);
    };
    daily?.forEach((p) => add({ url: p.url, title: p.title, date: p.date, when: short(p.date), image: p.image, duration: null }, "memo"));
    weekly?.forEach((p) => add({ url: p.url, title: p.title, date: p.end, when: weekNo(p.week), image: p.image, duration: null }, "deep"));
    sections?.forEach((p) => {
      const k: Kind[] = [SECTION_KIND[p.section], ...(p.video !== false && p.duration ? (["video"] as Kind[]) : [])].filter(Boolean);
      add({ url: p.url, title: p.title, date: p.date, when: short(p.date), image: p.thumbnail, duration: p.duration }, ...k);
    });
    videos?.forEach((v) => add({ url: v.url, title: v.title, date: v.date, when: short(v.date), image: v.thumbnail, duration: v.duration }, "video"));
    return [...byUrl.values()].sort((a, b) => b.date.localeCompare(a.date));
  }, [daily, weekly, sections, videos]);
}

const KIND_LABEL = Object.fromEntries([...KINDS, ["video", "Video"]]) as Record<Kind, string>;

function ResearchIndex() {
  const items = useResearch();
  const [kind, setKind] = useState<Kind | "all">("all");
  const [q, setQ] = useState("");
  const shown = items.filter((it) => (kind === "all" || it.kinds.has(kind)) && it.title.toLowerCase().includes(q.trim().toLowerCase()));
  if (!items.length) return null;
  const chip = (k: Kind | "all", label: string, count: number) => (
    <button key={k} onClick={() => setKind(k)} className={cn("rounded-full border px-3.5 py-1.5 text-[12.5px]", kind === k ? "border-text bg-text text-surface" : "border-border bg-surface text-text-2 hover:border-text")}>
      {label}<span className={cn("ml-1", kind === k ? "opacity-70" : "text-muted")}>{count}</span>
    </button>
  );
  return (
    <section>
      <Heading n="02" kicker="Research index" title="All research" />
      <div className="mt-4 flex flex-wrap items-center gap-2">
        {chip("all", "All", items.length)}
        {KINDS.map(([k, label]) => chip(k, label, items.filter((it) => it.kinds.has(k)).length))}
        <label className="flex w-full items-center gap-2 rounded-full border border-border bg-surface px-3.5 py-1.5 sm:ml-auto sm:w-56">
          <Search className="h-3.5 w-3.5 text-muted" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search titles…" className="w-full bg-transparent text-[13px] text-text outline-none placeholder:text-muted" />
        </label>
      </div>
      <div className="card mt-3 divide-y divide-border">
        {shown.map((it) => (
          <a key={it.url} href={it.url} target="_blank" rel="noopener noreferrer" className="group grid grid-cols-[80px_1fr] items-center gap-3 px-3 py-3 sm:grid-cols-[110px_1fr_auto] sm:gap-4 sm:px-4">
            <span className="aspect-video overflow-hidden rounded-md"><Cover src={it.image} /></span>
            <span className="min-w-0">
              <span className="inline-block rounded-full border border-border px-2.5 py-0.5 text-[11px] font-semibold text-text-2">
                {[...it.kinds].map((k) => KIND_LABEL[k]).join(" · ")}
              </span>
              <span className="mt-1.5 block truncate text-[14.5px] font-semibold text-text group-hover:text-accent">{it.title}</span>
              <span className="text-xs text-muted sm:hidden">{it.when}</span>
            </span>
            <span className="hidden whitespace-nowrap text-xs text-muted sm:block">
              {it.when}{it.duration ? ` · ${Math.round(it.duration / 60)} min` : ""}
            </span>
          </a>
        ))}
        {!shown.length && (
          <div className="p-7 text-center text-[13px] text-muted">
            No research matches.{" "}
            <button onClick={() => { setKind("all"); setQ(""); }} className="font-semibold text-accent">Reset filters</button>
          </div>
        )}
      </div>
    </section>
  );
}

function CtaBand() {
  return (
    <section className="flex flex-col gap-5 rounded-[10px] bg-text px-6 py-9 text-surface md:flex-row md:items-center md:justify-between md:px-11">
      <div>
        <div className="text-[11px] font-semibold uppercase tracking-[0.06em] opacity-60">Go deeper</div>
        <h2 className="mt-2 text-2xl font-semibold tracking-[-0.025em] md:text-[28px]">The models are open.<br />The research goes deeper.</h2>
        <p className="mt-2 text-sm opacity-70">Every memo and Sunday deep dive, in your inbox.</p>
      </div>
      <a href={SUBSTACK} target="_blank" rel="noopener noreferrer" className="inline-flex shrink-0 items-center gap-1 self-start rounded-full bg-surface px-5 py-2.5 text-[13px] font-semibold text-text md:self-auto">
        Subscribe on Substack <ArrowUpRight className="h-3.5 w-3.5" />
      </a>
    </section>
  );
}

export default function HomePage() {
  return (
    <div className="space-y-11 p-4 md:p-8">
      <Splash />
      <Hero />
      <StartHere />
      <Sections />
      <ResearchIndex />
      <CtaBand />
    </div>
  );
}
