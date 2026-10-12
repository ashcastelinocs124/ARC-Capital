import { useState, type ReactNode } from "react";
import type { WeekEvent } from "@/api/types";

/** One floating tooltip per chart: call show(e, content) on mouse move, hide() on leave. */
export function useTip() {
  const [tip, setTip] = useState<{ x: number; y: number; body: ReactNode } | null>(null);
  const show = (e: React.MouseEvent, body: ReactNode) => setTip({ x: e.clientX + 14, y: e.clientY + 14, body });
  const hide = () => setTip(null);
  const node = tip && (
    <div className="fixed z-50 pointer-events-none bg-text text-surface text-xs leading-[17px] px-2.5 py-1.5 rounded-md max-w-[260px]"
      style={{ left: tip.x, top: tip.y }}>{tip.body}</div>
  );
  return { show, hide, node };
}

export const COUNTRY: Record<string, string> = { US: "United States", CN: "China", DE: "Germany", JP: "Japan", IN: "India" };

export function fmt(v: number | null | undefined, unit = ""): string {
  if (v == null) return "–";
  return `${v.toLocaleString("en-US", { maximumFractionDigits: 2 })}${unit}`;
}

export function releaseLine(e: WeekEvent): string {
  const m = e.measure ? ` ${e.measure}` : "";
  const act = e.actual != null ? ` · actual ${fmt(e.actual, e.unit)}` : "";
  return `${e.name}${m}: est ${fmt(e.consensus, e.unit)} · prev ${fmt(e.previous, e.unit)}${act}`;
}

export function GapNote({ gaps, lanes }: { gaps: { lane: string; error: string }[]; lanes: string[] }) {
  const hit = gaps.filter((g) => lanes.includes(g.lane));
  if (!hit.length) return null;
  return (
    <p className="text-[11.5px] text-warning mt-2">
      Some data unavailable this run ({hit.map((g) => g.lane).join(", ")}); anything shown for it is from an earlier run this week.
    </p>
  );
}
