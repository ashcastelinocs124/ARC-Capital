import { useMacroIndicators, useRegimeForecast } from "@/hooks/useMacro";
import { RegimeQuadrant } from "@/components/RegimeQuadrant";
import { EconomicReleasesCard } from "@/components/EconomicReleasesCard";
import { MacroIndicatorsTable } from "@/components/MacroIndicatorsTable";


export default function MacroPage() {
  const { data: macro = [] } = useMacroIndicators();
  const { data: regime } = useRegimeForecast();

  return (
    <div className="p-4 md:p-8 space-y-6">
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
