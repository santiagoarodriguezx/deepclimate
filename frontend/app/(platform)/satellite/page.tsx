import type { Metadata } from "next";
import { SatelliteLoader } from "@/components/satellite/satellite-loader";

export const metadata: Metadata = { title: "Explorador satelital" };

export default function SatellitePage() {
  return <SatelliteLoader />;
}
