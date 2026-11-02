import { useQuery } from "@tanstack/react-query";
import { fetchSectorSignals } from "@/api/sectorSignals";

export const useSectorSignals = () =>
  useQuery({ queryKey: ["sector-signals"], queryFn: fetchSectorSignals, refetchInterval: 10 * 60_000 });
