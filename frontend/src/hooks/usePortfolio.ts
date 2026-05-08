import { useQuery } from "@tanstack/react-query";
import {
  fetchEquityCurveChart,
  fetchPortfolioMetrics,
  fetchPositions,
  fetchRecentFills,
} from "@/api/endpoints";

export function usePortfolioMetrics() {
  return useQuery({
    queryKey: ["portfolio_metrics"],
    queryFn: fetchPortfolioMetrics,
    refetchInterval: 30_000,
  });
}

export function usePositions() {
  return useQuery({
    queryKey: ["positions"],
    queryFn: fetchPositions,
    refetchInterval: 30_000,
  });
}

export function useEquityCurve() {
  return useQuery({
    queryKey: ["equity_curve"],
    queryFn: fetchEquityCurveChart,
    refetchInterval: 60_000,
  });
}

export function useRecentFills() {
  return useQuery({
    queryKey: ["recent_fills"],
    queryFn: fetchRecentFills,
    refetchInterval: 60_000,
  });
}
