import { useMacroIndicators, useRegimeForecast } from "@/hooks/useMacro";
import { RegimeQuadrant } from "@/components/RegimeQuadrant";
import { ConvictionLedger } from "@/components/ConvictionLedger";
import { RiskOffGauge } from "@/components/RiskOffGauge";
import { MacroIndicatorsTable } from "@/components/MacroIndicatorsTable";

// TODO: no /conviction_ledger endpoint yet — stubbed

const CONVICTION_STUB = {
  growthBullish: 0,
  growthBearish: 0,
  inflationBullish: 0,
  inflationBearish: 0,
};

export default function MacroPage() {
  const { data: macro = [] } = useMacroIndicators();
  const { data: regime } = useRegimeForecast();

  return (
    <div className="p-8 space-y-6 max-w-7xl mx-auto">
      {/* Top row: regime + conviction + risk-off */}
      <div className="grid lg:grid-cols-3 gap-6">
        <RegimeQuadrant
          growthUp={regime?.growth_up}
          inflationUp={regime?.inflation_up}
          growthProb={regime?.growth_prob}
          inflationProb={regime?.inflation_prob}
          running={regime?.running ?? true}
        />
        <ConvictionLedger {...CONVICTION_STUB} />
        <RiskOffGauge prob={undefined} />
      </div>

      {/* Macro indicators table */}
      <MacroIndicatorsTable data={macro} />
    </div>
  );
}
