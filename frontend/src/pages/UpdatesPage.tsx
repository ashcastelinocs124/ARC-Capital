import { useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { DailyPostsFeed } from "@/components/DailyPostsFeed";
import { useDailyPosts } from "@/hooks/useDailyPosts";
import { isNote } from "@/api/endpoints";

// /updates lists the published Substack daily notes. ?date= (the link in each Substack draft) opens that day's
// Substack post; the site never shows its own copy of a note, so an unpublished day just points back to Memo.
export default function UpdatesPage() {
  const wanted = useSearchParams()[0].get("date");
  const { data: posts, isLoading } = useDailyPosts();
  const post = wanted ? posts?.find((p) => p.date === wanted && isNote(p)) : undefined;
  useEffect(() => {
    if (post) window.location.replace(post.url);
  }, [post]);

  if (wanted) {
    if (isLoading || post) return <div className="p-8 text-sm text-muted">Opening the Substack post…</div>;
    return (
      <div className="space-y-3 p-4 md:p-8">
        <Link to="/updates" className="text-xs font-medium text-accent hover:text-accent-hover">‹ Back to Memo</Link>
        <div className="card p-6 text-sm text-muted">The note for {wanted} isn't published on Substack.</div>
      </div>
    );
  }
  return <DailyPostsFeed posts={posts ?? []} loading={isLoading} />;
}
