import type { ReactNode } from "react";
import { ChartTitle } from "./aiCapex/charts";

// Layout pieces shared by the study dashboards (Partisan Policy Gap, AI Data Centers & the 2026 Vote).

export function Card({ id, eyebrow, title, children }: { id: string; eyebrow: string; title: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-h`} className="bg-surface border border-border rounded-xl shadow-card px-4 py-4 md:px-5 scroll-mt-4">
      <div className="eyebrow">{eyebrow}</div>
      <h2 id={`${id}-h`} className="font-serif font-bold text-[22px] leading-tight text-text mt-1 mb-3">{title}</h2>
      {children}
    </section>
  );
}

export function Tile({ label, value, sub }: { label: ReactNode; value: string; sub: string }) {
  return (
    <div className="rounded-lg border border-border bg-surface-2 px-3.5 py-3">
      <div className="text-xs text-muted">{label}</div>
      <div className="num font-serif font-bold text-[28px] leading-tight text-text my-1">{value}</div>
      <div className="text-xs leading-[17px] text-muted">{sub}</div>
    </div>
  );
}

export const Note = ({ children }: { children: ReactNode }) => <p className="text-xs leading-[18px] text-muted mt-2">{children}</p>;
export const Two = ({ children }: { children: ReactNode }) => <div className="grid gap-5 lg:grid-cols-2">{children}</div>;
export const Box = ({ title, children }: { title: string; children: ReactNode }) => <div className="min-w-0"><ChartTitle>{title}</ChartTitle>{children}</div>;
