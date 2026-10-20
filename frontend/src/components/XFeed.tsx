import { useState } from "react";
import { ArrowUpRight, BarChart2, Heart, MessageCircle, Repeat2 } from "lucide-react";
import { X_PROFILE, type XPost } from "@/api/endpoints";
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

// One post as X draws it in a timeline. The whole post opens it on x.com; the action icons are
// decoration (no counts: the cache only asks X for new posts, so counts would go stale).
function XPostRow({ p, clamp }: { p: XPost; clamp?: boolean }) {
  return (
    <a href={p.url} target="_blank" rel="noopener noreferrer" className="flex min-w-0 gap-3 px-4 py-3 hover:bg-surface-3/45">
      <img src="/team/ashleyn.png" alt="" className="h-10 w-10 shrink-0 rounded-full object-cover object-[40%_30%]" />
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1 text-[15px] leading-5">
          <span className="shrink-0 font-bold text-text">Ashleyn Castelino</span>
          <span className="truncate text-muted">@AshleynCas46131</span>
          <span className="text-muted" aria-hidden="true">·</span>
          <time dateTime={p.at} title={FULL.format(new Date(p.at))} className="shrink-0 text-muted">{ago(p.at)}</time>
          <XLogo className="ml-auto h-4 w-4 shrink-0 text-muted" />
        </span>
        <span className={cn("mt-0.5 block whitespace-pre-line break-words text-[15px] leading-[1.45] text-text", clamp && "line-clamp-6")}>{p.text}</span>
        {p.image && (
          <img src={`${p.image}?name=small`} alt="Chart attached to the post" loading="lazy"
            className="mt-3 aspect-[16/10] w-full rounded-2xl border border-border bg-white object-cover" />
        )}
        <span className="mt-3 flex max-w-[420px] justify-between text-muted" aria-hidden="true">
          <MessageCircle className="h-[18px] w-[18px]" /><Repeat2 className="h-[18px] w-[18px]" />
          <Heart className="h-[18px] w-[18px]" /><BarChart2 className="h-[18px] w-[18px]" />
        </span>
      </span>
    </a>
  );
}

// Home: the 3 newest side by side in one bordered strip, split by dividers.
export function XStrip({ posts }: { posts: XPost[] }) {
  return (
    <div className="grid overflow-hidden rounded-2xl border border-border bg-background divide-y divide-border md:grid-cols-3 md:divide-x md:divide-y-0">
      {posts.slice(0, 3).map((p) => <XPostRow key={p.id} p={p} clamp />)}
    </div>
  );
}

// About: the 5 newest as a timeline as wide as X's own column, then "Show more" (the export keeps 10).
export function XFeedCard() {
  const posts = useXFeed().data ?? [];
  const [open, setOpen] = useState(false);
  if (!posts.length) return null;
  return (
    <section aria-label="On X" className="max-w-[640px] overflow-hidden rounded-2xl border border-border bg-background">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3.5">
        <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-[0.14em] text-accent">
          <XLogo className="h-3.5 w-3.5" />On X · @AshleynCas46131
        </div>
        <FollowOnX />
      </div>
      <div className="divide-y divide-border">
        {posts.slice(0, open ? 10 : 5).map((p) => <XPostRow key={p.id} p={p} />)}
      </div>
      {posts.length > 5 && (
        <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}
          className="block w-full border-t border-border px-4 py-3.5 text-left text-[15px] text-accent hover:bg-surface-3/45">
          {open ? "Show fewer" : "Show more"}
        </button>
      )}
    </section>
  );
}
