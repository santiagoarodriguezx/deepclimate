"use client";

import "leaflet/dist/leaflet.css";
import Link from "next/link";
import { CircleMarker, MapContainer, Popup, TileLayer, useMap } from "react-leaflet";
import type { LatLngBoundsExpression } from "leaflet";
import { useEffect } from "react";
import type { Observation, Station } from "@/lib/types";
import { formatDate, formatValue, isRecent } from "@/lib/utils";
import { EmptyState } from "@/components/ui/states";

export function StationMap({ stations, readings = [], variable = "PM25" }: {
  stations: Station[]; readings?: Observation[]; variable?: string;
}) {
  const located = stations.filter((station) => station.latitude && station.longitude &&
    Math.abs(station.latitude) <= 90 && Math.abs(station.longitude) <= 180);
  if (!located.length) return <EmptyState title="No hay estaciones con coordenadas" detail="El mapa no crea posiciones cuando el inventario oficial no publica una ubicación válida." />;
  return <div className="relative h-[360px] overflow-hidden rounded-xl border border-[var(--line)] sm:h-[430px]">
    <MapContainer center={[6.24, -75.58]} zoom={10} scrollWheelZoom={false} className="siata-map" aria-label="Mapa de estaciones">
      <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution="&copy; OpenStreetMap" />
      <Bounds stations={located} />
      {located.map((station) => {
        const reading = readings.find((item) => item.station_id === station.id && item.variable_id === variable);
        const current = reading && isRecent(reading.observed_at) && !["unvalidated_unit", "retrieval_timestamp"].includes(reading.quality_status);
        return <CircleMarker key={station.id} center={[station.latitude!, station.longitude!]} radius={current ? 7 : 4}
          pathOptions={{ color: "#111", weight: 1, fillColor: current ? "#111" : "#fff", fillOpacity: 1 }}>
          <Popup><div className="min-w-40 space-y-1.5 text-xs">
            <strong className="block text-sm">{station.name}</strong>
            <span className="block text-neutral-500">{station.municipality ?? "Valle de Aburrá"}</span>
            {reading ? <><span className="block font-medium">{current ? "Lectura reciente" : "Última lectura"}: {formatValue(reading.value, 2)} {reading.unit}</span><span className="block text-neutral-500">{formatDate(reading.observed_at)}</span></> : <span className="block text-neutral-500">Sin lectura para esta variable</span>}
            <Link className="mt-1 inline-block underline underline-offset-2" href={`/stations/${encodeURIComponent(station.id)}`}>Abrir estación →</Link>
          </div></Popup>
        </CircleMarker>;
      })}
    </MapContainer>
    <div className="pointer-events-none absolute bottom-3 left-3 z-[500] flex flex-wrap items-center gap-3 rounded-md border border-[var(--line)] bg-[var(--surface)]/95 px-2.5 py-1.5 text-[10px] text-[var(--muted)]"><span className="inline-flex items-center gap-1.5"><i className="size-2 rounded-full bg-[var(--fg)]" />Lectura reciente</span><span className="inline-flex items-center gap-1.5"><i className="size-2 rounded-full border border-[var(--fg)]" />Sin lectura validada</span><span>{located.length} ubicaciones · sin interpolación</span></div>
  </div>;
}

function Bounds({ stations }: { stations: Station[] }) {
  const map = useMap();
  useEffect(() => {
    if (stations.length > 1) {
      const bounds = stations.map((station) => [station.latitude!, station.longitude!] as [number, number]) as LatLngBoundsExpression;
      map.fitBounds(bounds, { padding: [28, 28], maxZoom: 12 });
    }
  }, [map, stations]);
  return null;
}
