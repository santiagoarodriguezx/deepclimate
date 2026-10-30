"use client";

import { useQuery } from "@tanstack/react-query";
import {
  getEvents, getFreshness, getGibsLayers, getHealth, getJevDecisions, getLatest,
  getRegionalForecast, getRegionalHistory, getSeries, getSources, getStations,
} from "@/lib/api";

export function useStations() {
  return useQuery({ queryKey: ["stations"], queryFn: getStations, staleTime: 120_000 });
}
export function useLatest(variable: string) {
  return useQuery({ queryKey: ["latest", variable], queryFn: () => getLatest(variable), staleTime: 30_000, refetchInterval: 60_000 });
}
export function useFreshness(variable: string) {
  return useQuery({ queryKey: ["freshness", variable], queryFn: () => getFreshness(variable), staleTime: 30_000, refetchInterval: 60_000 });
}
export function useEvents() {
  return useQuery({ queryKey: ["events"], queryFn: getEvents, staleTime: 30_000, refetchInterval: 60_000 });
}
export function useHealth() {
  return useQuery({ queryKey: ["health"], queryFn: getHealth, staleTime: 30_000, refetchInterval: 60_000 });
}
export function useSources() {
  return useQuery({ queryKey: ["sources"], queryFn: getSources, staleTime: 30_000, refetchInterval: 60_000 });
}
export function useGibsLayers() {
  return useQuery({ queryKey: ["gibs-layers"], queryFn: getGibsLayers, staleTime: 10 * 60_000 });
}
export function useJevDecisions() {
  return useQuery({ queryKey: ["jev-decisions"], queryFn: () => getJevDecisions(30), staleTime: 15_000, refetchInterval: 30_000 });
}
export function useRegionalForecast(variable: string, hours = 24) {
  return useQuery({
    queryKey: ["regional-forecast", variable, hours],
    queryFn: () => getRegionalForecast(variable, hours),
    staleTime: 30 * 60_000,
    refetchInterval: 30 * 60_000,
  });
}
export function useRegionalHistory(variable: string, days = 7) {
  return useQuery({ queryKey: ["regional-history", variable, days], queryFn: () => getRegionalHistory(variable, days), staleTime: 60_000 });
}
export function useTimeSeries(station: string, variable: string, days: number) {
  return useQuery({ queryKey: ["series", station, variable, days], queryFn: () => getSeries(station, variable, days), enabled: Boolean(station && variable), staleTime: 30_000 });
}
