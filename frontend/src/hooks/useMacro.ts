import { useQuery } from "@tanstack/react-query";
import {
  fetchEconCalendar,
  fetchHypotheses,
  fetchMacroIndicators,
  fetchNewsFeed,
  fetchTriggers,
  fetchYieldCurveChart,
} from "@/api/endpoints";

const FIVE_MINUTES = 5 * 60_000;

export const useMacroIndicators = () =>
  useQuery({ queryKey: ["macro_indicators"], queryFn: fetchMacroIndicators, refetchInterval: FIVE_MINUTES });

export const useYieldCurve = () =>
  useQuery({ queryKey: ["yield_curve"], queryFn: fetchYieldCurveChart, refetchInterval: FIVE_MINUTES });

export const useTriggers = () =>
  useQuery({ queryKey: ["triggers"], queryFn: fetchTriggers, refetchInterval: 60_000 });

export const useHypotheses = () =>
  useQuery({ queryKey: ["hypotheses"], queryFn: fetchHypotheses, refetchInterval: 60_000 });

export const useNewsFeed = () =>
  useQuery({ queryKey: ["news_feed"], queryFn: fetchNewsFeed, refetchInterval: 60_000 });

export const useEconCalendar = () =>
  useQuery({ queryKey: ["econ_calendar"], queryFn: fetchEconCalendar, refetchInterval: FIVE_MINUTES });
