import { useCallback, useState } from "react";
import { runPanel } from "../api/personas";
import type { PanelDiscussion } from "../api/types";

export function usePanelDiscussion(entryId: string) {
  const [panel, setPanel] = useState<PanelDiscussion | null>(null);
  const [pending, setPending] = useState(false);

  const run = useCallback(
    async (personas: string[], question: string) => {
      setPending(true);
      try {
        setPanel(await runPanel(entryId, personas, question));
      } finally {
        setPending(false);
      }
    },
    [entryId],
  );

  return { panel, pending, run };
}
