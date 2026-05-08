import { cn } from "@/lib/cn";

export interface FilterPill {
  id: string;
  label: string;
  count?: number;
}

interface Props {
  pills: FilterPill[];
  active: string;
  onChange: (id: string) => void;
  size?: "lg" | "sm";
}

/**
 * Filter pill tabs styled after the Decasonic-style "All Apps 28 / Live 26"
 * pattern. Active pill is solid black; inactive pills are light gray outlines.
 * Count badge sits inside the pill.
 */
export function FilterPills({ pills, active, onChange, size = "lg" }: Props) {
  const isLg = size === "lg";
  return (
    <div className={cn("flex items-center flex-wrap", isLg ? "gap-2" : "gap-1.5")}>
      {pills.map((pill) => {
        const isActive = pill.id === active;
        return (
          <button
            key={pill.id}
            onClick={() => onChange(pill.id)}
            className={cn(
              "inline-flex items-center gap-2 rounded-full font-medium transition-all",
              isLg ? "px-4 py-2 text-sm" : "px-3 py-1.5 text-xs",
              isActive
                ? "bg-text text-white shadow-sm"
                : "bg-surface-2 text-text-2 hover:bg-surface-3 border border-border",
            )}
          >
            <span>{pill.label}</span>
            {typeof pill.count === "number" && (
              <span
                className={cn(
                  "inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 rounded-full font-semibold text-[10px]",
                  isActive ? "bg-white/20 text-white" : "bg-surface-3 text-muted",
                )}
              >
                {pill.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

export interface CounterPillProps {
  label: string;
  count: number | string;
  accent?: "default" | "success" | "danger" | "warning";
}

/**
 * Counter pill styled after Decasonic's "AI Teammates 226" — soft outline
 * with a colored count number on the right. Used in page hero strips.
 */
export function CounterPill({ label, count, accent = "default" }: CounterPillProps) {
  return (
    <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-surface border border-border">
      <span className="text-sm text-muted">{label}</span>
      <span
        className={cn(
          "text-sm font-bold num",
          accent === "success" && "text-success",
          accent === "danger" && "text-danger",
          accent === "warning" && "text-warning",
          accent === "default" && "text-text",
        )}
      >
        {count}
      </span>
    </div>
  );
}
