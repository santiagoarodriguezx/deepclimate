"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, CalendarClock, Clock3, Gauge, MapPin, Wind, type LucideIcon } from "lucide-react";
import { api, getAnomalies, getAutomaticForecasts, getLatest, getRuns, getSeries } from "@/lib/api";
import type { ForecastRun, ModelRun, Station } from "@/lib/types";
import { VARIABLES, variableMeta } from "@/lib/types";
import { formatDate, formatValue, isRecent } from "@/lib/utils";
import { PageHeading } from "@/components/dashboard/page-heading";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Select } from "@/components/ui/select";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { ForecastChart, TimeSeriesChart } from "@/components/charts/time-series-chart";

export function StationDetail({ stationId }: { stationId: string }) {
  const [variable, setVariable] = useState("PM25");
  const [days, setDays] = useState(7);
  const stationQuery = useQuery({ queryKey: ["station", stationId], queryFn: () => api<Station>(`/api/stations/${encodeURIComponent(stationId)}`) });
  const latestQuery = useQuery({ queryKey: ["latest", variable], queryFn: () => getLatest(variable), staleTime: 30_000 });
  const seriesQuery = useQuery({ queryKey: ["series", stationId, variable, days], queryFn: () => getSeries(stationId, variable, days), enabled: Boolean(stationId) });
  const anomalyQuery = useQuery({ queryKey: ["anomalies", stationId, variable], queryFn: () => getAnomalies(variable, stationId), enabled: variable === "PM25" });
  const runsQuery = useQuery({ queryKey: ["models", stationId, "PM25"], queryFn: () => getRuns(stationId, "PM25", 5), enabled: variable === "PM25" });
  const reading = latestQuery.data?.find((item) => item.station_id === stationId);
  const recent = reading && isRecent(reading.observed_at) && reading.quality_status === "good";
  const forecastQuery = useQuery({
    queryKey: ["automatic-forecasts", stationId, "PM25"],
    queryFn: () => getAutomaticForecasts(stationId, "PM25"),
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
  const station = stationQuery.data;
  const selectedSeries = seriesQuery.data?.series ?? [];
  const stationForecasts = forecastQuery.data?.forecasts ?? [];
  const forecast72 = stationForecasts.find((record) => record.horizon_hours === 72);
  const forecastIsFresh = forecast72?.status === "available" && forecast72.forecast.length >= 72 && isRecent(forecast72.generated_at, 2);

  if (stationQuery.isLoading) return <LoadingState label="Cargando ficha de estación" />;
  if (stationQuery.error) return <ErrorState message={stationQuery.error.message} retry={() => void stationQuery.refetch()} />;
  if (!station) return <EmptyState title="Estación no encontrada" detail="Revisa su código o vuelve al inventario oficial." />;

  return <>
    <Link href="/" className="mb-6 inline-flex items-center gap-2 text-xs text-[var(--muted)] hover:text-[var(--fg)]"><ArrowLeft className="size-3.5" /> Volver al panorama</Link>
    <PageHeading eyebrow={`${stationType(station.station_type)} · ${station.code ?? station.id}`} title={station.name} description={`${station.municipality ?? "Valle de Aburrá"}${station.neighborhood ? ` · ${station.neighborhood}` : ""}`} action={<Badge className="px-3 py-1.5"><span className={`size-1.5 rounded-full ${recent ? "bg-[var(--fg)]" : "border border-[var(--muted)]"}`} />{recent ? "Dato ≤ 3 h" : reading ? "Dato antiguo" : "Sin observación"}</Badge>} />

    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <Fact icon={Gauge} label={`Último ${variableMeta(variable).label}`} value={reading ? `${formatValue(reading.value)} ${reading.unit}` : "—"} detail={reading ? formatDate(reading.observed_at) : "Sin lectura publicada"} />
      <Fact icon={MapPin} label="Ubicación" value={station.latitude && station.longitude ? `${station.latitude.toFixed(4)}, ${station.longitude.toFixed(4)}` : "No publicada"} detail="Coordenadas del inventario oficial" />
      <Fact icon={Wind} label="Tipo de red" value={stationType(station.station_type)} detail={station.altitude ? `${formatValue(station.altitude)} m s. n. m.` : "Altitud sin dato"} />
      <Fact icon={Clock3} label="Calidad de origen" value={reading ? quality(reading.quality_status) : "Sin medición"} detail={reading?.quality_status === "retrieval_timestamp" ? "La hora es de captura, no del sensor" : reading?.quality_status === "unvalidated_unit" ? "Unidad sin validar por el proveedor" : "Procedencia consultada desde SIATA"} />
    </div>

    <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(280px,.7fr)]">
      <Card className="min-w-0"><CardHeader className="flex-wrap items-end"><div><p className="eyebrow">SERIE TEMPORAL</p><h3 className="mt-1.5 text-base font-medium">Historial de {variableMeta(variable).label}</h3></div><div className="flex gap-2"><label className="sr-only" htmlFor="detail-variable">Variable</label><Select id="detail-variable" value={variable} onChange={(e) => setVariable(e.target.value)}>{VARIABLES.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</Select><label className="sr-only" htmlFor="detail-period">Periodo</label><Select id="detail-period" value={days} onChange={(e) => setDays(Number(e.target.value))}><option value={1}>24 horas</option><option value={7}>7 días</option><option value={30}>30 días</option></Select></div></CardHeader><CardContent className="pt-4">
        {variable === "rain" || variable === "river_level" ? <EmptyState title="Esta serie no se grafica como temporal" detail="El feed consultado no publica una hora de observación por registro y, para nivel, la unidad no está validada. Se conservan las capturas con su procedencia." /> : <TimeSeriesChart points={selectedSeries} variable={variable} loading={seriesQuery.isLoading} error={seriesQuery.error?.message} label={station.name} />}
        <p className="mt-2 flex items-center gap-1.5 text-[10px] text-[var(--muted)]"><CalendarClock className="size-3" />{seriesQuery.data?.points_count ?? 0} puntos · ventana {days} días · valores observados, no interpolados</p>
      </CardContent></Card>
      <Card><CardHeader><div><p className="eyebrow">ANÁLISIS DETECTADO</p><h3 className="mt-1.5 text-base font-medium">Anomalías temporales</h3></div><Badge>PM2.5</Badge></CardHeader><CardContent className="pt-4">
        {anomalyQuery.isLoading ? <LoadingState /> : anomalyQuery.error ? <ErrorState message={anomalyQuery.error.message} /> : anomalyQuery.data?.status === "insufficient_data" ? <EmptyState title="Historial insuficiente" detail="El detector requiere al menos diez observaciones horarias en la ventana analizada." /> : anomalyQuery.data?.anomalies?.length ? <div className="space-y-3">{anomalyQuery.data.anomalies.slice(-5).reverse().map((item, index) => <div key={`${String(item.timestamp)}-${index}`} className="rounded-lg border border-[var(--line)] p-3"><div className="flex items-center justify-between gap-2"><span className="font-mono text-xs">{formatValue(Number(item.value))} µg/m³</span><Badge>{String(item.method ?? "anomalía")}</Badge></div><p className="mt-2 text-[10px] text-[var(--muted)]">{formatDate(String(item.timestamp))} · rango esperado {Array.isArray(item.expected_range) ? item.expected_range.join(" – ") : "no disponible"}</p></div>)}</div> : <EmptyState title="Sin anomalías detectadas" detail="Hay suficientes observaciones horarias para ejecutar el detector, pero no superaron su umbral estadístico." />}
      </CardContent></Card>
    </div>

    <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.5fr)_minmax(300px,.8fr)]">
      <Card><CardHeader><div><p className="eyebrow">PIPELINE AUTOMÁTICO · PM2.5</p><h3 className="mt-1.5 text-base font-medium">Pronóstico de la estación</h3></div><Badge>24 · 48 · 72 h</Badge></CardHeader><CardContent className="pt-4">
        {forecastQuery.isLoading ? <LoadingState label="Cargando pronósticos guardados" /> : forecastQuery.error ? <ErrorState message={forecastQuery.error.message} /> : <>
          <div className="grid grid-cols-3 gap-2">
            {([24, 48, 72] as const).map((hours) => <ForecastHorizon key={hours} hours={hours} record={stationForecasts.find((item) => item.horizon_hours === hours)} />)}
          </div>
          {forecastIsFresh && forecast72 ? <div className="mt-4"><ForecastChart points={forecast72.forecast} variable="PM25" /><p className="mt-2 text-[10px] text-[var(--muted)]">Modelo #{forecast72.model_run_id} · generado automáticamente {formatDate(forecast72.generated_at)} · los intervalos reflejan error de validación, no una garantía probabilística.</p></div> : <p className="mt-4 rounded-lg border border-dashed border-[var(--line)] px-3 py-3 text-xs leading-5 text-[var(--muted)]">El worker evalúa y publica pronósticos automáticamente cuando hay datos recientes y un modelo validado.</p>}
        </>}
      </CardContent></Card>
      <Card><CardHeader><div><p className="eyebrow">HISTORIAL DE ENTRENAMIENTO</p><h3 className="mt-1.5 text-base font-medium">Versiones registradas</h3></div></CardHeader><CardContent className="pt-4">
        {runsQuery.isLoading ? <LoadingState /> : runsQuery.error ? <ErrorState message={runsQuery.error.message} /> : runsQuery.data?.length ? <div className="divide-y divide-[var(--line)]">{runsQuery.data.map((run) => <RunRow key={run.id} run={run} />)}</div> : <p className="text-xs leading-5 text-[var(--muted)]">El ciclo automático sigue recopilando una serie horaria continua para validar y publicar un modelo.</p>}
      </CardContent></Card>
    </div>
  </>;
}

function Fact({ icon: Icon, label, value, detail }: { icon: LucideIcon; label: string; value: string; detail: string }) {
  return <Card><CardContent className="pt-4"><div className="flex items-center justify-between"><p className="eyebrow">{label}</p><Icon className="size-4 text-[var(--muted)]" /></div><p className="mt-4 truncate text-base font-medium">{value}</p><p className="mt-1.5 truncate text-[10px] text-[var(--muted)]">{detail}</p></CardContent></Card>;
}

function ForecastHorizon({ hours, record }: { hours: 24 | 48 | 72; record?: ForecastRun }) {
  const fresh = record?.status === "available" && record.forecast.length >= hours &&
    isRecent(record.generated_at, 2);
  const currentRecord = fresh ? record : undefined;
  const point = currentRecord?.forecast[hours - 1];
  const mae = currentRecord?.metrics.mae;
  return <div className="rounded-lg border border-[var(--line)] p-3"><p className="text-[10px] text-[var(--muted)]">{hours} horas</p><p className="mt-2 text-sm font-medium">{point ? `${formatValue(point.prediction)} µg/m³` : "En recopilación"}</p>{point && <p className="mt-1 text-[9px] text-[var(--muted)]">MAE {formatValue(mae, 2)} µg/m³</p>}</div>;
}

function RunRow({ run }: { run: ModelRun }) {
  return <div className="flex items-start justify-between gap-3 py-3"><div><p className="text-xs font-medium">{run.model_name} · #{run.id}</p><p className="mt-1 text-[10px] text-[var(--muted)]">{formatDate(run.trained_at)} · {run.training_points} observaciones</p></div><span className="shrink-0 text-right font-mono text-[10px]">MAE {formatValue(run.metrics.mae, 2)}<span className="mt-1 block text-[var(--muted)]">RMSE {formatValue(run.metrics.rmse, 2)}</span></span></div>;
}

function stationType(type: string) {
  return ({ air_quality: "Calidad del aire", meteorology: "Meteorología", pluviometric: "Pluviómetro", stream_level: "Nivel" } as Record<string, string>)[type] ?? type;
}
function quality(value: string) {
  return ({ good: "Validada por origen", retrieval_timestamp: "Hora de captura", unvalidated_unit: "Unidad sin validar", extreme_value: "Valor extremo" } as Record<string, string>)[value] ?? value;
}
