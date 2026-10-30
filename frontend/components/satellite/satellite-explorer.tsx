"use client";

import { useEffect, useMemo, useState } from "react";
import "leaflet/dist/leaflet.css";
import { CircleMarker, MapContainer, Popup, TileLayer, useMap } from "react-leaflet";
import { CalendarClock, CloudRain, Eye, Layers3, Satellite } from "lucide-react";
import { useGibsLayers, useStations } from "@/lib/hooks/use-siata";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { PageHeading } from "@/components/dashboard/page-heading";
import type { Station } from "@/lib/types";

const LAYERS = {
  imerg: "IMERG_Precipitation_Rate_30min",
  modis: "MODIS_Terra_CorrectedReflectance_TrueColor",
} as const;
const EMPTY_STATIONS: Station[] = [];

export function SatelliteExplorer() {
  const stationsQuery = useStations();
  const layerQuery = useGibsLayers();
  const [layerId, setLayerId] = useState<string>(LAYERS.imerg);
  const [selectedTime, setSelectedTime] = useState("");
  const [network, setNetwork] = useState("air_quality");
  const [tileState, setTileState] = useState<"loading" | "available" | "error">("loading");

  const layer = layerQuery.data?.layers.find((item) => item.id === layerId);
  const located = useMemo(() => (stationsQuery.data ?? EMPTY_STATIONS).filter((station) =>
    (network === "all" || station.station_type === network) &&
    station.latitude !== null && station.longitude !== null &&
    Math.abs(station.latitude) <= 90 && Math.abs(station.longitude) <= 180,
  ), [stationsQuery.data, network]);
  const center = medianCenter(located);

  if (stationsQuery.isLoading || layerQuery.isLoading) return <LoadingState />;
  if (stationsQuery.error || layerQuery.error || !layerQuery.data) return <ErrorState message={stationsQuery.error?.message ?? layerQuery.error?.message ?? "NASA GIBS no devolvió los metadatos de sus capas."} retry={() => { void stationsQuery.refetch(); void layerQuery.refetch(); }} />;
  if (!layer) return <ErrorState message="La capa seleccionada no aparece en las capacidades actuales de NASA GIBS." retry={() => void layerQuery.refetch()} />;
  if (!located.length) return <ErrorState message="El inventario no contiene estaciones geolocalizadas para esta selección." retry={() => void stationsQuery.refetch()} />;

  const isRain = layerId === LAYERS.imerg;
  const activeTime = selectedTime || layer.default_time;
  const tileTime = encodeURIComponent(activeTime);
  const extension = isRain ? "png" : "jpg";
  const tileUrl = `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/${layerId}/default/${tileTime}/${layer.tile_matrix_set}/{z}/{y}/{x}.${extension}`;

  return <div className="space-y-5">
    <PageHeading eyebrow="TELEDETECCIÓN · CAPAS OFICIALES" title="Explorador satelital." description="Teselas NASA GIBS superpuestas a las ubicaciones verificadas de estaciones SIATA. La capa raster conserva su resolución y no se convierte en mediciones puntuales." action={<Badge><Satellite className="size-3" /> NASA GIBS</Badge>} />

    <Card>
      <CardHeader className="flex-wrap items-end"><div><p className="eyebrow">IMAGEN Y PRECIPITACIÓN</p><h2 className="mt-1.5 text-base font-medium">{layer.title}</h2></div><div className="flex flex-wrap gap-2">
        <label className="sr-only" htmlFor="satellite-layer">Producto satelital</label><Select id="satellite-layer" value={layerId} onChange={(event) => { setLayerId(event.target.value); setSelectedTime(""); setTileState("loading"); }} className="text-xs"><option value={LAYERS.imerg}>IMERG · precipitación 30 min</option><option value={LAYERS.modis}>MODIS Terra · color verdadero</option></Select>
        <label className="sr-only" htmlFor="satellite-network">Red de estaciones</label><Select id="satellite-network" value={network} onChange={(event) => setNetwork(event.target.value)} className="text-xs"><option value="air_quality">Calidad del aire</option><option value="meteorology">Meteorología</option><option value="pluviometric">Pluviómetros</option><option value="all">Todas las redes</option></Select>
        <label htmlFor="satellite-time" className="sr-only">{isRain ? "Fecha y hora del producto IMERG" : "Fecha de la imagen MODIS"}</label>
        {isRain ? <input id="satellite-time" aria-label="Fecha y hora del producto IMERG" type="datetime-local" step={1800} value={toLocalDateTime(activeTime)} onChange={(event) => { const value = event.target.value; if (!value) return; const date = new Date(value); date.setMinutes(Math.floor(date.getMinutes() / 30) * 30, 0, 0); setSelectedTime(date.toISOString().replace(/\.\d{3}Z$/, "Z")); setTileState("loading"); }} className="h-9 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2 text-xs" />
          : <input id="satellite-time" aria-label="Fecha de la imagen MODIS" type="date" value={activeTime.slice(0, 10)} max={layer.default_time.slice(0, 10)} onChange={(event) => { setSelectedTime(event.target.value); setTileState("loading"); }} className="h-9 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2 text-xs" />}
      </div></CardHeader>
      <CardContent className="pt-4">
        <div className="relative h-[520px] overflow-hidden rounded-xl border border-[var(--line)] sm:h-[620px]">
          <MapContainer center={center} zoom={9} minZoom={3} maxZoom={12} scrollWheelZoom className="siata-map" aria-label="Mapa satelital NASA con estaciones SIATA">
            <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution="&copy; OpenStreetMap" />
            <TileLayer key={tileUrl} url={tileUrl} opacity={isRain ? 0.78 : 0.88} maxNativeZoom={layer.max_zoom ?? 9}
              attribution="NASA GIBS / Earthdata" eventHandlers={{ load: () => setTileState("available"), tileerror: () => setTileState("error") }} />
            <MapBounds stations={located} />
            {located.map((station) => <CircleMarker key={station.id} center={[station.latitude!, station.longitude!]} radius={4} pathOptions={{ color: "#111", weight: 1, fillColor: "#fff", fillOpacity: 1 }}>
              <Popup><div className="min-w-40 space-y-1.5 text-xs"><strong className="block">{station.name}</strong><span className="block text-neutral-500">{station.municipality ?? "Valle de Aburrá"}</span><span className="block font-mono text-[10px]">{station.latitude?.toFixed(5)}, {station.longitude?.toFixed(5)}</span><span className="block text-neutral-500">La imagen no representa una lectura de esta estación.</span></div></Popup>
            </CircleMarker>)}
          </MapContainer>
          <div className="pointer-events-none absolute left-3 top-3 z-[500] flex flex-wrap gap-2">
            <Badge className="bg-[var(--surface)]/95"><span className={`size-1.5 rounded-full ${tileState === "available" ? "bg-[var(--fg)]" : tileState === "error" ? "bg-[var(--muted)]" : "animate-pulse bg-[var(--fg)]"}`} />{tileState === "available" ? "Teselas recibidas" : tileState === "error" ? "Teselas no disponibles" : "Consultando NASA GIBS"}</Badge>
            <Badge className="bg-[var(--surface)]/95">{located.length} estaciones · sin interpolación</Badge>
          </div>
          <div className="pointer-events-none absolute bottom-3 left-3 z-[500] rounded-md border border-[var(--line)] bg-[var(--surface)]/95 px-3 py-2 text-[10px] leading-4 text-[var(--muted)]"><span className="font-medium text-[var(--fg)]">{isRain ? "IMERG Early · 30 min · 0.1°" : "MODIS Terra · color verdadero"}</span><br />Vigencia {activeTime} · producto de visualización</div>
        </div>
      </CardContent>
    </Card>

    <div className="grid gap-3 sm:grid-cols-3">
      <ContextCard icon={CloudRain} title="IMERG no es pluviómetro" detail="La capa muestra precipitación estimada por satélite en una grilla de ~10 km; no sustituye sensores SIATA." />
      <ContextCard icon={CalendarClock} title="Tiempo del producto" detail={`Último tiempo publicado por GIBS: ${layer.default_time}. La selección puede estar limitada por la disponibilidad de teselas.`} />
      <ContextCard icon={Layers3} title="Solo raster de visualización" detail="Las teselas no se descargan ni se leen como datos para Machine Learning. Para análisis cuantitativo se requiere el producto geoespacial original y su procedencia." />
    </div>
  </div>;
}

function ContextCard({ icon: Icon, title, detail }: { icon: typeof Eye; title: string; detail: string }) {
  return <Card><CardContent className="flex gap-3 py-4"><Icon className="mt-0.5 size-4 shrink-0 text-[var(--muted)]" /><div><h3 className="text-xs font-medium">{title}</h3><p className="mt-1.5 text-[10px] leading-4 text-[var(--muted)]">{detail}</p></div></CardContent></Card>;
}

function medianCenter(stations: Station[]): [number, number] {
  const median = (values: number[]) => {
    const sorted = values.slice().sort((a, b) => a - b);
    return sorted.length ? sorted[Math.floor(sorted.length / 2)] : 0;
  };
  return [median(stations.map((station) => station.latitude!)), median(stations.map((station) => station.longitude!))];
}

function toLocalDateTime(value: string) {
  if (!value) return "";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "";
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

function MapBounds({ stations }: { stations: Station[] }) {
  const map = useMap();
  useEffect(() => {
    if (stations.length > 1) map.fitBounds(stations.map((station) => [station.latitude!, station.longitude!]), { padding: [24, 24], maxZoom: 10 });
  }, [map, stations]);
  return null;
}
