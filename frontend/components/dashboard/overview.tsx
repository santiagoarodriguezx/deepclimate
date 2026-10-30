"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Activity, ArrowRight, CloudRain, Droplets, Gauge, MapPin, Thermometer, Wind } from "lucide-react";
import { getLatest } from "@/lib/api";
import { useEvents, useFreshness, useLatest, useRegionalForecast, useStations, useTimeSeries } from "@/lib/hooks/use-siata";
import { useQueryClient } from "@tanstack/react-query";
import { formatDate, formatValue, humanLag, isRecent } from "@/lib/utils";
import { variableMeta } from "@/lib/types";
import type { Observation } from "@/lib/types";
import type { Station } from "@/lib/types";
import { PageHeading } from "@/components/dashboard/page-heading";
import { MetricCard } from "@/components/dashboard/metric-card";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { RegionalForecastChart, TimeSeriesChart } from "@/components/charts/time-series-chart";
import { MapLoader } from "@/components/stations/map-loader";

const chartVariables = ["PM25", "PM10", "temperature", "humidity", "rain"];
const qualityExcluded = new Set(["unvalidated_unit", "retrieval_timestamp"]);
const EMPTY_STATIONS: Station[] = [];

export function Overview() {
  const [variable, setVariable] = useState("PM25");
  const [days, setDays] = useState(7);
  const [municipality, setMunicipality] = useState("all");
  const [stationId, setStationId] = useState("");
  const queryClient = useQueryClient();
  const stationsQuery = useStations();
  const pmQuery = useLatest("PM25");
  const temperatureQuery = useLatest("temperature");
  const humidityQuery = useLatest("humidity");
  const rainQuery = useLatest("rain");
  const freshnessQuery = useFreshness("PM25");
  const eventsQuery = useEvents();
  const regionalRainForecast = useRegionalForecast("rain_probability", 24);
  const regionalTemperatureForecast = useRegionalForecast("temperature", 24);
  const stations = stationsQuery.data ?? EMPTY_STATIONS;
  const readings = pmQuery.data ?? [];
  const municipalities = useMemo(() => {
    const labels = new Map<string, string>();
    stations.forEach((station) => {
      if (station.municipality) labels.set(municipalityKey(station.municipality), cleanMunicipality(station.municipality));
    });
    return [...labels.entries()].sort((a, b) => a[1].localeCompare(b[1], "es"));
  }, [stations]);
  const municipalityStations = stations.filter((station) => municipality === "all" || municipalityKey(station.municipality ?? "") === municipality);
  const networkTypes = variable === "temperature" || variable === "humidity" ? ["meteorology"] : variable === "rain" ? ["meteorology", "pluviometric"] : variable === "river_level" ? ["stream_level"] : ["air_quality"];
  const scopedStations = municipalityStations.filter((station) => networkTypes.includes(station.station_type));
  const recentAir = readings.filter((reading) => isRecent(reading.observed_at) && !qualityExcluded.has(reading.quality_status));
  const latestVariable = useQuery({ queryKey: ["latest", variable], queryFn: () => getLatest(variable), enabled: variable !== "PM25", staleTime: 30_000 });
  const variableRows = variable === "PM25" ? readings : latestVariable.data ?? [];
  const scopedIds = new Set(scopedStations.map((station) => station.id));
  const freshestStation = variableRows.filter((row) => scopedIds.has(row.station_id) && !qualityExcluded.has(row.quality_status))
    .slice().sort((a, b) => Date.parse(b.observed_at) - Date.parse(a.observed_at))[0]?.station_id;
  const selected = (stationId && scopedIds.has(stationId) ? stationId : "") || freshestStation || scopedStations[0]?.id || "";
  const visibleStationIds = new Set(municipalityStations.map((station) => station.id));
  const seriesStation = useTimeSeries(selected, variable, days);
  const currentReadings = (rows: Observation[] | undefined) => (rows ?? []).filter((row) => isRecent(row.observed_at) && !qualityExcluded.has(row.quality_status));
  const currentTemperature = currentReadings(temperatureQuery.data);
  const currentHumidity = currentReadings(humidityQuery.data);
  const rainSnapshots = (rainQuery.data ?? []).filter((row) => qualityExcluded.has(row.quality_status) || !isRecent(row.observed_at));
  const average = (values: Observation[]) => values.length ? values.reduce((total, item) => total + item.value, 0) / values.length : null;
  const mapStations = municipalityStations;
  const mapReadings = variableRows.filter((row) => visibleStationIds.has(row.station_id));
  const series = seriesStation.data?.series ?? [];
  const events = eventsQuery.data ?? [];
  const rainForecastPoints = regionalRainForecast.data?.forecast ?? [];
  const temperatureForecastPoints = regionalTemperatureForecast.data?.forecast ?? [];
  const peakRainPoint = rainForecastPoints.reduce<(typeof rainForecastPoints)[number] | null>(
    (best, point) => !best || point.value > best.value ? point : best,
    null,
  );
  const temperatureRange = temperatureForecastPoints.length ? {
    min: Math.min(...temperatureForecastPoints.map((point) => point.value)),
    max: Math.max(...temperatureForecastPoints.map((point) => point.value)),
  } : null;
  const unavailable = [stationsQuery.error, pmQuery.error, freshnessQuery.error].find(Boolean) as Error | undefined;

  return <motion.div initial={{ opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .28 }}>
    <PageHeading eyebrow="INTELIGENCIA AMBIENTAL · VALLE DE ABURRÁ" title="El estado de la red, en contexto." description="Observaciones publicadas por SIATA, frescura por estación y análisis conectados a mediciones reales." action={<span className="flex items-center gap-2 text-xs text-[var(--muted)]"><span className="size-1.5 rounded-full bg-[var(--fg)]" /> Actualizado {formatDate(freshnessQuery.data?.checked_at)}</span>} />
    {unavailable && <div className="mb-5"><ErrorState message={`No se pudieron consultar todos los datos: ${unavailable.message}`} retry={() => { void stationsQuery.refetch(); void pmQuery.refetch(); void freshnessQuery.refetch(); }} /></div>}

    <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Indicadores ambientales">
      <MetricCard label="PM2.5 promedio" value={formatValue(average(recentAir))} unit="µg/m³" detail={`${recentAir.length} estaciones · dato ≤ 3 h`} icon={Gauge} />
      <MetricCard label="Temperatura media" value={formatValue(average(currentTemperature))} unit="°C" detail={`${currentTemperature.length} telemetrías con hora`} icon={Thermometer} />
      <MetricCard label="Humedad relativa" value={formatValue(average(currentHumidity))} unit="%" detail={`${currentHumidity.length} telemetrías con hora`} icon={Droplets} />
      <MetricCard label="Red PM2.5 disponible" value={freshnessQuery.data ? `${freshnessQuery.data.stations_online}/${freshnessQuery.data.total_stations}` : "—"} detail={freshnessQuery.data ? `Rezago medio ${humanLag(freshnessQuery.data.average_lag_seconds)}` : "Esperando estado de estaciones"} icon={Activity} />
    </section>

    {rainSnapshots.length > 0 && <div className="mt-3 flex items-start gap-2 rounded-xl border border-[var(--line)] bg-[var(--surface)] px-4 py-3 text-xs leading-5 text-[var(--muted)]"><CloudRain className="mt-0.5 size-4 shrink-0" /><span><strong className="font-medium text-[var(--fg)]">{rainSnapshots.length} pluviómetros con captura.</strong> SIATA no publica la hora de observación ni el intervalo de acumulación en estos feeds; por eso no se presenta como intensidad actual.</span></div>}

    <div className="mt-5 grid gap-4 xl:grid-cols-[minmax(0,1.65fr)_minmax(300px,.85fr)]">
      <Card className="min-w-0">
        <CardHeader className="flex-wrap items-end"><div><p className="eyebrow">EVOLUCIÓN OBSERVADA</p><h3 className="mt-1.5 text-base font-medium">{variableMeta(variable).label} por estación</h3></div>
          <div className="flex flex-wrap gap-2">
            <label className="sr-only" htmlFor="overview-zone">Zona / municipio</label><Select id="overview-zone" value={municipality} onChange={(e) => { setMunicipality(e.target.value); setStationId(""); }} className="max-w-[150px] text-xs"><option value="all">Todos los municipios</option>{municipalities.map(([key, name]) => <option key={key} value={key}>{name}</option>)}</Select>
            <label className="sr-only" htmlFor="overview-station">Estación</label><Select id="overview-station" value={selected} onChange={(e) => setStationId(e.target.value)} className="max-w-[190px] text-xs"><option value="">Seleccionar estación</option>{scopedStations.map((station) => <option key={station.id} value={station.id}>{station.name}</option>)}</Select>
            <label className="sr-only" htmlFor="overview-variable">Variable</label><Select id="overview-variable" value={variable} onChange={(e) => { setVariable(e.target.value); setStationId(""); }} className="text-xs">{chartVariables.map((id) => <option key={id} value={id}>{variableMeta(id).label}</option>)}</Select>
            <label className="sr-only" htmlFor="overview-range">Periodo</label><Select id="overview-range" value={days} onChange={(e) => setDays(Number(e.target.value))} className="text-xs"><option value={1}>24 horas</option><option value={7}>7 días</option><option value={30}>30 días</option></Select>
          </div>
        </CardHeader>
        <CardContent className="pt-4">{variable === "rain" ? <EmptyState title="Historial no comparable" detail="El feed actual no publica hora de observación ni periodo de acumulación; no se grafica una captura como serie horaria." /> : <TimeSeriesChart points={series} variable={variable} loading={seriesStation.isLoading} error={seriesStation.error?.message} label={stations.find((item) => item.id === selected)?.name} />}</CardContent>
      </Card>

      <Card>
        <CardHeader><div><p className="eyebrow">SEÑALES RECIENTES</p><h3 className="mt-1.5 text-base font-medium">Lecturas destacadas</h3></div><Badge>≤ 3 h</Badge></CardHeader>
        <CardContent className="pt-4">
          {pmQuery.isLoading ? <LoadingState /> : recentAir.filter((row) => visibleStationIds.has(row.station_id)).length ? <div className="divide-y divide-[var(--line)]">{recentAir.filter((row) => visibleStationIds.has(row.station_id)).slice().sort((a, b) => b.value - a.value).slice(0, 7).map((row) => <Link key={row.station_id} href={`/stations/${encodeURIComponent(row.station_id)}`} className="flex items-center justify-between gap-3 py-3 first:pt-0 last:pb-0"><div className="min-w-0"><p className="truncate text-xs font-medium">{row.station_name ?? row.station_code ?? row.station_id}</p><p className="mt-1 truncate text-[10px] text-[var(--muted)]">{cleanMunicipality(row.municipality ?? "Valle de Aburrá")} · {formatDate(row.observed_at)}</p></div><span className="shrink-0 font-mono text-sm">{formatValue(row.value)}<span className="ml-1 text-[9px] text-[var(--muted)]">µg/m³</span></span></Link>)}</div> : <EmptyState title="Sin lecturas PM2.5 recientes" detail="La tabla conserva el histórico, pero este panel solo resume observaciones de las últimas tres horas." />}
          <Link className="mt-4 flex items-center gap-1 text-xs text-[var(--muted)] hover:text-[var(--fg)]" href="/stations">Explorar estaciones <ArrowRight className="size-3.5" /></Link>
        </CardContent>
      </Card>
    </div>

    <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.55fr)_minmax(260px,.75fr)]">
      <Card className="min-w-0">
        <CardHeader><div><p className="eyebrow">PRONÓSTICO DE MODELO EXTERNO</p><h3 className="mt-1.5 text-base font-medium">Probabilidad de precipitación · 24 h</h3></div><Badge>{regionalRainForecast.data?.source_name ?? "Open-Meteo"}</Badge></CardHeader>
        <CardContent className="pt-3">{regionalRainForecast.isLoading ? <LoadingState /> : regionalRainForecast.error ? <ErrorState message={regionalRainForecast.error.message} retry={() => void regionalRainForecast.refetch()} /> : <RegionalForecastChart points={rainForecastPoints} variable="rain_probability" unit="%" />}</CardContent>
      </Card>
      <Card>
        <CardHeader><div><p className="eyebrow">CONTEXTO REGIONAL</p><h3 className="mt-1.5 text-base font-medium">Señal de los modelos</h3></div><CloudRain className="size-4 text-[var(--muted)]" /></CardHeader>
        <CardContent className="pt-4">
          <div className="rounded-xl border border-[var(--line)] p-3.5"><p className="text-[10px] text-[var(--muted)]">Mayor probabilidad horaria prevista</p><p className="mt-1.5 text-2xl font-medium">{peakRainPoint ? `${formatValue(peakRainPoint.value, 0)}%` : "—"}</p><p className="mt-1 text-[10px] text-[var(--muted)]">{peakRainPoint ? formatDate(peakRainPoint.timestamp) : "Sin valores de pronóstico disponibles"}</p></div>
          <div className="mt-2 rounded-xl border border-[var(--line)] p-3.5"><p className="text-[10px] text-[var(--muted)]">Rango térmico previsto</p><p className="mt-1.5 text-lg font-medium">{temperatureRange ? `${formatValue(temperatureRange.min)}–${formatValue(temperatureRange.max)} °C` : "—"}</p><p className="mt-1 text-[10px] text-[var(--muted)]">{regionalTemperatureForecast.data?.generated_at ? `Captura ${formatDate(regionalTemperatureForecast.data.generated_at)} UTC` : "Esperando el siguiente ciclo del conector"}</p></div>
          <p className="mt-3 text-[10px] leading-4 text-[var(--muted)]">Pronóstico de modelo por celda regional. No es una observación local ni un pronóstico emitido por SIATA.</p>
        </CardContent>
      </Card>
    </div>

    <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.65fr)_minmax(300px,.85fr)]">
      <Card className="overflow-hidden">
        <CardHeader><div><p className="eyebrow">DISTRIBUCIÓN GEOESPACIAL</p><h3 className="mt-1.5 text-base font-medium">Estaciones y última lectura</h3></div><Badge><MapPin className="size-3" />{mapStations.length} estaciones</Badge></CardHeader>
        <CardContent className="pt-4"><MapLoader stations={mapStations} readings={mapReadings} variable={variable} /></CardContent>
      </Card>
      <Card>
        <CardHeader><div><p className="eyebrow">ALERTAS Y DISPONIBILIDAD</p><h3 className="mt-1.5 text-base font-medium">Estado operativo</h3></div><Badge>{events.length} activas</Badge></CardHeader>
        <CardContent className="pt-4">
          <FreshnessList status={freshnessQuery.data?.status_distribution} total={freshnessQuery.data?.total_stations ?? 0} />
          <div className="my-5 border-t border-[var(--line)]" />
          {events.length ? <div className="space-y-3">{events.slice(0, 4).map((event) => <div key={`${event.event_type}:${event.station_ids.join(",")}`} className="border-l-2 border-[var(--fg)] pl-3"><div className="flex items-center justify-between gap-2"><p className="text-xs font-medium">{event.title}</p><span className="text-[9px] uppercase tracking-wider text-[var(--muted)]">{event.severity}</span></div><p className="mt-1.5 text-[10px] leading-4 text-[var(--muted)]">{event.description}</p><p className="mt-1.5 text-[9px] text-[var(--muted)]">{formatDate(event.detected_at)}</p></div>)}</div> : <EmptyState title="Sin alertas activas" detail="Los eventos se generan con lecturas PM2.5 válidas y recientes." />}
        </CardContent>
      </Card>
    </div>

    <Card className="mt-4">
      <CardHeader><div><p className="eyebrow">RED DE SENSORES</p><h3 className="mt-1.5 text-base font-medium">Mapa de datos ambientales</h3></div><Badge>{stations.length} estaciones activas</Badge></CardHeader>
      <CardContent className="grid gap-3 pt-4 sm:grid-cols-3">
        <SignalSummary icon={Wind} label="Temperatura" data={currentTemperature} unit="°C" />
        <SignalSummary icon={Droplets} label="Humedad relativa" data={currentHumidity} unit="%" />
        <SignalSummary icon={CloudRain} label="Captura de lluvia" data={(rainQuery.data ?? []).filter((row) => visibleStationIds.has(row.station_id))} unit="capturas · intervalo sin publicar" caveat="No es una tasa de lluvia." />
      </CardContent>
    </Card>
    <div className="mt-4 flex justify-end gap-4"><Button variant="ghost" size="sm" onClick={() => { void queryClient.invalidateQueries(); }}><Activity className="size-3.5" />Actualizar panel</Button><Link href="/models" className="inline-flex items-center gap-1 text-xs text-[var(--muted)] hover:text-[var(--fg)]">Abrir laboratorio ML <ArrowRight className="size-3.5" /></Link></div>
  </motion.div>;
}

