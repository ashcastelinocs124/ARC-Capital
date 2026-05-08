import { Card, CardContent } from "@/components/ui/card";
import { Sparkles } from "lucide-react";

export function PlaceholderPage({ name, phase }: { name: string; phase: string }) {
  return (
    <div className="p-6">
      <Card>
        <CardContent className="flex flex-col items-center justify-center py-16">
          <div className="w-12 h-12 rounded-full bg-accent/15 flex items-center justify-center mb-4">
            <Sparkles className="h-6 w-6 text-accent" />
          </div>
          <div className="text-lg font-semibold mb-1">{name}</div>
          <div className="text-sm text-muted">Coming in {phase}</div>
        </CardContent>
      </Card>
    </div>
  );
}
