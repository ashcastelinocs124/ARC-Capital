import { useState } from "react";
import { PageIntro } from "@/components/layout/PageIntro";
import { CardBoundary } from "@/components/modelCard";
import { useAiCapex } from "@/hooks/useAiCapex";
import { Spending } from "@/components/dashboards/aiCapex/Spending";
import { Funding } from "@/components/dashboards/aiCapex/Funding";
import { Demand } from "@/components/dashboards/aiCapex/Demand";
import { Compute } from "@/components/dashboards/aiCapex/Compute";
import { Adoption } from "@/components/dashboards/aiCapex/Adoption";
import { CompanyTable } from "@/components/dashboards/aiCapex/CompanyTable";

function CopyLink() {
  const [done, setDone] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href); // filters included
      setDone(true);
      setTimeout(() => setDone(false), 2000);
    } catch {
      /* no clipboard (insecure context): the address bar still has the link */
    }
  };
  return (
    <button type="button" onClick={copy} aria-live="polite"
      className="mt-2 inline-flex items-center gap-1.5 rounded-full border border-border-strong bg-surface-2 px-3 py-1 text-[12.5px] font-semibold text-text hover:border-accent">
      {done ? "Copied" : "⧉ Copy link"}
    </button>
  );
}

const day = (d: string) => new Date(`${d}T12:00:00`).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric" });

export default function AiCapexPage() {
  const { data, isLoading } = useAiCapex();
  return (
    <div className="grid gap-4">
      <PageIntro
        kicker="Dashboard · AI Demand & Capex"
        title="Is AI demand keeping up with the spending?"
        steps={["Spending", "Funding", "Demand", "Compute", "Adoption"]}
        when={data ? { label: "Updated", value: day(data.as_of), note: <CopyLink /> } : undefined}
      >
        What Microsoft, Alphabet, Amazon, Meta and Oracle, plus the neoclouds CoreWeave, Nebius and IREN, spend on
        data centers, how they pay for it, and the demand and compute shortage behind it. Every figure comes from
        company filings, a cited and number-checked search, or the source named under its chart.
      </PageIntro>
      {isLoading ? (
        <p className="text-sm text-muted">Loading…</p>
      ) : !data ? (
        <p className="text-sm text-muted">The dashboard hasn't been built yet. It updates every evening at 5 pm New York time.</p>
      ) : (
        <>
          <CardBoundary name="Spending"><Spending data={data} /></CardBoundary>
          <CardBoundary name="Funding"><Funding data={data} /></CardBoundary>
          <CardBoundary name="Demand"><Demand data={data} /></CardBoundary>
          <CardBoundary name="Compute"><Compute data={data} /></CardBoundary>
          <CardBoundary name="Adoption"><Adoption data={data} /></CardBoundary>
          <CardBoundary name="Company table"><CompanyTable data={data} /></CardBoundary>
          {data.gaps.length > 0 && (
            // a lane that failed keeps its last value: say so, rather than pass it off as today's
            <p className="text-xs text-muted">
              Not updated today, showing the last good reading:{" "}
              {data.gaps.map((g) => g.lane.replace("company:", "")).join(", ")}.
            </p>
          )}
        </>
      )}
    </div>
  );
}
