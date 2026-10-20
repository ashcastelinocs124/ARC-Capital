import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, ArrowUpRight, Search } from "lucide-react";
import { useDailyPosts } from "@/hooks/useDailyPosts";
import { useWeeklyPosts } from "@/hooks/useWeekly";
import { isNote, weekLabel } from "@/api/endpoints";
import { useSectionPosts } from "@/hooks/useSectionPosts";
import { useVideos } from "@/hooks/useVideos";
import { useXFeed } from "@/hooks/useXFeed";
import { FollowOnX, XStrip } from "@/components/XFeed";
import { useSectorSentiment } from "@/hooks/useSectorSentiment";
import { useWeekAhead } from "@/hooks/useWeekAhead";
import { clock } from "@/pages/VideosPage";
import { cn } from "@/lib/cn";
import { CircuitTraces, Skyline } from "@/components/SplashArt";
import { AgentsArt, DeepArt, DotMatrix, MemoArt, VideosArt } from "@/components/SectionArt";

// The home page: an overview of everything on the site (layout after map.damnang.com).
// Built only from data the other pages already fetch, so the static site needs no new exports.

const SUBSTACK = "https://archresearch.substack.com/";
const isPost = (url: string) => url.startsWith(`${SUBSTACK}p/`); // every rendered feed link must be a post
const short = (d: string) => new Date(`${d}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });

const Cover = ({ src }: { src: string | null | undefined }) =>
  src ? <img src={src} alt="" loading="lazy" className="h-full w-full object-cover" /> : <div className="h-full w-full bg-gradient-to-br from-accent-soft-2 via-accent to-accent-hover" />;

// The hero's green line rolls through these. All sit in one grid cell, so the
// longest sets the size and nothing below jumps.
const TAGLINES = ["on the forces moving markets.", "charted every day.", "checked against the data."];

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

// ── page sections ─────────────────────────────────────────────────────────
// Full-screen opener (after semianalysis.com): traces draw, the logo and name rise, and the
// hero card waits below the fold. 10rem ≈ top bar + tabs + page padding.

function Splash() {
  return (
    <section className="card relative flex min-h-[calc(100svh-10rem)] lg:min-h-[calc(100svh-9rem)] flex-col items-center justify-center gap-2 overflow-hidden">
      <CircuitTraces />
      <Skyline />
      <img src="/arc-logo.png" alt="" className="logo-in logo-img relative splash-logo h-56 w-auto md:h-80" style={{ animationDelay: "0.1s" }} />
      <span className="rise relative text-xl font-semibold tracking-[-0.02em] text-text md:text-2xl" style={{ animationDelay: "0.7s" }}>
        ARC <span className="text-accent">Research</span>
      </span>
      <span className="rise relative -mt-1 text-xl font-semibold tracking-[-0.02em] text-text md:text-2xl" style={{ animationDelay: "0.8s" }}>
        Global Macro &amp; AI <span className="text-accent">Research</span>
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
  const daily = useDailyPosts().data?.find(isNote);
  const weekly = useWeeklyPosts().data?.[0];
  const video = useVideos().data?.find((v) => isPost(v.url));
  const fg = useSectorSentiment().data?.fear_greed;
  const entries: [string, string, string, ReactNode][] = [
    ["/updates", "Daily Memo", "The day's macro in five items, with charts.", <Cover src={daily?.image} />],
    ["/deep-research", "Weekly Deep Dive", "Every Sunday: 10–12 trends, checked against the data.", <Cover src={weekly?.image} />],
    ["/macro", "Radar", `The week ahead · Fear & Greed ${fg ? `${fg.score} · ${fg.zone}` : "and sector sentiment"}`, <Cover src="/thumbs/radar-cover.jpg" />],
    ["/videos", "Videos", "AI updates and special topics, explained on camera.", <Cover src={video?.thumbnail} />],
  ];
  return (
    <section id="hero" className="card grid scroll-mt-4 items-center gap-8 px-6 py-10 md:grid-cols-2 md:gap-12 md:px-14 md:py-16">
      <div className="min-w-0">
        <div className="eyebrow">ARC Research</div>
        <h1 className="mt-4 text-4xl font-semibold leading-[1.03] tracking-[-0.035em] text-text md:text-6xl">
          Independent research<br /><RotatingTagline />
        </h1>
        <p className="mt-5 max-w-xl text-base leading-relaxed text-muted md:text-lg">
          An AI-driven, thematic research platform: a daily memo, a Sunday deep dive and a weekly radar on the economy, markets and the AI stack.
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
  const daily = useDailyPosts().data?.find(isNote);
  const weekly = useWeeklyPosts().data?.[0];
  const video = useVideos().data?.find((v) => isPost(v.url));
  const reads = [
    daily && { url: daily.url, img: daily.image, tag: `Memo · ${short(daily.date)}`, title: daily.title },
    weekly && { url: weekly.url, img: weekly.image, tag: `Deep Dive · ${weekLabel(weekly)}`, title: weekly.title },
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

// Section cards (after semianalysis.com's tool cards): line art, the name and one fact in mono. A light
// moves from one card to the next on its own, redrawing each card's art.
function Sections() {
  const wa = useWeekAhead().data;
  const deep = useWeeklyPosts().data?.find((p) => p.week); // a weekly report, not a listed extra
  const n = useVideos().data?.length;
  const cards: [string, string, string, ReactNode, string?][] = [
    ["/macro", "Radar", wa ? `Week of ${short(wa.week_start)}` : "The week ahead", <DotMatrix value={wa?.events.length} />, "EVENTS THIS WEEK"],
    ["/updates", "Memo", "Five items, every weekday", <MemoArt />],
    ["/deep-research", "Deep Research", deep?.takeaways.length ? `${weekLabel(deep)} · ${deep.takeaways.length} trends` : "10–12 trends, every Sunday", <DeepArt />],
    ["/videos", "Videos", n ? `${n} videos on camera` : "Explained on camera", <VideosArt />],
    ["/agents", "Agents", "How the desk is built", <AgentsArt />],
  ];
  const [lit, setLit] = useState(0);
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const t = setInterval(() => setLit((i) => (i + 1) % cards.length), 2400);
    return () => clearInterval(t);
  }, [cards.length]);
  return (
    <section>
      <Heading n="01" kicker="Browse by section" title="Everything on ARC Research, at a glance." />
      <div className="mt-4 grid gap-3.5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        {cards.map(([to, title, sub, art, tag], i) => (
          <Link key={to} to={to}
            className={cn("group flex flex-col overflow-hidden rounded-[10px] border bg-surface-2 transition-colors hover:border-border-strong", i === lit ? "sec-lit border-border-strong" : "border-border")}>
            <span className="relative aspect-[16/10] sm:aspect-square">
              <span className="absolute inset-0">{art}</span>
              {tag && <span className="absolute bottom-2.5 right-3 font-mono text-[10px] tracking-[0.1em] text-muted">{tag}</span>}
            </span>
            <span className="px-[18px] pb-[18px] pt-4">
              <span className="block text-lg font-semibold tracking-[-0.01em] text-text">{title}</span>
              <span className="mt-1.5 block font-mono text-[12.5px] text-muted">{sub}</span>
            </span>
          </Link>
        ))}
      </div>
    </section>
  );
}

type Kind = "memo" | "charts" | "deep" | "ai" | "special" | "video";
const KINDS: [Kind, string][] = [["memo", "Memo"], ["charts", "Charts"], ["deep", "Deep Dive"], ["ai", "AI"], ["special", "Special Topics"], ["video", "Videos"]];
const SECTION_KIND: Record<string, Kind> = { "ai-models": "ai", "semis-chips": "ai", "artificial-intelligence-update": "ai", "special-topics": "special" };
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
    daily?.forEach((p) => add({ url: p.url, title: p.title, date: p.date, when: short(p.date), image: p.image, duration: null }, isNote(p) ? "memo" : "charts"));
    weekly?.forEach((p) => add({ url: p.url, title: p.title, date: p.end, when: weekLabel(p), image: p.image, duration: null }, "deep"));
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
      <Heading n="03" kicker="Research index" title="All research" />
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

function LatestOnX() {
  const posts = useXFeed().data ?? [];
  if (!posts.length) return null;
  return (
    <section aria-label="Latest on X">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <Heading n="02" kicker="On X · @AshleynCas46131" title="Latest on X" />
        <FollowOnX />
      </div>
      <div className="mt-4"><XStrip posts={posts} /></div>
    </section>
  );
}

function CtaBand() {
  return (
    <section className="flex flex-col gap-5 rounded-[10px] bg-text px-6 py-9 text-surface md:flex-row md:items-center md:justify-between md:px-11">
      <div>
        <div className="text-[11px] font-semibold uppercase tracking-[0.06em] opacity-60">Go deeper</div>
        <h2 className="mt-2 text-2xl font-semibold tracking-[-0.025em] md:text-[28px]">The week ahead is on Radar.<br />The research goes deeper.</h2>
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
      <LatestOnX />
      <ResearchIndex />
      <CtaBand />
    </div>
  );
}
