import { useQuery } from "@tanstack/react-query";
import {
  fetchExposureClassChart,
  fetchExposureInstrumentChart,
  fetchWarnings,
} from "@/api/endpoints";

export const useExposureClass = () =>
  useQuery({ queryKey: ["exposure_class"], queryFn: fetchExposureClassChart, refetchInterval: 60_000 });

export const useExposureInstrument = () =>
  useQuery({ queryKey: ["exposure_instrument"], queryFn: fetchExposureInstrumentChart, refetchInterval: 60_000 });

export const useWarnings = () =>
  useQuery({ queryKey: ["warnings"], queryFn: fetchWarnings, refetchInterval: 60_000 });
