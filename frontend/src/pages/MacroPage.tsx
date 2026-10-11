import { useMacroIndicators, useRegimeForecast } from "@/hooks/useMacro";
import { RegimeQuadrant } from "@/components/RegimeQuadrant";
import { EconomicReleasesCard } from "@/components/EconomicReleasesCard";
import { MacroIndicatorsTable } from "@/components/MacroIndicatorsTable";
import { PageIntro } from "@/components/layout/PageIntro";


export default function MacroPage() {
  const { data: macro = [] } = useMacroIndicators();
  const { data: regime } = useRegimeForecast();

  return (
    <div className="p-4 md:p-8 space-y-6">
      <PageIntro kicker="Macro & Signals" title="Where the US economy is, and what just came out"
        steps={["Pulse + Pressure", "Regime map", "Economic releases", "Indicators"]}
        when={{ label: "Updated daily", value: "17:00 ET" }}>
        The regime map places the economy on growth and inflation using ARC's Pulse and Pressure models. Below it,
        every scheduled US data release and the core macro indicators, refreshed each evening after the close.
      </PageIntro>
      <div>
        <RegimeQuadrant
          growthUp={regime?.growth_up}
          inflationUp={regime?.inflation_up}
          growthProb={regime?.growth_prob}
          inflationProb={regime?.inflation_prob}
          running={regime?.running ?? true}
        />
      </div>

      <EconomicReleasesCard />

      {/* Macro indicators table */}
      <MacroIndicatorsTable data={macro} />
    </div>
  );
}
