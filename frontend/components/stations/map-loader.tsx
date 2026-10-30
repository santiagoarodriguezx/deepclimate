"use client";

import dynamic from "next/dynamic";
import type { Observation, RegionalForecast, Station } from "@/lib/types";
import { LoadingState } from "@/components/ui/states";

const MapView = dynamic(() => import("@/components/stations/map-view").then((module) => module.StationMap), {
  ssr: false,
  loading: () => <LoadingState label="Cargando cartografía" />,
});

export function MapLoader(props: { stations: Station[]; readings?: Observation[]; variable?: string; regionalForecasts?: Record<string, RegionalForecast> }) {
  return <MapView key={props.variable ?? "dashboard"} {...props} />;
}
