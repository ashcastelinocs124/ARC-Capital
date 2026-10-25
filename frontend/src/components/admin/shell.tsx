import { createContext, useContext } from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/cn";

// The admin page header (pages/AdminPage.tsx) owns the title and description; a section puts its own buttons on
// the header's right with <HeaderActions>, so every section keeps one header without the shell knowing its state.
export const ActionsSlot = createContext<HTMLElement | null>(null);

export function HeaderActions({ children }: { children: React.ReactNode }) {
  const slot = useContext(ActionsSlot);
  return slot ? createPortal(children, slot) : null;
}

export type Tone = "run" | "wait" | "ok" | "fail" | "off";

const DOT: Record<Tone, string> = {
  run: "bg-accent motion-safe:animate-[pulse-ring_1.6s_ease-in-out_infinite]",
  wait: "bg-warning",
  ok: "bg-accent",
  fail: "bg-danger",
  off: "border-[1.5px] border-muted",
};
const TEXT: Record<Tone, string> = {
  run: "text-accent",
  wait: "text-warning",
  ok: "text-text-2",
  fail: "text-danger",
  off: "text-muted",
};

/** A status as a dot plus a word (never color alone). The dot moves only while something runs. */
export function Status({ tone, children, className }: { tone: Tone; children?: React.ReactNode; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-[7px] text-xs font-medium", TEXT[tone], className)}>
      <i className={cn("block h-[7px] w-[7px] flex-none rounded-full", DOT[tone])} aria-hidden="true" />
      {children}
    </span>
  );
}

// Buttons in the console's shape (8px corners, not pills).
export const btn = {
  primary: "inline-flex h-8 items-center gap-1.5 rounded-lg bg-accent px-3 text-[13px] font-medium text-on-accent hover:bg-accent-hover disabled:opacity-50",
  secondary: "inline-flex h-8 items-center gap-1.5 rounded-lg border border-border bg-surface px-3 text-[13px] font-medium text-text hover:border-border-strong disabled:opacity-50",
  ghost: "inline-flex h-8 items-center gap-1.5 rounded-lg px-3 text-[13px] font-medium text-text-2 hover:bg-surface-3 disabled:opacity-50",
};

/** A small set of mutually exclusive choices (a range, a mode), as pressed buttons in one group. */
export function Segmented<T extends string>({ value, options, onChange, label }: {
  value: T; options: [T, string][]; onChange: (v: T) => void; label: string;
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex rounded-lg border border-border bg-surface-2 p-0.5">
      {options.map(([v, text]) => (
        <button key={v} type="button" aria-pressed={v === value} onClick={() => onChange(v)}
          className={cn("h-7 rounded-md px-3 text-[13px] font-medium",
            v === value ? "bg-surface text-text ring-1 ring-border" : "text-muted hover:text-text-2")}>
          {text}
        </button>
      ))}
    </div>
  );
}
