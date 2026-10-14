import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, ArrowUpRight, Play, Search } from "lucide-react";
import { useDailyPosts } from "@/hooks/useDailyPosts";
import { useWeekly, useWeeklyPosts } from "@/hooks/useWeekly";
import { useSectionPosts } from "@/hooks/useSectionPosts";
import { useVideos } from "@/hooks/useVideos";
import { useModels } from "@/hooks/useModels";
import { useWeekAhead } from "@/hooks/useWeekAhead";
import { isWeekly } from "@/api/endpoints";
import { clock } from "@/pages/VideosPage";
import { cn } from "@/lib/cn";
import { CircuitTraces, Skyline } from "@/components/SplashArt";

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

function MacroVis() {
  const wa = useWeekAhead().data;
  return (
    <>
      <img src="/thumbs/radar-cover.jpg" alt="" loading="lazy" className="h-full w-full object-cover" />
      {wa && <Big value={`${wa.events.length} events`} label={`Week of ${short(wa.week_start)}`} />}
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
          Independent research<br /><RotatingTagline />
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
