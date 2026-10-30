"use client";

import "leaflet/dist/leaflet.css";
import Image from "next/image";
import Link from "next/link";
import { useMemo, useState } from "react";
import { Circle, CircleMarker, MapContainer, Popup, TileLayer, useMap } from "react-leaflet";
import type { LatLngBoundsExpression } from "leaflet";
import { useEffect, useRef } from "react";
import type { GibsLayer, Observation, RegionalForecast, Station } from "@/lib/types";
import { useGibsLayers } from "@/lib/hooks/use-siata";
import { OpenFreeMapLayer } from "@/components/stations/openfreemap-layer";
import { formatDate, formatValue, isRecent, parseUtcDate } from "@/lib/utils";
import { EmptyState } from "@/components/ui/states";

const INVALID_QUALITY = new Set(["unvalidated_unit", "retrieval_timestamp", "extreme_value", "doubtful", "unvalidated"]);
const COLOR_RAMP = ["#2878b5", "#36a889", "#d8c34a", "#ef8a36", "#bf3b46"];
const GIBS_LAYERS = [
  ["IMERG_Precipitation_Rate_30min", "NASA GPM · IMERG (lluvia)"],
  ["MODIS_Terra_CorrectedReflectance_TrueColor", "NASA MODIS · color verdadero"],
] as const;
const OBSERVED_LAYERS = [
  ["PM25", "PM2.5", "µg/m³"], ["PM10", "PM10", "µg/m³"], ["O3", "Ozono", "µg/m³"], ["NO2", "NO₂", "µg/m³"],
  ["temperature", "Temperatura", "°C"], ["humidity", "Humedad", "%"], ["wind_speed", "Viento", "m/s"],
  ["wind_direction", "Dirección del viento", "°"], ["pressure", "Presión", "hPa"], ["rain", "Lluvia · captura SIATA", "unidad de origen"],
  ["river_level", "Nivel · captura SIATA", "unidad de origen"],
] as const;
const MODEL_LAYERS = [
  ["rain_probability", "Open-Meteo · probabilidad de lluvia", "%"], ["rain", "Open-Meteo · precipitación", "mm"],
  ["temperature", "Open-Meteo · temperatura", "°C"], ["humidity", "Open-Meteo · humedad", "%"],
  ["wind_speed", "Open-Meteo · viento", "m/s"], ["cloud_cover", "Open-Meteo · nubosidad", "%"],
] as const;

type Props = {
  stations: Station[];
  readings?: Observation[];
  variable?: string;
  regionalForecasts?: Record<string, RegionalForecast>;
};

