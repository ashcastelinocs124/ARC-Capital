import { cn } from "@/lib/cn";

/** The short "what this page is" header every page opens with (approved mockup page-intros.html). */
export function PageIntro({ kicker, title, children, steps, highlight, when }: {
  kicker: string;
  title: string;
  children: React.ReactNode;
  steps?: string[];
  highlight?: number; // index of the step to tint green
  when?: { label: string; value: string; note?: string };
}) {
  return (
    <section className="bg-surface border border-border rounded-xl shadow-card px-5 py-4 md:px-6 md:py-5 grid gap-4 md:grid-cols-[1fr_auto] md:items-center">
      <div className="min-w-0">
        <div className="text-[11px] font-bold tracking-[0.14em] uppercase text-accent">{kicker}</div>
        <h1 className="font-serif font-bold text-[21px] md:text-[24px] leading-tight text-text mt-1 mb-1.5">{title}</h1>
        <p className="text-[13.5px] leading-[21px] text-text-2 max-w-3xl">{children}</p>
        {steps && <div className="flex flex-wrap items-center gap-1.5 mt-2.5 text-[11.5px] text-text-2">
          {steps?.map((s, i) => (
            <span key={s} className="flex items-center gap-1.5">
              {i > 0 && <span className="text-muted-2">→</span>}
              <span className={cn("border rounded-full px-2.5 py-0.5",
                i === highlight ? "border-accent text-accent bg-accent-soft" : "border-border-strong bg-surface")}>{s}</span>
            </span>
          ))}
        </div>}
      </div>
      {when && (
        <div className="text-xs text-muted leading-[18px] md:text-right md:border-l md:border-border md:pl-6">
          {when.label}
          <b className="block text-[15px] text-text">{when.value}</b>
          {when.note}
        </div>
      )}
    </section>
  );
}
