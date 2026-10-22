import { Link } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import { cn } from "@/lib/cn";
import { C } from "@/lib/theme";
import { ZoneBar, zoneOf } from "@/components/FearGreedGauge";
import { useDailyPosts } from "@/hooks/useDailyPosts";
import { useSectionPosts } from "@/hooks/useSectionPosts";
import { useSectorSentiment } from "@/hooks/useSectorSentiment";
import { XFeedCard } from "@/components/XFeed";
import { useThemePosts } from "@/hooks/useThemes";
import { useWeeklyPosts } from "@/hooks/useWeekly";
import { isNote, weekLabel } from "@/api/endpoints";

// /about: who's behind ARC (profile + a live "Latest from ARC" desk), its X feed, and what ARC publishes.
// The desk reads feeds the site already exports, so the public snapshot needs nothing new; an empty feed hides its row.
const SUB = "https://archresearch.substack.com/p/";
const DAY = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
const day = (d: string) => DAY.format(new Date(`${d}T00:00:00Z`));

const LINKS: [string, string][] = [
  ["castelino.ai", "https://castelino.ai"],
  ["X · @AshleynCas46131", "https://x.com/AshleynCas46131"],
  ["LinkedIn", "https://www.linkedin.com/in/ashleyn-castelino/"],
  ["YouTube", "https://www.youtube.com/@ashleyn4869"],
];

const PUBS: [string, string, string, string][] = [
  ["/updates", "Every weekday", "Memo", "The daily note: five stories, what moved and why it matters."],
  ["/macro#theme", "Weekdays · 08:00 ET", "Theme Charts", "The day's top macro theme in five or six charts."],
  ["/macro", "Daily · 09:30 & 17:00 ET", "Radar", "The week ahead, Fear & Greed, and which sectors are stretched."],
  ["/deep-research", "Sundays", "Deep Research", "The week's 10 to 12 trends, researched in depth."],
  ["/ai/models", "New videos", "AI Models", "Video essays on frontier and open-weight models and the labs behind them."],
  ["/ai/chips", "New videos", "Semis & Chips", "Video essays on GPUs, foundries and the compute supply chain."],
  ["/special-topics", "Occasional", "Special Topics", "Longer dives and presentations."],
];

const AI_LABEL: Record<string, string> = { "ai-models": "AI Models", "semis-chips": "Semis & Chips", "artificial-intelligence-update": "AI Models" };

type Row = { label: string; color: string; when: string; title: string; href: string; image?: string | null; score?: number };

function useDesk(): Row[] {
  const theme = useThemePosts().data?.[0];
  const fg = useSectorSentiment().data?.fear_greed;
  const memo = useDailyPosts().data?.find(isNote);
  const deep = useWeeklyPosts().data?.[0];
  const ai = useSectionPosts().data?.find((p) => p.section in AI_LABEL); // newest first
  const rows: (Row | false | null | undefined)[] = [
    theme && { label: "Theme Charts", color: C.inflation, when: day(theme.date), title: theme.title, href: theme.url, image: theme.image },
    fg && { label: "Radar", color: C.jobs, when: "Today", title: `Fear & Greed: ${zoneOf(fg.score).name}`, href: "/macro#sector-sentiment", score: fg.score },
    memo && { label: "Memo", color: C.accent, when: day(memo.date), title: memo.title, href: memo.url, image: memo.image },
    deep && { label: "Deep Research", color: C.ai, when: weekLabel(deep), title: deep.title, href: deep.url, image: deep.image },
    ai && { label: AI_LABEL[ai.section], color: C.text2, when: `${day(ai.date)}${ai.duration ? ` · ▶ ${Math.round(ai.duration / 60)} min` : ""}`,
      title: ai.title, href: ai.url, image: ai.thumbnail },
  ];
  // every off-site link must be one of our Substack posts
  return rows.filter((r): r is Row => !!r && (r.href.startsWith("/") || r.href.startsWith(SUB)));
}

