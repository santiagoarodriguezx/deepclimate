"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, BrainCircuit, ChartNoAxesCombined, CircleHelp, Database, Gauge, Radar, TriangleAlert, type LucideIcon } from "lucide-react";
import { getAnomalies, getClusters, getCorrelation, getForecast, getRuns, trainModel } from "@/lib/api";
import { useStations } from "@/lib/hooks/use-siata";
import type { Forecast } from "@/lib/types";
import { formatDate, formatValue } from "@/lib/utils";
import { PageHeading } from "@/components/dashboard/page-heading";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { ForecastChart } from "@/components/charts/time-series-chart";

export function ModelLab() {
  const stationsQuery = useStations();
  const stations = useMemo(() => stationsQuery.data?.filter((station) => station.station_type === "air_quality") ?? [], [stationsQuery.data]);
  const [stationId, setStationId] = useState("");
  const selectedStation = stationId || stations[0]?.id || "";
  const [horizon, setHorizon] = useState(24);
  const queryClient = useQueryClient();
  const runsQuery = useQuery({ queryKey: ["models", selectedStation, "PM25"], queryFn: () => getRuns(selectedStation, "PM25", 20), enabled: Boolean(selectedStation) });
  const train = useMutation({
    mutationFn: () => trainModel(selectedStation, "PM25"),
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ["models", selectedStation, "PM25"] }); await queryClient.invalidateQueries({ queryKey: ["forecast", selectedStation] }); },
  });
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const forecastMutation = useMutation({ mutationFn: () => getForecast(selectedStation, "PM25", horizon), onSuccess: setForecast });
  const anomalyQuery = useQuery({ queryKey: ["anomalies", "spatial", "PM25"], queryFn: () => getAnomalies("PM25"), enabled: false });
  const clusterQuery = useQuery({ queryKey: ["clusters"], queryFn: getClusters, enabled: false });
  const correlationQuery = useQuery({ queryKey: ["correlation", selectedStation, "rain", "PM25"], queryFn: () => getCorrelation(selectedStation, "rain", "PM25", 14), enabled: false });
  const runs = runsQuery.data ?? [];
  const latest = runs[0];

  return <>
    <PageHeading eyebrow="MODELADO · EVALUACIÓN · PRONÓSTICO" title="Laboratorio de Machine Learning" description="Modelos y métricas persistidos por el backend. El laboratorio separa el entrenamiento real, la evaluación temporal y el pronóstico disponible." action={<Badge><BrainCircuit className="size-3.5" /> Ridge autoregresivo</Badge>} />

    <div className="mb-4 grid gap-3 md:grid-cols-[minmax(220px,1fr)_repeat(3,minmax(130px,.55fr))]">
      <Card><CardContent className="flex h-full items-center justify-between gap-3 py-4"><div><p className="eyebrow">VARIABLE MODELADA</p><p className="mt-2 text-sm font-medium">PM2.5 · µg/m³</p></div><Gauge className="size-4 text-[var(--muted)]" /></CardContent></Card>
      <Metric label="Modelos guardados" value={runsQuery.isLoading ? "…" : String(runs.length)} />
      <Metric label="Último entrenamiento" value={latest ? formatDate(latest.trained_at) : "Sin modelo"} />
      <Metric label="MAE validación" value={latest ? formatValue(latest.metrics.mae, 2) : "—"} />
    </div>

    <div className="grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(310px,.8fr)]">
      <Card className="min-w-0">
        <CardHeader className="flex-wrap items-end"><div><p className="eyebrow">PRONÓSTICO PERSISTIDO</p><h3 className="mt-1.5 text-base font-medium">PM2.5 · próxima ventana</h3></div><div className="flex flex-wrap gap-2"><label className="sr-only" htmlFor="model-station">Estación</label><Select id="model-station" value={selectedStation} onChange={(e) => { setStationId(e.target.value); setForecast(null); }}><option value="">Elegir estación</option>{stations.map((station) => <option key={station.id} value={station.id}>{station.name}</option>)}</Select><label className="sr-only" htmlFor="forecast-horizon">Horizonte</label><Select id="forecast-horizon" value={horizon} onChange={(e) => setHorizon(Number(e.target.value))}><option value={24}>24 horas</option><option value={48}>48 horas</option><option value={72}>72 horas</option></Select></div></CardHeader>
        <CardContent className="pt-4">
          <div className="mb-4 flex flex-wrap gap-2"><Button onClick={() => train.mutate()} disabled={!selectedStation || train.isPending}><Database className="size-3.5" />{train.isPending ? "Entrenando y evaluando" : "Entrenar modelo"}</Button><Button variant="outline" onClick={() => forecastMutation.mutate()} disabled={!selectedStation || forecastMutation.isPending}><ChartNoAxesCombined className="size-3.5" />{forecastMutation.isPending ? "Generando" : "Consultar pronóstico"}</Button></div>
          {train.error && <p className="mb-3 text-xs text-[var(--muted)]" role="alert">No se pudo entrenar: {train.error.message}</p>}
          {train.data && <div className="mb-4 rounded-lg border border-[var(--line)] px-3 py-2 text-xs" role="status">{train.data.status === "trained" ? `Entrenamiento #${train.data.id} guardado con validación temporal.` : `No se entrenó: ${train.data.reason ?? train.data.status}.`}</div>}
          {forecastMutation.error && <p className="mb-3 text-xs text-[var(--muted)]" role="alert">{forecastMutation.error.message}</p>}
          {forecast ? forecast.status === "available" ? <><ForecastChart points={forecast.forecast} variable="PM25" /><p className="mt-3 text-[10px] leading-5 text-[var(--muted)]">Entrenamiento #{forecast.model_run_id} · generado {formatDate(forecast.generated_at)} · MAE {formatValue(forecast.metrics?.mae, 2)} · RMSE {formatValue(forecast.metrics?.rmse, 2)}. El rango se estima con el error de validación; no es una garantía probabilística calibrada.</p></> : <EmptyState title="Pronóstico no disponible" detail={forecast.reason ?? `Estado del modelo: ${forecast.status}. Entrena solo cuando el historial alcance las horas consecutivas requeridas.`} /> : <EmptyState title="Aún no has consultado un pronóstico" detail="La gráfica se carga únicamente tras solicitar un modelo entrenado; no hay curvas de demostración." />}
        </CardContent>
      </Card>

      <Card><CardHeader><div><p className="eyebrow">ENTRENAMIENTO VIGENTE</p><h3 className="mt-1.5 text-base font-medium">Ridge por hora</h3></div><Badge>{latest ? `Versión #${latest.id}` : "Sin entrenar"}</Badge></CardHeader><CardContent className="pt-4">
        <div className="space-y-3 text-xs"><ModelFact label="Estación" value={stations.find((item) => item.id === selectedStation)?.name ?? "Selecciona estación"} /><ModelFact label="Variable objetivo" value="PM2.5" /><ModelFact label="Puntos de entrenamiento" value={latest ? String(latest.training_points) : "—"} /><ModelFact label="Validación cronológica" value={latest ? `${latest.validation_points} puntos` : "Último tramo temporal"} /><ModelFact label="Entrenado" value={latest ? formatDate(latest.trained_at) : "—"} /><ModelFact label="MAE baseline persistencia" value={latest ? formatValue(latest.metrics.baseline_mae, 2) : "—"} /><ModelFact label="R²" value={latest ? formatValue(latest.metrics.r2, 3) : "—"} /></div>
        <div className="mt-5 rounded-xl border border-[var(--line)] p-3"><p className="text-[11px] font-medium">Reglas del experimento</p><p className="mt-2 text-[10px] leading-5 text-[var(--muted)]">Mínimo 72 horas consecutivas, corte temporal 80/20, comparación con persistencia y valores de calidad excluidos. Se guardan métricas y parámetros del modelo; el API no expone predicciones de validación ni importancia de variables.</p></div>
      </CardContent></Card>
    </div>

    <Card className="mt-4"><CardHeader><div><p className="eyebrow">EXPERIMENTOS REGISTRADOS</p><h3 className="mt-1.5 text-base font-medium">Historial del modelo por estación</h3></div><Badge>{runs.length} versiones</Badge></CardHeader><CardContent className="pt-4">
      {runsQuery.isLoading ? <LoadingState /> : runsQuery.error ? <ErrorState message={runsQuery.error.message} retry={() => void runsQuery.refetch()} /> : runs.length ? <div className="overflow-x-auto"><table className="data-table min-w-[650px]"><thead><tr><th>Versión</th><th>Entrenado</th><th>Observaciones</th><th>MAE</th><th>RMSE</th><th>Baseline MAE</th><th>R²</th></tr></thead><tbody>{runs.map((run) => <tr key={run.id}><td className="font-medium">Ridge · #{run.id}</td><td>{formatDate(run.trained_at)}</td><td>{run.training_points} / {run.validation_points}</td><td className="font-mono">{formatValue(run.metrics.mae, 2)}</td><td className="font-mono">{formatValue(run.metrics.rmse, 2)}</td><td className="font-mono">{formatValue(run.metrics.baseline_mae, 2)}</td><td className="font-mono">{formatValue(run.metrics.r2, 3)}</td></tr>)}</tbody></table></div> : <EmptyState title="No hay experimentos para esta estación" detail="El historial aparece luego de entrenar con datos horarios consecutivos válidos." />}
    </CardContent></Card>

    <div className="mt-4 grid gap-4 xl:grid-cols-3">
      <AnalysisPanel title="Anomalías espaciales" eyebrow="LECTURAS PM2.5 RECIENTES" icon={Radar} busy={anomalyQuery.isFetching} onRun={() => void anomalyQuery.refetch()} button="Analizar red" error={anomalyQuery.error?.message}>
        {anomalyQuery.data?.anomalies?.length ? anomalyQuery.data.anomalies.slice(0, 5).map((item, index) => <ModelFact key={`${String(item.station_id)}-${index}`} label={String(item.station_name ?? item.station_id)} value={`${formatValue(Number(item.value))} · vecinas ${formatValue(Number(item.neighbor_mean))}`} />) : anomalyQuery.data ? <p className="text-xs text-[var(--muted)]">No se detectaron anomalías en {anomalyQuery.data.stations_evaluated ?? 0} estaciones elegibles.</p> : <p className="text-xs text-[var(--muted)]">Compara datos PM2.5 con hora válida y estaciones vecinas geográficas.</p>}
      </AnalysisPanel>
      <AnalysisPanel title="Correlación exploratoria" eyebrow="ASOCIACIÓN, NO CAUSALIDAD" icon={Activity} busy={correlationQuery.isFetching} onRun={() => void correlationQuery.refetch()} button="Lluvia vs PM2.5" error={correlationQuery.error?.message}>
        {correlationQuery.data ? <p className="text-xs leading-5 text-[var(--muted)]">{correlationQuery.data.status === "available" ? `Pearson ${formatValue(Number(correlationQuery.data.pearson), 3)} · Spearman ${formatValue(Number(correlationQuery.data.spearman), 3)} · ${correlationQuery.data.aligned_points} horas coincidentes.` : `${String(correlationQuery.data.relationship ?? "Datos insuficientes")}. Las capturas de lluvia sin hora de observación quedan excluidas.`}</p> : <p className="text-xs text-[var(--muted)]">Consulta solo mediciones horarias coincidentes y válidas.</p>}
      </AnalysisPanel>
      <AnalysisPanel title="Perfiles de estación" eyebrow="AGRUPACIÓN EXPLORATORIA" icon={TriangleAlert} busy={clusterQuery.isFetching} onRun={() => void clusterQuery.refetch()} button="Agrupar PM2.5" error={clusterQuery.error?.message}>
        {clusterQuery.data?.clusters?.length ? <div className="space-y-2">{clusterQuery.data.clusters.map((cluster, index) => <ModelFact key={index} label={String(cluster.label ?? `Grupo ${index + 1}`)} value={`${String(cluster.station_count)} estaciones · media ${formatValue(Number(cluster.avg_pm25))} µg/m³`} />)}<p className="pt-2 text-[10px] text-[var(--muted)]">Una variable y una lectura por estación; resultado exploratorio, no interpreta fuentes ni causalidad.</p></div> : clusterQuery.data ? <p className="text-xs text-[var(--muted)]">No hay suficientes lecturas recientes para agrupar estaciones.</p> : <p className="text-xs text-[var(--muted)]">Agrupa la última lectura elegible por estación.</p>}
      </AnalysisPanel>
    </div>
    <div className="mt-4 flex gap-2 text-[10px] leading-5 text-[var(--muted)]"><CircleHelp className="mt-1 size-3.5 shrink-0" /><p>El backend ofrece actualmente un modelo entrenable para series horarias PM2.5. No hay modelos publicados de temperatura o lluvia ni métricas de clasificación disponibles; esta vista no rellena esos huecos con datos simulados.</p></div>
  </>;
}

function Metric({ label, value }: { label: string; value: string }) {
  return <Card><CardContent className="py-4"><p className="eyebrow">{label}</p><p className="mt-3 truncate text-sm font-medium">{value}</p></CardContent></Card>;
}
function ModelFact({ label, value }: { label: string; value: string }) {
  return <div className="flex items-center justify-between gap-3 border-b border-[var(--line)] pb-2 last:border-0 last:pb-0"><span className="text-[var(--muted)]">{label}</span><strong className="text-right font-medium">{value}</strong></div>;
}
function AnalysisPanel({ title, eyebrow, icon: Icon, busy, onRun, button, error, children }: {
  title: string; eyebrow: string; icon: LucideIcon; busy: boolean; onRun: () => void; button: string; error?: string; children: React.ReactNode;
}) {
  return <Card><CardHeader><div><p className="eyebrow">{eyebrow}</p><h3 className="mt-1.5 text-base font-medium">{title}</h3></div><Icon className="size-4 text-[var(--muted)]" /></CardHeader><CardContent className="pt-4"><Button size="sm" variant="outline" onClick={onRun} disabled={busy} className="mb-4"><Activity className="size-3.5" />{busy ? "Analizando" : button}</Button>{error && <p className="mb-3 text-[10px] text-[var(--muted)]" role="alert">{error}</p>}<div className="space-y-2">{children}</div></CardContent></Card>;
}
