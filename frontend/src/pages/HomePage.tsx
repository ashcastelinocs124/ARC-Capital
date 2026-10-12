import { useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, ArrowUpRight, Play, Search } from "lucide-react";
import { useDailyPosts } from "@/hooks/useDailyPosts";
import { useWeekly, useWeeklyPosts } from "@/hooks/useWeekly";
import { useSectionPosts } from "@/hooks/useSectionPosts";
import { useVideos } from "@/hooks/useVideos";
import { useModels } from "@/hooks/useModels";
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
function Spark({ values, color = C.accent, dot = true, pad = [46, 14] }: { values: number[]; color?: string; dot?: boolean; pad?: [number, number] }) {
  if (values.length < 2) return null;
  const lo = Math.min(...values), hi = Math.max(...values), [top, bot] = pad;
  const y = (v: number) => top + (1 - (v - lo) / (hi - lo || 1)) * (132 - top - bot);
  const x = (i: number) => 8 + (i * 276) / (values.length - 1);
  return (
    <svg viewBox="0 0 300 132" preserveAspectRatio="none" className="block h-full w-full">
      <polyline fill="none" stroke={color} strokeWidth={2} vectorEffect="non-scaling-stroke" points={values.map((v, i) => `${x(i)},${y(v)}`).join(" ")} />
      {dot && <circle cx={x(values.length - 1)} cy={y(values[values.length - 1])} r={4} fill={color} />}
    </svg>
  );
}

function Big({ value, label }: { value: string; label: string }) {
  return (
    <div className="absolute bottom-2.5 left-3 rounded bg-surface-2/85 px-1.5 py-0.5">
      <div className="num text-[22px] font-bold leading-tight text-text">{value}</div>
      <div className="text-[10.5px] text-muted">{label}</div>
    </div>
  );
}

