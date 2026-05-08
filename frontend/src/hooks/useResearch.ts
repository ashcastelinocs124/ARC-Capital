import { useQuery } from "@tanstack/react-query";
import {
  fetchCorrelationHeatmap,
  fetchScreener,
  fetchSectorPerf,
  fetchTaChart,
} from "@/api/endpoints";

export const useTaChart = () =>
  useQuery({ queryKey: ["ta_chart"], queryFn: fetchTaChart, refetchInterval: 60_000 });

export const useScreener = () =>
  useQuery({ queryKey: ["screener"], queryFn: fetchScreener, refetchInterval: 5 * 60_000 });

export const useCorrelation = () =>
  useQuery({ queryKey: ["correlation"], queryFn: fetchCorrelationHeatmap, refetchInterval: 5 * 60_000 });

export const useSectorPerf = () =>
  useQuery({ queryKey: ["sector_perf"], queryFn: fetchSectorPerf, refetchInterval: 60_000 });
