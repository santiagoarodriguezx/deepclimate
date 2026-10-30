"use client";

import dynamic from "next/dynamic";
import { LoadingState } from "@/components/ui/states";

const SatelliteExplorer = dynamic(
  () => import("@/components/satellite/satellite-explorer").then((module) => module.SatelliteExplorer),
  { ssr: false, loading: () => <LoadingState label="Cargando mapa satelital" /> },
);

export function SatelliteLoader() {
  return <SatelliteExplorer />;
}