export function StationMap({ stations, readings = [], variable = "PM25", regionalForecasts = {} }: Props) {
  const [layerId, setLayerId] = useState(variable);
  const [satellite, setSatellite] = useState(false);
  const [opacity, setOpacity] = useState(72);
  const [frameIndex, setFrameIndex] = useState<number | null>(null);
  const [heat, setHeat] = useState(false);
  const [satelliteId, setSatelliteId] = useState<string>(GIBS_LAYERS[0][0]);
  const [tileState, setTileState] = useState<"loading" | "available" | "error">("loading");
  const gibsQuery = useGibsLayers();
  const located = useMemo(() => stations.filter((station) => station.latitude != null && station.longitude != null &&
    Math.abs(station.latitude) <= 90 && Math.abs(station.longitude) <= 180), [stations]);
  const isModel = layerId.startsWith("model:");
  const modelVariable = isModel ? layerId.slice(6) : "";
  const satelliteLayer = gibsQuery.data?.layers.find((layer) => layer.id === satelliteId);
  const frames = useMemo(() => satelliteLayer ? availableFrames(satelliteLayer) : [], [satelliteLayer]);
  const resolvedFrameIndex = frameIndex == null ? Math.max(0, frames.length - 1) : Math.min(frameIndex, Math.max(0, frames.length - 1));
  const frame = frames[resolvedFrameIndex] ?? satelliteLayer?.default_time;

  const latestReadings = useMemo(() => {
    const latest = new Map<string, Observation>();
    for (const reading of readings) {
      const key = `${reading.station_id}:${reading.variable_id}`;
      const existing = latest.get(key);
      if (!existing || (parseUtcDate(reading.observed_at)?.getTime() ?? 0) > (parseUtcDate(existing.observed_at)?.getTime() ?? 0)) latest.set(key, reading);
    }
    return latest;
  }, [readings]);
  const selectedReadings = isModel ? [] : located.flatMap((station) => {
    const reading = latestReadings.get(`${station.id}:${layerId}`);
    return reading ? [{ station, reading, valid: isRecent(reading.observed_at) && !INVALID_QUALITY.has(reading.quality_status) }] : [];
  });
  const validValues = selectedReadings.filter((item) => item.valid).map((item) => item.reading.value);
  const min = validValues.length ? Math.min(...validValues) : null;
  const max = validValues.length ? Math.max(...validValues) : null;
  const model = regionalForecasts[modelVariable];
  const unit = isModel
    ? MODEL_LAYERS.find(([id]) => id === modelVariable)?.[2] ?? model?.unit ?? ""
    : OBSERVED_LAYERS.find(([id]) => id === layerId)?.[2] ?? "";
  const layerLabel = isModel
    ? MODEL_LAYERS.find(([id]) => id === modelVariable)?.[1] ?? modelVariable
    : OBSERVED_LAYERS.find(([id]) => id === layerId)?.[1] ?? layerId;
  const tileExtension = satelliteLayer?.formats.some((format) => format.includes("jpeg")) ? "jpg" : "png";
  const gibsTileUrl = satelliteLayer && frame
    ? `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/${satelliteLayer.id}/default/${encodeURIComponent(frame)}/${satelliteLayer.tile_matrix_set}/{z}/{y}/{x}.${tileExtension}`
    : null;
  if (!located.length) return <EmptyState title="No hay estaciones con coordenadas" detail="El mapa no crea posiciones cuando el inventario oficial no publica una ubicación válida." />;

  const enoughForHeat = validValues.length >= 8;
  return <div className="space-y-3">
    <div className="flex flex-wrap items-end justify-between gap-3">
      <label className="grid gap-1 text-[10px] text-[var(--muted)]">Capa de datos
        <select value={layerId} onChange={(event) => { setLayerId(event.target.value); setHeat(false); }} className="min-h-9 min-w-56 rounded-md border border-[var(--line)] bg-[var(--surface)] px-2.5 text-xs text-[var(--fg)]">
          <optgroup label="Observaciones SIATA">{OBSERVED_LAYERS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}</optgroup>
          <optgroup label="Pronóstico regional · Open-Meteo">{MODEL_LAYERS.map(([id, label]) => <option key={id} value={`model:${id}`}>{label}</option>)}</optgroup>
        </select>
      </label>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-[10px] text-[var(--muted)]">
        {!isModel && <button type="button" disabled={!enoughForHeat} onClick={() => setHeat((value) => !value)} aria-pressed={heat}
          title={enoughForHeat ? "Densidad visual de las estaciones disponibles" : "Se requieren al menos 8 lecturas válidas y recientes"}
          className="rounded-md border border-[var(--line)] px-2.5 py-2 disabled:cursor-not-allowed disabled:opacity-50">{heat ? "Ocultar densidad" : `Densidad visual · ${validValues.length} puntos`}</button>}
        <label className="inline-flex items-center gap-2"><input type="checkbox" checked={satellite} onChange={(event) => { setSatellite(event.target.checked); if (event.target.checked) setTileState("loading"); }} /> Imágenes NASA GIBS</label>
        {satellite && <select value={satelliteId} onChange={(event) => { setSatelliteId(event.target.value); setFrameIndex(null); setTileState("loading"); }} aria-label="Producto satelital" className="min-h-9 rounded-md border border-[var(--line)] bg-[var(--surface)] px-2 text-[10px] text-[var(--fg)]">
          {GIBS_LAYERS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
        </select>}
      </div>
    </div>

    <div className="relative h-[390px] overflow-hidden rounded-xl border border-[var(--line)] sm:h-[490px]">
      <MapContainer center={[6.24, -75.58]} zoom={10} scrollWheelZoom className="siata-map" aria-label="Mapa geográfico multicapas del Valle de Aburrá">
        <OpenFreeMapLayer />
        {satellite && gibsTileUrl && <TileLayer key={gibsTileUrl} url={gibsTileUrl} opacity={opacity / 100} maxNativeZoom={satelliteLayer?.max_zoom ?? 6}
          attribution="NASA GIBS / GPM IMERG" eventHandlers={{ load: () => setTileState("available"), tileerror: () => setTileState("error") }} />}
        <Bounds stations={located} />
        {heat && enoughForHeat && !isModel && selectedReadings.filter((item) => item.valid).map(({ station, reading }) => <Circle key={`density:${station.id}`}
          center={[station.latitude!, station.longitude!]} radius={850} pathOptions={{ color: "transparent", weight: 0, fillColor: valueColor(reading.value, min!, max!), fillOpacity: .19 }} />)}
        {located.map((station) => {
          const reading = isModel ? null : latestReadings.get(`${station.id}:${layerId}`);
          const valid = Boolean(reading && isRecent(reading.observed_at) && !INVALID_QUALITY.has(reading.quality_status));
          const color = valid && reading ? valueColor(reading.value, min!, max!) : "#ffffff";
          return <CircleMarker key={station.id} center={[station.latitude!, station.longitude!]} radius={valid ? 6.5 : 4}
            pathOptions={{ color: "#26313b", weight: valid ? 1.5 : 1, fillColor: color, fillOpacity: valid ? .96 : .85 }}>
            <Popup><div className="min-w-44 space-y-1.5 text-xs">
              <strong className="block text-sm">{station.name}</strong><span className="block text-neutral-500">{station.municipality ?? "Valle de Aburrá"} · {station.station_type}</span>
              {reading ? <><span className="block font-medium">{layerLabel}: {formatValue(reading.value, 2)} {reading.unit}</span>
                <span className="block text-neutral-500">{valid ? "Observación SIATA validada · " : `${reading.quality_status} · `}{formatDate(reading.observed_at)}</span></>
                : <span className="block text-neutral-500">{isModel ? "El pronóstico es regional y no se atribuye a esta estación." : "Sin registro para la variable seleccionada."}</span>}
              <span className="block font-mono text-[10px] text-neutral-500">{station.latitude?.toFixed(5)}, {station.longitude?.toFixed(5)}</span>
              <Link className="mt-1 inline-block underline underline-offset-2" href={`/stations/${encodeURIComponent(station.id)}`}>Abrir estación →</Link>
            </div></Popup>
          </CircleMarker>;
        })}
        {isModel && model?.status === "available" && model.latitude != null && model.longitude != null && <CircleMarker
          center={[model.latitude, model.longitude]} radius={13} pathOptions={{ color: "#f5a623", weight: 3, fillColor: "#f5a623", fillOpacity: .38 }}>
          <Popup><div className="space-y-1 text-xs"><strong>{layerLabel}</strong><p>Celda regional de modelo · {formatValue(model.forecast[0]?.value)} {unit}</p><p>Válido {formatDate(model.forecast[0]?.timestamp)}</p><p>Resolución: {model.spatial_resolution ?? "publicada por proveedor"}</p></div></Popup>
        </CircleMarker>}
      </MapContainer>

      <div className="pointer-events-none absolute left-3 top-3 z-[500] rounded-md border border-[var(--line)] bg-[var(--surface)]/95 px-3 py-2 text-[10px] shadow-sm">
        <p className="font-medium text-[var(--fg)]">{isModel ? "OPEN-METEO · MODELO REGIONAL" : "SIATA · OBSERVACIONES POR ESTACIÓN"}</p>
        <p className="mt-1 text-[var(--muted)]">{layerLabel} · {isModel ? model?.status === "available" ? `celda ${model.spatial_resolution ?? "regional"}` : "sin pronóstico persistido" : `${validValues.length}/${located.length} lecturas válidas · últimas 3 h`}</p>
        {!isModel && validValues.length > 0 && <div className="mt-1.5 flex items-center gap-2"><span>{formatValue(min)} {unit}</span><i className="h-1.5 w-24 rounded-full" style={{ background: `linear-gradient(90deg, ${COLOR_RAMP.join(", ")})` }} /><span>{formatValue(max)} {unit}</span></div>}
        {heat && <p className="mt-1.5 max-w-60 text-[9px] text-[var(--muted)]">Densidad visual alrededor de sensores · no es interpolación ni un valor estimado entre estaciones.</p>}
      </div>

      {satellite && <div className="absolute bottom-3 left-3 right-3 z-[500] rounded-md border border-[var(--line)] bg-[var(--surface)]/95 p-2.5 shadow-sm sm:right-auto sm:min-w-[320px]">
        <div className="flex items-center justify-between gap-3 text-[10px]"><span className="font-medium">{GIBS_LAYERS.find(([id]) => id === satelliteId)?.[1] ?? "NASA GIBS"}</span><span className="text-[var(--muted)]">{tileState === "error" ? "Teselas no disponibles · " : tileState === "available" ? "Teselas cargadas · " : "Consultando teselas · "}{frame ?? "sin fecha"}</span></div>
        {satelliteLayer?.legend_url && <div className="mt-1.5 flex items-center gap-2"><Image src={satelliteLayer.legend_url} alt="Leyenda oficial NASA GIBS para precipitación IMERG" width={500} height={60} unoptimized className="max-h-8 max-w-full object-contain" /><span className="text-[9px] text-[var(--muted)]">Leyenda de NASA GIBS</span></div>}
        {satelliteId === "IMERG_Precipitation_Rate_30min" && <p className="mt-1 text-[9px] text-[var(--muted)]">Estimación satelital de tasa de lluvia; no es pluviómetro.</p>}
        <div className="mt-2 grid grid-cols-[auto_1fr_auto] items-center gap-2 text-[9px] text-[var(--muted)]"><span>Opacidad</span><input aria-label="Opacidad de la capa IMERG" type="range" min="15" max="100" step="5" value={opacity} onChange={(event) => setOpacity(Number(event.target.value))} /><span>{opacity}%</span></div>
        {frames.length > 1 && <div className="mt-2 grid grid-cols-[auto_1fr_auto] items-center gap-2 text-[9px] text-[var(--muted)]"><span>Tiempo</span><input aria-label="Tiempo de la capa NASA" type="range" min="0" max={frames.length - 1} value={resolvedFrameIndex} onChange={(event) => { setFrameIndex(Number(event.target.value)); setTileState("loading"); }} /><span>{frames.length} escenas</span></div>}
        <p className="mt-1 text-[9px] text-[var(--muted)]">Tiempos elegibles según rangos publicados por GIBS; la disponibilidad de teselas puede variar.</p>
      </div>}
      {satellite && !satelliteLayer && <div className="absolute bottom-3 left-3 z-[500] rounded-md border border-[var(--line)] bg-[var(--surface)]/95 px-3 py-2 text-[10px]">{gibsQuery.isError ? "Metadatos GIBS no disponibles" : "Cargando metadatos NASA GIBS…"}</div>}
    </div>
    <p className="text-[10px] leading-4 text-[var(--muted)]">Base vectorial OpenFreeMap · OpenStreetMap · sin clave ni cuota publicada. Círculos en color = observaciones SIATA recientes y válidas; círculo ámbar = celda del pronóstico Open-Meteo; raster NASA = estimación IMERG. No se infieren valores donde no hay sensores.</p>
  </div>;
}

function availableFrames(layer: GibsLayer): string[] {
  const end = parseUtcDate(layer.default_time)?.getTime();
  if (end == null) return [layer.default_time];
  const range = layer.time_ranges.find((entry) => {
    const [startText, endText] = entry.split("/");
    const start = parseUtcDate(startText)?.getTime();
    const limit = parseUtcDate(endText)?.getTime();
    return start != null && limit != null && start <= end && end <= limit;
  });
  if (!range) return [layer.default_time];
  const [startText, endText, period] = range.split("/");
  const start = parseUtcDate(startText)?.getTime();
  const limit = parseUtcDate(endText)?.getTime();
  if (start == null || limit == null) return [layer.default_time];
  const step = period === "PT30M" ? 30 * 60_000 : period === "P1D" ? 24 * 60 * 60_000 : null;
  if (!step) return [layer.default_time];
  const last = Math.min(end, limit);
  const frames: string[] = [];
  for (let time = last; time >= start && frames.length < 17; time -= step) {
    const iso = new Date(time).toISOString();
    frames.push(period === "P1D" ? iso.slice(0, 10) : iso.replace(/\.000Z$/, "Z"));
  }
  return frames.reverse();
}

function valueColor(value: number, min: number, max: number) {
  const ratio = max === min ? .5 : Math.max(0, Math.min(1, (value - min) / (max - min)));
  return COLOR_RAMP[Math.min(COLOR_RAMP.length - 1, Math.floor(ratio * COLOR_RAMP.length))];
}

function Bounds({ stations }: { stations: Station[] }) {
  const map = useMap();
  const fitted = useRef(false);
  useEffect(() => {
    if (stations.length > 1 && !fitted.current) {
      const bounds = stations.map((station) => [station.latitude!, station.longitude!] as [number, number]) as LatLngBoundsExpression;
      map.fitBounds(bounds, { padding: [28, 28], maxZoom: 12 });
      fitted.current = true;
    }
  }, [map, stations]);
  return null;
}
