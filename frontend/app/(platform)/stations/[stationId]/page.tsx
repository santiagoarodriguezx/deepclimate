import type { Metadata } from "next";
import { StationDetail } from "@/components/stations/station-detail";

export const metadata: Metadata = { title: "Estación SIATA" };

export default async function StationPage({ params }: { params: Promise<{ stationId: string }> }) {
  const { stationId } = await params;
  return <StationDetail stationId={stationId} />;
}