function DeskRow({ r }: { r: Row }) {
  const body = (
    <>
      {r.score != null ? (
        <span className="grid h-12 w-[76px] place-items-center rounded-md border border-border bg-surface font-serif text-xl font-bold text-accent">{r.score}</span>
      ) : r.image ? (
        <img src={r.image} alt="" loading="lazy" className="h-12 w-[76px] rounded-md border border-border object-cover" />
      ) : (
        <span className="h-12 w-[76px] rounded-md border border-border bg-surface-3" />
      )}
      <span className="min-w-0">
        <span className="block text-[11px] font-bold uppercase tracking-[0.06em]" style={{ color: r.color }}>
          {r.label}<span className="ml-1.5 font-medium normal-case tracking-normal text-muted">{r.when}</span>
        </span>
        <span className="line-clamp-2 text-[13.5px] font-semibold leading-snug text-text">{r.title}</span>
        {r.score != null && <span className="mt-1.5 block"><ZoneBar score={r.score} /></span>}
      </span>
    </>
  );
  const cls = "grid grid-cols-[76px_1fr] items-center gap-3 rounded-[10px] px-2 py-2.5 hover:bg-surface-3";
  return r.href.startsWith("/")
    ? <Link to={r.href} className={cls}>{body}</Link>
    : <a href={r.href} target="_blank" rel="noopener noreferrer" className={cls}>{body}</a>;
}

export default function AboutPage() {
  const desk = useDesk();
  return (
    <div className="space-y-5 p-4 md:p-8">
      <section className={cn("card grid overflow-hidden", desk.length > 0 && "lg:grid-cols-[1.45fr_1fr]")}>
        <div className="p-5 md:px-[30px] md:py-7">
          <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-accent">About</div>
          <div className="mt-3.5 flex items-center gap-3.5 md:gap-[22px]">
            <img src="/team/ashleyn.png" alt="Ashleyn Castelino" width={200} height={200}
              className="h-[120px] w-[120px] shrink-0 rounded-2xl border-2 border-accent/55 object-cover object-[40%_30%] md:h-[200px] md:w-[200px] md:rounded-[28px]" />
            <div className="min-w-0">
              <h1 className="font-serif text-[26px] font-bold leading-tight text-text md:text-[34px]">Ashleyn Castelino</h1>
              <p className="mb-3 mt-1.5 text-[13.5px] text-muted">Analyst · macro &amp; AI research</p>
              <div className="flex flex-wrap gap-2">
                {LINKS.map(([label, href], i) => (
                  <a key={href} href={href} target="_blank" rel="noopener noreferrer"
                    className={cn("inline-flex items-center gap-1 rounded-full border px-3 py-1.5 text-[13px]",
                      i === 0 ? "border-transparent bg-accent font-semibold text-on-accent hover:bg-accent-hover"
                        : "border-border text-text hover:border-accent hover:text-accent")}>
                    {label} <ArrowUpRight className="h-3.5 w-3.5" />
                  </a>
                ))}
              </div>
            </div>
          </div>
          <p className="mb-3 mt-[22px] font-serif text-lg font-semibold leading-snug text-text md:text-[21px]">
            Independent research on macro and AI, published every weekday, with every number checked against its source.
          </p>
          <div className="space-y-2.5 text-[14.5px] leading-relaxed text-text-2">
            <p>
              I do independent research on macroeconomics and AI, from rates, inflation and growth to AI models, chips
              and semiconductors. I started ARC to make that research daily, open and checkable: the data comes straight
              from the source, the reasoning is written out, and the methods are documented on this site.
            </p>
            <p>
              I also build the systems behind it: the AI agents that gather the day's data and write the Daily Update and
              the Sunday deep dive, and the machine-learning models behind them.
            </p>
          </div>
        </div>
        {desk.length > 0 && (
          <aside className="border-t border-border bg-surface-2 px-3 pb-3 pt-5 md:px-[22px] lg:border-l lg:border-t-0">
            <div className="mb-2 flex items-center justify-between px-2">
              <span className="text-[11px] font-bold uppercase tracking-[0.08em] text-accent">Latest from ARC</span>
              <span className="inline-flex items-center gap-1.5 text-[11.5px] text-muted">
                <i className="h-[7px] w-[7px] rounded-full bg-accent ring-[3px] ring-accent/25" />Updated live
              </span>
            </div>
            {desk.map((r) => <DeskRow key={r.label} r={r} />)}
          </aside>
        )}
      </section>

      <XFeedCard />

      <section>
        <h2 className="mb-3 font-serif text-[21px] font-bold text-text">What ARC publishes</h2>
        <div className="grid gap-3.5 md:grid-cols-2 lg:grid-cols-3">
          {PUBS.map(([to, when, name, blurb]) => (
            <Link key={to} to={to} className="card block px-5 py-[18px] transition-shadow hover:shadow-card-hover">
              <div className="text-[11px] font-bold uppercase tracking-[0.08em] text-accent">{when}</div>
              <div className="mt-1 flex justify-between text-base font-bold text-text">
                {name}<ArrowUpRight className="h-3.5 w-3.5 text-muted" />
              </div>
              <p className="mt-1 text-[13px] leading-snug text-muted">{blurb}</p>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
