import { useRef, useState } from "react";

// Hover detail for the AI Demand & Capex charts. One hook per chart: hovering an item shows its tooltip
// and dims the rest; the chart is one Tab stop where the arrow keys step through the items and Esc
// closes, so nothing is mouse-only (WCAG 2.1.1); a live region reads the tooltip to screen readers.

export interface Tip { title: string; lines: string[] }

export const tipText = (t: Tip) => [t.title, ...t.lines].join(". ");

/** ▲ 74% / ▼ 3% from two numbers, or null when there's nothing to compare. */
export function change(now: number | null | undefined, then: number | null | undefined): string | null {
  if (now == null || then == null || then === 0) return null;
  const p = Math.round((now / then - 1) * 100);
  return `${p >= 0 ? "▲" : "▼"} ${Math.abs(p)}%`;
}

export function useHover(tips: Tip[]) {
  const [active, setActive] = useState<number | null>(null);
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);
  const els = useRef<(Element | null)[]>([]);
  const place = (k: number) => {
    const r = els.current[k]?.getBoundingClientRect();
    if (r) setPos({ x: r.right + 8, y: r.top });
  };
  const item = (k: number) => ({
    ref: (el: Element | null) => {
      els.current[k] = el;
    },
    onMouseMove: (e: React.MouseEvent) => {
      setActive(k);
      setPos({ x: e.clientX + 14, y: e.clientY + 14 });
    },
    onMouseLeave: () => setActive(null),
  });
  const chart = {
    tabIndex: tips.length ? 0 : -1,
    className: "rounded-md outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface",
    onFocus: () => {
      if (!tips.length) return;
      setActive(0);
      place(0);
    },
    onBlur: () => setActive(null),
    onKeyDown: (e: React.KeyboardEvent) => {
      if (e.key === "Escape") return setActive(null);
      const d = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
      if (!d || !tips.length) return;
      e.preventDefault();
      const k = ((active ?? -1) + d + tips.length) % tips.length;
      setActive(k);
      place(k);
    },
  };
  /** Full opacity for the hovered item (or everything when nothing is hovered), faded otherwise. */
  const dim = (on: boolean) => (active == null || on ? 1 : 0.32);
  const tip = active != null ? tips[active] : null;
  const node = (
    <>
      {tip && pos && (
        <div role="tooltip" className="fixed z-50 pointer-events-none max-w-[260px] rounded-md bg-text px-2.5 py-1.5 text-xs leading-[17px] text-surface shadow-lg"
          style={{ left: Math.min(pos.x, window.innerWidth - 272), top: Math.min(pos.y, window.innerHeight - 90) }}>
          <b className="block">{tip.title}</b>
          {tip.lines.map((l) => <div key={l}>{l}</div>)}
        </div>
      )}
      <span className="sr-only" aria-live="polite">{tip ? tipText(tip) : ""}</span>
    </>
  );
  return { active, item, chart, dim, node };
}
