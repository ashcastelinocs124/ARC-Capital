import { Play } from "lucide-react";
import { useVideos } from "@/hooks/useVideos";
import type { Video } from "@/api/endpoints";

const fmt = (d: string) =>
  new Date(`${d}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });

export const clock = (sec: number) => `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;

// A post without a cover image (a video embedded in a newsletter) gets the brand gradient.
export function VideoCard({ v }: { v: Video }) {
  const isVideo = v.video !== false;
  return (
    <a href={v.url} target="_blank" rel="noopener noreferrer" className="card group block overflow-hidden p-0 transition-shadow hover:shadow-card-hover">
      <div className="relative aspect-video bg-gradient-to-br from-[#0b3d24] via-accent to-[#9ad7b6]">
        {v.thumbnail && <img src={v.thumbnail} alt="" loading="lazy" className="absolute inset-0 h-full w-full object-cover" />}
        {isVideo && (
          <span className="absolute inset-0 grid place-items-center">
            <span className="grid h-12 w-12 place-items-center rounded-full bg-black/45 text-white group-hover:bg-accent group-hover:text-on-accent">
              <Play className="h-5 w-5 fill-current" />
            </span>
          </span>
        )}
        {isVideo && v.duration && (
          <span className="absolute bottom-2 right-2 rounded-md bg-black/65 px-1.5 py-0.5 text-[11px] font-semibold text-white">
            {clock(v.duration)}
          </span>
        )}
      </div>
      <div className="p-5">
        <div className="flex items-center justify-between">
          <span className="eyebrow">{fmt(v.date)}</span>
          <span className="pill">{isVideo ? "VIDEO" : "ARTICLE"}</span>
        </div>
        <h3 className="mt-3 text-base font-semibold leading-snug text-text">{v.title}</h3>
        <p className="mt-1.5 line-clamp-2 text-xs leading-relaxed text-muted">{v.summary}</p>
        <div className="mt-3 text-[13px] font-semibold text-accent">{isVideo ? "Watch" : "Read"} on Substack ↗</div>
      </div>
    </a>
  );
}

export default function VideosPage() {
  const { data, isLoading } = useVideos();
  const videos = data ?? [];
  return (
    <div className="p-4 md:p-8 space-y-5">
      <div>
        <h2 className="text-xl font-semibold tracking-tight text-text">
          Videos <span className="text-xs font-normal text-muted">{videos.length ? `${videos.length} on Substack` : ""}</span>
        </h2>
        <p className="text-xs text-muted mt-0.5">Walkthroughs from the ARC Research Substack. Each one opens the post.</p>
      </div>
      {isLoading && <div className="text-sm text-muted">Loading…</div>}
      {!isLoading && videos.length === 0 && (
        <div className="card p-6 text-sm text-muted">No videos yet. They appear after the next snapshot publish.</div>
      )}
      <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
        {videos.map((v) => (
          <VideoCard key={v.url} v={v} />
        ))}
      </div>
    </div>
  );
}
