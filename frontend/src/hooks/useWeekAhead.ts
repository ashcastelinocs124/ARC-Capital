import { useQuery } from "@tanstack/react-query";
import { fetchAiSentiment, fetchWeekAhead } from "@/api/endpoints";

export const useWeekAhead = () =>
  useQuery({ queryKey: ["week-ahead"], queryFn: fetchWeekAhead, refetchInterval: 5 * 60_000 });

export const useAiSentiment = () =>
  useQuery({ queryKey: ["ai-sentiment"], queryFn: fetchAiSentiment, refetchInterval: 5 * 60_000 });