function FreshnessList({ status, total }: { status?: Record<string, number>; total: number }) {
  const rows = [["HEALTHY", "Recientes"], ["DELAYED", "Con demora"], ["STALE", "Antiguas"], ["OFFLINE", "Sin señal"], ["UNKNOWN", "Sin registro"]] as const;
  return <div className="space-y-3">{rows.map(([key, label]) => {
    const count = status?.[key] ?? 0;
    const pct = total ? Math.round((count / total) * 100) : 0;
    return <div key={key} className="grid grid-cols-[88px_1fr_25px] items-center gap-2.5"><span className="text-[10px] text-[var(--muted)]">{label}</span><div className="h-1 overflow-hidden rounded bg-[var(--surface-hover)]"><div className="h-full bg-[var(--fg)]" style={{ width: `${pct}%` }} /></div><span className="text-right font-mono text-[10px]">{count}</span></div>;
  })}</div>;
}

function SignalSummary({ icon: Icon, label, data, unit, caveat }: {
  icon: typeof Wind; label: string; data: Observation[]; unit: string; caveat?: string;
}) {
  const latest = data.slice().sort((a, b) => Date.parse(b.observed_at) - Date.parse(a.observed_at))[0];
  const isSnapshot = latest?.quality_status === "retrieval_timestamp";
  return <div className="rounded-xl border border-[var(--line)] p-4"><div className="flex items-center justify-between"><span className="text-xs text-[var(--muted)]">{label}</span><Icon className="size-4 text-[var(--muted)]" /></div><div className="mt-3 text-lg font-medium tracking-tight">{isSnapshot ? `${data.length} estaciones` : formatValue(latest?.value)}<span className="ml-1 text-[10px] font-normal text-[var(--muted)]">{isSnapshot ? "capturas" : unit}</span></div><p className="mt-1.5 text-[10px] text-[var(--muted)]">{caveat ?? (latest ? `Último dato ${formatDate(latest.observed_at)}` : "Sin observaciones disponibles")}</p></div>;
}

function cleanMunicipality(input: string) {
  return input
    .replace(/MedellÃ­n/gi, "Medellín")
    .replace(/Medellin/gi, "Medellín")
    .replace(/Itag&#252í/gi, "Itagüí")
    .replace(/^itagui$/i, "Itagüí")
    .trim();
}

function municipalityKey(input: string) {
  return cleanMunicipality(input).normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
}

\n