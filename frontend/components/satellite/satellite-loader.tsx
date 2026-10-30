"use client";

import dynamic from "next/dynamic";
import { LoadingState } from "@/components/ui/states";
import type { Station } from "@/lib/types";

const SatelliteExplorer = dynamic(
  () => import("@/components/satellite/satellite-explorer").then((module) => module.SatelliteExplorer),
  { ssr: false, loading: () => <LoadingState label="Cargando mapa satelital" /> },
);

export function SatelliteLoader({ compact = false, stations }: { compact?: boolean; stations: Station[] }) {
  return <SatelliteExplorer compact={compact} stations={stations} />;
}
