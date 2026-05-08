import type { MacroIndicatorRow } from "@/api/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function MacroIndicatorsTable({ data }: { data: MacroIndicatorRow[] }) {
  if (!data || data.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Macro Indicators</CardTitle>
        </CardHeader>
        <CardContent className="py-12 text-center text-sm text-muted">No data.</CardContent>
      </Card>
    );
  }

  const columns = Object.keys(data[0]).filter((k) => k !== "date");

  return (
    <Card>
      <CardHeader>
        <CardTitle>Macro Indicators</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase tracking-wide text-muted bg-surface-2">
              <tr>
                <th className="px-4 py-2 text-left">Date</th>
                {columns.map((c) => (
                  <th key={c} className="px-4 py-2 text-right font-mono">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {data.slice(-10).reverse().map((row, i) => (
                <tr key={i} className="hover:bg-surface-2">
                  <td className="px-4 py-2 font-mono num text-muted-2">{row.date}</td>
                  {columns.map((c) => (
                    <td key={c} className="px-4 py-2 text-right font-mono num">
                      {typeof row[c] === "number"
                        ? (row[c] as number).toFixed(2)
                        : String(row[c] ?? "—")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
