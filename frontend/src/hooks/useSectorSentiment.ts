import { useQuery } from "@tanstack/react-query";
import { fetchSectorSentiment } from "@/api/endpoints";

export function useSectorSentiment() {
  return useQuery({
    queryKey: ["sector-sentiment"],
    queryFn: fetchSectorSentiment,
    refetchInterval: 60_000,
  });
}
