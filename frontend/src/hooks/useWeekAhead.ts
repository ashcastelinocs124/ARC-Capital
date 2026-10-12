import { useQuery } from "@tanstack/react-query";
import { fetchWeekAhead } from "@/api/endpoints";

export const useWeekAhead = () =>
  useQuery({ queryKey: ["week-ahead"], queryFn: fetchWeekAhead, refetchInterval: 5 * 60_000 });
