import { useEffect, useState } from "react";
import { cn } from "@/lib/cn";
import { call } from "@/components/admin/DailyDesk";

// Admin X posts: share a published Substack post on X as a thread (title, one post per takeaway,
// then the link), for daily notes and weekly deep dives alike. Drafts come from the post's own title and takeaways (src/castelino/x_post.py).
type Post = {
  kind: "daily" | "weekly";
  when: string;
  title: string;
  url: string;
  slug: string;
  drafts: string[];
  posted_ids: string[];
  image: string | null; // the post's cover, attached to the first post (X hides link cards on thread replies)
};

const LIMIT = 280;
// X's weighted length: a link counts 23, emoji and CJK 2 (same rule as x_post.xlen).
const xlen = (s: string) =>
  [...s.replace(/https?:\/\/\S+/g, "x".repeat(23))].reduce((n, c) => {
    const o = c.codePointAt(0)!;
    return n + (o <= 4351 || (o >= 8192 && o <= 8247) ? 1 : 2);
  }, 0);
const xUrl = (id: string) => `https://x.com/i/status/${id}`;
const label = (p: Post) =>
  p.kind === "daily"
    ? new Date(`${p.when}T12:00:00`).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" })
    : `Week of ${p.when.slice(5)}`;

export default function XPosts() {
  const [posts, setPosts] = useState<Post[] | null>(null);
  const [canPost, setCanPost] = useState(true);
  const [sel, setSel] = useState<string | null>(null);
  const [texts, setTexts] = useState<Record<string, string[]>>({});
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: "ok" | "err"; text: string } | null>(null);
  const [noImage, setNoImage] = useState<Record<string, boolean>>({}); // slugs whose cover is unticked

  const load = () =>
    call<{ can_post: boolean; posts: Post[] }>("/x")
      .then((r) => {
        setPosts(r.posts);
        setCanPost(r.can_post);
        setSel((s) => s ?? r.posts[0]?.slug ?? null);
        setTexts((t) => Object.fromEntries(r.posts.map((p) => [p.slug, t[p.slug] ?? p.drafts])));
      })
      .catch((e) => setMsg({ tone: "err", text: String(e.message ?? e) }));
  useEffect(() => { load(); }, []);

  const post = posts?.find((p) => p.slug === sel);
  const t = (post && texts[post.slug]) || [];
  const done = !!post && post.posted_ids.length > 0 && post.posted_ids.length >= post.drafts.length;
  const partial = !!post && post.posted_ids.length > 0 && !done;
  const tooLong = t.some((s) => xlen(s) > LIMIT);
  const edit = (i: number, v: string) => post && setTexts((x) => ({ ...x, [post.slug]: t.map((s, j) => (j === i ? v : s)) }));
  const remove = (i: number) => post && setTexts((x) => ({ ...x, [post.slug]: t.filter((_, j) => j !== i) }));

  const send = () => {
    if (!post) return;
    const what = partial ? `the remaining ${post.drafts.length - post.posted_ids.length} post(s)` : `${t.length} post(s)`;
    if (!window.confirm(`Post ${what} to X now? This can't be undone from here.`)) return;
    setBusy(true);
    setMsg(null);
    const image = !!post.image && !noImage[post.slug];
    call<{ posted_ids: string[]; total: number; error: string | null }>(`/x/${post.slug}`, { texts: t, image })
      .then((r) => {
        setMsg(r.error
          ? { tone: "err", text: `${r.posted_ids.length} of ${r.total} posted, then: ${r.error}. Use Retry the rest.` }
          : { tone: "ok", text: `Posted ${r.total} to X.` });
        return load();
      })
      .catch((e) => setMsg({ tone: "err", text: String(e.message ?? e) }))
      .finally(() => setBusy(false));
  };

  return (
    <div className="space-y-4 px-4 pb-8 md:px-8">
      {!canPost && (
        <div className="rounded-xl border border-warning/40 bg-warning-soft px-4 py-2.5 text-sm text-warning">
          Posting is off: set X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN and X_ACCESS_SECRET (X developer portal → your app,
          with Read and write) on the server.
        </div>
      )}
      <div className="grid gap-4 lg:grid-cols-[340px_1fr]">
        <div className="flex flex-col gap-1.5">
          {posts === null && <span className="text-sm text-muted">Loading posts…</span>}
          {posts?.length === 0 && <span className="text-sm text-muted">No published Substack posts found.</span>}
          {posts?.map((p) => (
            <button key={p.slug} onClick={() => { setSel(p.slug); setMsg(null); }}
              className={cn("rounded-xl border bg-surface px-3 py-2.5 text-left",
                p.slug === sel ? "border-accent ring-1 ring-accent" : "border-border hover:border-border-strong")}>
              <div className="flex justify-between text-[11px] text-muted">
                <span>{label(p)}</span>
                <span className={cn("rounded px-1.5", p.kind === "daily" ? "bg-surface-3 text-text-2" : "bg-accent-soft text-accent")}>
                  {p.kind === "daily" ? "Daily note" : "Weekly · thread"}
                </span>
              </div>
              <div className="mt-1 text-sm font-semibold leading-snug">{p.title}</div>
              {p.posted_ids.length > 0 && (
                <span className="text-[11px] text-accent">
                  {p.posted_ids.length >= p.drafts.length ? "Posted ✓" : `${p.posted_ids.length}/${p.drafts.length} posted`}
                </span>
              )}
            </button>
          ))}
        </div>

        {post && (
          <div className="rounded-2xl border border-border bg-surface p-4 md:p-5">
            {msg && (
              <div className={cn("mb-3 rounded-lg px-3 py-2 text-sm", msg.tone === "ok" ? "bg-accent-soft text-accent" : "bg-danger-soft text-danger")}>
                {msg.text}
              </div>
            )}
            <h4 className="font-serif text-lg font-semibold leading-snug">{post.title}</h4>
            <p className="mb-3 text-xs text-muted">
              A thread: the title, one post per takeaway, then the link. Edit or remove posts before sending.{" "}
              · <a className="underline" href={post.url} target="_blank" rel="noreferrer">Substack post ↗</a>
            </p>
            <div className="space-y-3">
              {t.map((s, i) => {
                const n = xlen(s);
                const sent = post.posted_ids[i];
                return (
                  <div key={i} className="flex gap-3">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-border text-[10px] font-bold text-accent">ARC</div>
                    <div className="min-w-0 flex-1">
                      <div className="text-xs text-muted">{i === 0 ? "Post" : `Reply ${i}`}{sent && <> · <a className="text-accent underline" href={xUrl(sent)} target="_blank" rel="noreferrer">posted ↗</a></>}</div>
                      <textarea value={s} disabled={done || partial || busy} onChange={(e) => edit(i, e.target.value)}
                        rows={Math.min(7, s.split("\n").length + 1)}
                        className="mt-1 w-full resize-y rounded-lg border border-border bg-surface p-2 text-sm disabled:bg-surface-2" />
                      <div className="flex justify-between text-[11px]">
                        <span className={n > LIMIT ? "font-semibold text-danger" : "text-muted"}>{n}/{LIMIT}{n > LIMIT && " — too long"}</span>
                        {post.kind === "weekly" && i > 0 && i < t.length - 1 && !done && !partial && (
                          <button onClick={() => remove(i)} className="text-muted hover:text-danger">remove</button>
                        )}
                      </div>
                      {i === 0 && post.image && (
                        <div className="mt-2 max-w-[520px]">
                          <img src={post.image} alt="" loading="lazy"
                            className={cn("block aspect-video w-full rounded-2xl border border-border object-cover", noImage[post.slug] && "opacity-30")} />
                          <label className="mt-1.5 flex items-center gap-2 text-[11.5px] text-muted">
                            <input type="checkbox" checked={!noImage[post.slug]} disabled={done || partial || busy}
                              onChange={(e) => setNoImage((x) => ({ ...x, [post.slug]: !e.target.checked }))} />
                            Attach the post's cover to this post (the same picture the site shows)
                          </label>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="mt-4 flex items-center justify-between gap-3">
              <span className="text-xs text-muted">
                {done ? <>Posted · <a className="underline" href={xUrl(post.posted_ids[0])} target="_blank" rel="noreferrer">view on X ↗</a></>
                  : `${t.length} post${t.length === 1 ? "" : "s"} · posted once`}
              </span>
              <button onClick={send} disabled={done || busy || tooLong || !canPost || t.length === 0}
                className="rounded-lg bg-text px-4 py-2 text-sm font-semibold text-background disabled:opacity-40">
                {done ? "Posted ✓" : busy ? "Posting…" : partial ? "Retry the rest" : "Post to X"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
