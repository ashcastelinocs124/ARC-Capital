import { useState } from "react";
import { ArrowUpRight, BarChart2, Heart, MessageCircle, Repeat2 } from "lucide-react";
import { X_PROFILE, type XPost, type XReport } from "@/api/endpoints";
import { useXFeed } from "@/hooks/useXFeed";
import { cn } from "@/lib/cn";

// Your posts drawn as an X timeline: Home's "Latest on X" strip (XStrip) and About's "On X" feed (XFeedCard).
// Every link is built by x_feed.py and checked by fetchXFeed: x.com/AshleynCas46131/status/<id>.

const FULL = new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit", month: "short", day: "numeric", year: "numeric" });
const DAY = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" });
// As X writes it: "now", "12m", "4h", then the day ("Oct 20"). The reader's own clock and time zone.
const ago = (at: string) => {
  const t = new Date(at).getTime();
  if (Number.isNaN(t)) return "";
  const m = Math.max(0, Math.round((Date.now() - t) / 60_000));
  return m < 1 ? "now" : m < 60 ? `${m}m` : m < 1440 ? `${Math.floor(m / 60)}h` : DAY.format(t);
};

function XLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={cn("fill-current", className)}>
      <path d="M18.9 2H22l-6.8 7.8L23 22h-6.2l-4.8-6.3L6.4 22H3.3l7.3-8.3L1 2h6.3l4.4 5.8L18.9 2Zm-1.1 18h1.7L6.3 3.9H4.5L17.8 20Z" />
    </svg>
  );
}

export function FollowOnX() {
  return (
    <a href={X_PROFILE} target="_blank" rel="noopener noreferrer"
      className="inline-flex shrink-0 items-center gap-1 rounded-full bg-accent px-4 py-2 text-[13.5px] font-semibold text-on-accent hover:bg-accent-hover">
      Follow on X <ArrowUpRight className="h-3.5 w-3.5" />
    </a>
  );
}

const Chart = ({ src }: { src: string }) => (
  <img src={`${src}?name=small`} alt="Chart attached to the post" loading="lazy"
    className="mt-3 aspect-[16/10] w-full rounded-2xl border border-border bg-white object-cover" />
);

// The ARC report the thread links (a Daily Update, Theme Charts or Deep Dive post on Substack).
function ReportCard({ r }: { r: XReport }) {
  return (
    <a href={r.url} target="_blank" rel="noopener noreferrer"
      className="mt-3 flex items-center gap-3 rounded-2xl border border-border px-3.5 py-3 hover:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent">
      <span className="min-w-0 flex-1">
        <span className="block text-[11px] font-bold uppercase tracking-[0.12em] text-accent">ARC report</span>
        <span className="mt-0.5 block text-[14px] font-semibold leading-snug text-text">{r.title}</span>
        <span className="block text-[12.5px] text-muted">Read it on Substack</span>
      </span>
      <ArrowUpRight className="h-4 w-4 shrink-0 text-muted" aria-hidden="true" />
    </a>
  );
}

