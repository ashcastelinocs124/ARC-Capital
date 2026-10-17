import { PageIntro } from "@/components/layout/PageIntro";
import { useSectionPosts } from "@/hooks/useSectionPosts";
import { VideoCard } from "@/pages/VideosPage";

// Substack sections as one feed (/ai/models, /ai/chips, /special-topics).
// `slugs` are Substack section URL slugs, as in section_posts.py; the first one is the "View all" link.
export default function SectionPage({ slugs, kicker, title, blurb }: { slugs: string[]; kicker: string; title: string; blurb: string }) {
  const { data, isLoading } = useSectionPosts();
  const posts = (data ?? []).filter((p) => slugs.includes(p.section));
  return (
    <div className="space-y-5 p-4 md:p-8">
      <PageIntro kicker={kicker} title={title}>
        {blurb} Each card opens the post on the ARC Research Substack.
      </PageIntro>
      {isLoading && <div className="text-sm text-muted">Loading…</div>}
      {!isLoading && posts.length === 0 && <div className="card p-6 text-sm text-muted">No posts in this section yet.</div>}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {posts.map((p) => (
          <VideoCard key={p.url} v={p} />
        ))}
      </div>
      <a href={`https://archresearch.substack.com/s/${slugs[0]}`} target="_blank" rel="noopener noreferrer"
        className="inline-block text-[13px] font-semibold text-accent hover:text-accent-hover">
        View all on Substack ↗
      </a>
    </div>
  );
}
