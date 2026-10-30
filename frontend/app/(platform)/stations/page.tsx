import type { Metadata } from "next";
import { StationExplorer } from "@/components/stations/station-explorer";

export const metadata: Metadata = { title: "Estaciones SIATA" };

export default function StationsPage() {
  return <StationExplorer />;
}