function Tile({ to, title, blurb, children }: { to: string; title: string; blurb: string; children: ReactNode }) {
  return (
    <Link to={to} className="card group flex w-full flex-col overflow-hidden transition-shadow hover:shadow-card-hover sm:w-[calc(50%-8px)] lg:w-[calc((100%-32px)/3)]">
      <div className="relative h-[180px] overflow-hidden border-b border-border bg-surface-2">{children}</div>
      <div className="px-3.5 pb-3.5 pt-3">
        <div className="text-[14.5px] font-semibold text-text">{title}</div>
        <p className="mt-1 line-clamp-2 min-h-[2.75em] text-xs leading-snug text-muted">{blurb}</p>
      </div>
    </Link>
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
  if (!p) return null;
  return (
    <div className="absolute inset-2.5 rounded-md border border-border bg-surface px-3 py-2.5">
      <div className="text-[8.5px] font-semibold uppercase tracking-[0.08em] text-muted">ARC Daily Note · {short(p.date)}</div>
      <div className="mt-1 line-clamp-2 text-[11px] font-bold leading-tight text-text">{p.title}</div>
      <ol className="mt-1.5 space-y-0.5 text-[9px] text-muted">
        {p.takeaways.slice(0, 3).map((t, i) => (
          <li key={t} className="truncate"><b className="text-accent">{i + 1}</b> {t}</li>
        ))}
      </ol>
    </div>
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

// ── page sections ─────────────────────────────────────────────────────────
function Hero() {
  const daily = useDailyPosts().data?.[0];
  const weekly = useWeeklyPosts().data?.[0];
  const video = useVideos().data?.find((v) => isPost(v.url));
  const models = useModels().data;
  const prob = (id: string) => pct(models?.find((m) => m.id === id)?.prob);
  const growth = (models?.find((m) => m.id === "growth")?.history ?? []).slice(-24).map((h) => h.value);
  const entries: [string, string, string, ReactNode][] = [
    ["/updates", "Daily Memo", "The day's macro in five items, with charts.", <Cover src={daily?.image} />],
    ["/deep-research", "Weekly Deep Dive", "Every Sunday: 10–12 trends, checked against the data.", <Cover src={weekly?.image} />],
    ["/models", "Live models", `Pulse ${prob("growth")} · Pressure ${prob("inflation")} · Sector Sentiment · Cross-Asset`, <Spark values={growth} pad={[18, 18]} />],
    ["/videos", "Videos", "AI updates and special topics, explained on camera.", <Cover src={video?.thumbnail} />],
  ];
  return (
    <section className="card grid gap-8 px-6 py-8 md:grid-cols-[1.2fr_1fr] md:px-11 md:py-10">
      <div className="min-w-0">
        <div className="eyebrow">ARC Research</div>
        <h1 className="mt-4 text-4xl font-semibold leading-[1.03] tracking-[-0.035em] text-text md:text-5xl">
          Macro and AI,<br /><span className="text-accent">explained for everyone.</span>
        </h1>
        <p className="mt-4 max-w-md text-base leading-relaxed text-muted md:text-[17px]">
          A daily memo, a Sunday deep dive and live models on the economy, markets and the AI stack.
        </p>
        <div className="mt-6 flex flex-wrap gap-2.5">
          {daily && isPost(daily.url) ? (
            <a href={daily.url} target="_blank" rel="noopener noreferrer" className="rounded-full bg-accent px-5 py-2 text-[13px] font-semibold text-on-accent hover:bg-accent-hover">Start reading</a>
          ) : (
            <Link to="/updates" className="rounded-full bg-accent px-5 py-2 text-[13px] font-semibold text-on-accent hover:bg-accent-hover">Start reading</Link>
          )}
          <a href={SUBSTACK} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 rounded-full border border-border px-5 py-2 text-[13px] font-semibold text-text hover:border-text">
            Subscribe <ArrowUpRight className="h-3.5 w-3.5" />
          </a>
        </div>
        {video && (
          <a href={video.url} target="_blank" rel="noopener noreferrer" className="group mt-7 flex items-center gap-3 text-[13px]">
            <span className="aspect-video w-24 shrink-0 overflow-hidden rounded-md"><Cover src={video.thumbnail} /></span>
            <span>
              <span className="block font-semibold text-text group-hover:text-accent">{video.title}</span>
              <span className="text-muted">Latest video{video.duration ? ` · ${clock(video.duration)}` : ""} ↗</span>
            </span>
          </a>
        )}
      </div>
      <div className="flex flex-col gap-3">
        {entries.map(([to, title, blurb, thumb]) => (
          <Link key={to} to={to} className="card group flex items-center gap-3.5 px-3.5 py-3 transition-shadow hover:shadow-card-hover">
            <span className="h-[54px] w-[88px] shrink-0 overflow-hidden rounded-md border border-border bg-surface-2">{thumb}</span>
            <span className="min-w-0 flex-1">
              <span className="block text-[15px] font-semibold text-text">{title}</span>
              <span className="block text-[12.5px] leading-snug text-muted">{blurb}</span>
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

function Sections() {
  const n = useVideos().data?.length;
  return (
    <section>
      <Heading n="01" kicker="Browse by section" title="Everything on ARC Research, at a glance." />
      <div className="mt-4 flex flex-wrap justify-center gap-4">
        <Tile to="/models" title="Models" blurb="Pulse, Pressure and the market signals, updated live."><ModelsVis /></Tile>
        <Tile to="/updates" title="Memo" blurb="The daily note: five ranked items with charts."><MemoVis /></Tile>
        <Tile to="/deep-research" title="Deep Research" blurb="Sunday deep dive: the week in 10–12 trends."><DeepVis /></Tile>
        <Tile to="/videos" title="Videos" blurb={`${n ? `${n} videos · ` : ""}AI Update and Special Topics.`}><VideosVis /></Tile>
        <Tile to="/agents" title="Agents" blurb="The AI desk behind every memo."><AgentsVis /></Tile>
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
      <Hero />
      <StartHere />
      <Sections />
      <ResearchIndex />
      <CtaBand />
    </div>
  );
}
