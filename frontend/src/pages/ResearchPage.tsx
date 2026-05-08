import { useState } from "react";
import { Search } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useScreener, useSectorPerf } from "@/hooks/useResearch";

export default function ResearchPage() {
  const [symbol, setSymbol] = useState("SPY");
  const { data: screener = [] } = useScreener();
  const { data: sectors = [] } = useSectorPerf();

  return (
    <div className="p-8 space-y-6 max-w-7xl mx-auto">
      {/* Symbol picker + TA chart */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Technical Analysis</CardTitle>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                className="bg-surface-2 border border-border rounded-md px-3 py-1.5 text-sm font-mono w-24 focus:outline-none focus:ring-1 focus:ring-accent"
                placeholder="SPY"
              />
              <Button size="sm" variant="outline">
                <Search className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="h-80 flex items-center justify-center text-sm text-muted bg-surface-2 rounded-md">
            <div className="text-center">
              <div>TA chart for <span className="font-mono font-semibold text-text">{symbol}</span></div>
              <div className="text-xs mt-1">RSI(14), MACD, OBV — backend endpoint not yet implemented</div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Screener + Sector Perf */}
      <div className="grid lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Instrument Screener</CardTitle>
          </CardHeader>
          <CardContent>
            {screener.length === 0 ? (
              <div className="py-12 text-center text-sm text-muted">No screener data.</div>
            ) : (
              <pre className="text-xs text-muted bg-surface-2 p-3 rounded-md overflow-auto max-h-80">
                {JSON.stringify(screener, null, 2)}
              </pre>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Sector Performance</CardTitle>
          </CardHeader>
          <CardContent>
            {sectors.length === 0 ? (
              <div className="py-12 text-center text-sm text-muted">No sector data.</div>
            ) : (
              <pre className="text-xs text-muted bg-surface-2 p-3 rounded-md overflow-auto max-h-80">
                {JSON.stringify(sectors, null, 2)}
              </pre>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Correlation heatmap placeholder */}
      <Card>
        <CardHeader>
          <CardTitle>Correlation Heatmap</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-48 flex items-center justify-center text-sm text-muted">
            Correlation matrix — backend endpoint not yet implemented
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
