import { useEffect } from "react";
import { Navigate, useSearchParams } from "react-router-dom";
import { useThemePosts } from "@/hooks/useThemes";

// Theme Charts lives on Radar (/macro#theme) since 2026-10-17. /themes?run= (an older X thread's link)
// still opens that run's Substack post; anything else lands on Radar's card.
export default function ThemesPage() {
  const run = useSearchParams()[0].get("run");
  const { data: posts = [], isLoading } = useThemePosts();
  const post = run ? posts.find((p) => p.run_id === run) : undefined;
  useEffect(() => {
    if (post) window.location.replace(post.url);
  }, [post]);
  if (run && (isLoading || post)) return <div className="p-8 text-sm text-muted">Opening the Substack post…</div>;
  return <Navigate to="/macro#theme" replace />;
}
