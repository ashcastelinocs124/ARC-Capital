import { useMacroIndicators } from "@/hooks/useMacro";
import { RegimeQuadrant } from "@/components/RegimeQuadrant";
import { ConvictionLedger } from "@/components/ConvictionLedger";
import { RiskOffGauge } from "@/components/RiskOffGauge";
import { MacroIndicatorsTable } from "@/components/MacroIndicatorsTable";

// TODO: real endpoints for these don't exist yet — use stubbed values
// matching the design until backend exposes /regime_forecast and /conviction_ledger
const REGIME_STUB = {
  growthUp: null,
  inflationUp: null,
  growthProb: null,
  inflationProb: null,
};

const CONVICTION_STUB = {
  growthBullish: 0,
  growthBearish: 0,
  inflationBullish: 0,
  inflationBearish: 0,
};

export default function MacroPage() {
  const { data: macro = [] } = useMacroIndicators();

  return (
    <div className="p-8 space-y-6 max-w-7xl mx-auto">
      {/* Top row: regime + conviction + risk-off */}
      <div className="grid lg:grid-cols-3 gap-6">
        <RegimeQuadrant {...REGIME_STUB} />
        <ConvictionLedger {...CONVICTION_STUB} />
        <RiskOffGauge prob={undefined} />
      </div>

      {/* Macro indicators table */}
      <MacroIndicatorsTable data={macro} />
    </div>
  );
}