// One post as X draws it in a timeline: the post opens it on x.com, the report card opens the report,
// and "Show the full thread" opens the analysis and chart posts under it. The action icons are
// decoration (no counts: the cache only asks X for new posts, so counts would go stale).
function XPostRow({ p, clamp }: { p: XPost; clamp?: boolean }) {
  const [open, setOpen] = useState(false);
  const thread = p.thread ?? [];
  const id = `thread-${p.id}`;
  return (
    <div className="flex h-full min-w-0 gap-3 px-4 py-3">
      <img src="/team/ashleyn.png" alt="" className="h-10 w-10 shrink-0 rounded-full object-cover object-[40%_30%]" />
      <div className="min-w-0 flex-1">
        <a href={p.url} target="_blank" rel="noopener noreferrer" className="block rounded-lg hover:bg-surface-3/45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent">
          <span className="flex items-center gap-1 text-[15px] leading-5">
            <span className="shrink-0 font-bold text-text">Ashleyn Castelino</span>
            <span className="truncate text-muted">@AshleynCas46131</span>
            <span className="text-muted" aria-hidden="true">·</span>
            <time dateTime={p.at} title={FULL.format(new Date(p.at))} className="shrink-0 text-muted">{ago(p.at)}</time>
            <XLogo className="ml-auto h-4 w-4 shrink-0 text-muted" />
          </span>
          <span className={cn("mt-0.5 block whitespace-pre-line break-words text-[15px] leading-[1.45] text-text", clamp && !open && "line-clamp-6")}>{p.text}</span>
          {p.image && <Chart src={p.image} />}
        </a>
        {p.report && <ReportCard r={p.report} />}
        {thread.length > 0 && (
          <>
            <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} aria-controls={id}
              className="mt-3 text-[14px] font-semibold text-accent hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent">
              {open ? "Hide the thread" : `Show the full thread (${thread.length} more ${thread.length === 1 ? "post" : "posts"})`}
            </button>
            {open && (
              <ol id={id} className="mt-2 space-y-3 border-l-2 border-border pl-3">
                {thread.map((t) => (
                  <li key={t.id}>
                    <a href={t.url} target="_blank" rel="noopener noreferrer" className="block rounded-lg hover:bg-surface-3/45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent">
                      <span className="block whitespace-pre-line break-words text-[14.5px] leading-[1.45] text-text">{t.text}</span>
                      {t.image && <Chart src={t.image} />}
                    </a>
                  </li>
                ))}
              </ol>
            )}
          </>
        )}
        <span className="mt-3 flex max-w-[420px] justify-between text-muted" aria-hidden="true">
          <MessageCircle className="h-[18px] w-[18px]" /><Repeat2 className="h-[18px] w-[18px]" />
          <Heart className="h-[18px] w-[18px]" /><BarChart2 className="h-[18px] w-[18px]" />
        </span>
      </div>
    </div>
  );
}

const COLS = ["", "md:grid-cols-1", "md:grid-cols-2", "md:grid-cols-3"];

// Posts side by side, 3 to a row, split by 1px lines (the gap shows the border colour). Blank cells
// finish a short last row so it never shows as a grey block; fewer than 3 posts get their own columns.
function XGrid({ posts }: { posts: XPost[] }) {
  const cols = Math.min(posts.length, 3);
  if (!cols) return null;
  const fill = (cols - (posts.length % cols)) % cols;
  return (
    <div className={cn("grid gap-px bg-border", COLS[cols])}>
      {posts.map((p) => (
        <div key={p.id} className="min-w-0 bg-background"><XPostRow p={p} clamp /></div>
      ))}
      {Array.from({ length: fill }, (_, i) => <div key={`fill-${i}`} aria-hidden="true" className="hidden bg-background md:block" />)}
    </div>
  );
}

// The newest `first` posts, 3 to a row, then "Show more" for up to 9 (the export keeps 10).
function MoreGrid({ posts, first }: { posts: XPost[]; first: number }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <XGrid posts={posts.slice(0, open ? 9 : first)} />
      {posts.length > first && (
        <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}
          className="block w-full border-t border-border px-4 py-3.5 text-left text-[15px] text-accent hover:bg-surface-3/45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent">
          {open ? "Show fewer" : "Show more"}
        </button>
      )}
    </>
  );
}

// Home: the 3 newest side by side in one bordered strip, then "Show more".
export function XStrip({ posts }: { posts: XPost[] }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-border">
      <MoreGrid posts={posts} first={3} />
    </div>
  );
}

// About: the 6 newest side by side, 3 to a row, then "Show more".
export function XFeedCard() {
  const posts = useXFeed().data ?? [];
  if (!posts.length) return null;
  return (
    <section aria-label="On X" className="overflow-hidden rounded-2xl border border-border bg-background">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3.5">
        <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-[0.14em] text-accent">
          <XLogo className="h-3.5 w-3.5" />On X · @AshleynCas46131
        </div>
        <FollowOnX />
      </div>
      <MoreGrid posts={posts} first={6} />
    </section>
  );
}
