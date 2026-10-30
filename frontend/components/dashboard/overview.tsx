"use client";

import { motion } from "framer-motion";
import { Activity, Droplets, Gauge, Thermometer, Wind, type LucideIcon } from "lucide-react";
import { useDashboard } from "@/lib/hooks/use-siata";
import type { DashboardSnapshot, ForecastRun, Observation, RegionalForecast, Source } from "@/lib/types";
import { formatDate, formatValue, humanLag, isRecent, parseUtcDate } from "@/lib/utils";
import { PageHeading } from "@/components/dashboard/page-heading";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { RegionalForecastChart } from "@/components/charts/time-series-chart";
import { MapLoader } from "@/components/stations/map-loader";

const INVALID_QUALITY = new Set(["unvalidated_unit", "retrieval_timestamp", "extreme_value", "doubtful", "unvalidated"]);
const HORIZONS = [24, 48, 72] as const;

export function Overview() {
  const query = useDashboard();
  if (query.isLoading) return <LoadingState label="Consolidando datos de estaciones y proveedores" />;
  if (query.error || !query.data) return <ErrorState message={query.error?.message ?? "No se pudo cargar el panorama consolidado."} />;

  const data = query.data;
  const current = (variable: string) => (data.observations[variable] ?? []).filter(
    (row) => isRecent(row.observed_at) && !INVALID_QUALITY.has(row.quality_status),
  );
  const pm25 = current("PM25");
  const pm10 = current("PM10");
  const ozone = current("O3");
  const nitrogenDioxide = current("NO2");
  const temperature = current("temperature");
  const humidity = current("humidity");
  const wind = current("wind_speed");
  const windDirection = current("wind_direction");
  const pressure = current("pressure");
  const average = (rows: Observation[]) => rows.length ? rows.reduce((sum, row) => sum + row.value, 0) / rows.length : null;
  const displayStations = data.stations.filter((station) => station.latitude != null && station.longitude != null);
  const regionalRain = data.regional_forecasts.rain_probability;
  const regionalTemperature = data.regional_forecasts.temperature;
  const regionalRainAmount = data.regional_forecasts.rain;
  const forecastSource = data.sources.sources.find((source) => source.id === "open_meteo");
  const forecastRows = data.model_forecasts.filter((row) => row.variable_id === "PM25");
  const forecastWorker = data.sources.sources.find((source) => source.id === "model_forecasts");
  const latestModel = data.models.find((model) => model.variable_id === "PM25");
  const sourceFailures = data.sources.sources.filter((source) => source.status === "error").length;

  return <motion.div initial={{ opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .25 }}>
    <PageHeading
      eyebrow="DEEPCLIMATE · VALLE DE ABURRÁ"
      title="Panorama ambiental unificado"
      description="Observaciones SIATA, productos regionales, modelos y estado de las fuentes en una sola lectura automática."
      action={<span className="text-xs text-[var(--muted)]">Actualizado {formatDate(data.generated_at)}</span>}
    />

    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-7" aria-label="Condiciones ambientales observadas">
      <Metric label="PM2.5" value={average(pm25)} unit="µg/m³" count={pm25.length} icon={Gauge} />
      <Metric label="PM10" value={average(pm10)} unit="µg/m³" count={pm10.length} icon={Activity} />
      <Metric label="Ozono" value={average(ozone)} unit="µg/m³" count={ozone.length} icon={Activity} />
      <Metric label="NO₂" value={average(nitrogenDioxide)} unit="µg/m³" count={nitrogenDioxide.length} icon={Activity} />
      <Metric label="Temperatura" value={average(temperature)} unit="°C" count={temperature.length} icon={Thermometer} />
      <Metric label="Humedad relativa" value={average(humidity)} unit="%" count={humidity.length} icon={Droplets} />
      <Metric label="Viento" value={average(wind)} unit="m/s" count={wind.length} icon={Wind} />
      <Metric label="Dirección del viento" value={circularMeanDegrees(windDirection)} unit="°" count={windDirection.length} icon={Wind} />
      <Metric label="Presión" value={average(pressure)} unit="hPa" count={pressure.length} icon={Gauge} />
    </section>

    <section className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.45fr)_minmax(340px,.9fr)]" aria-label="Pronóstico regional y de modelos locales">
      <Card className="min-w-0">
        <CardHeader>
          <div><p className="eyebrow">OPEN-METEO · CELDA REGIONAL</p><h3 className="mt-1.5 text-base font-medium">Probabilidad de precipitación · 72 h</h3></div>
          <Badge>{forecastSource?.last_run?.finished_at ? `Captura ${formatDate(forecastSource.last_run.finished_at)}` : "Pronóstico de modelo"}</Badge>
        </CardHeader>
        <CardContent className="pt-3">
          {regionalRain.status === "available" ? <RegionalForecastChart points={regionalRain.forecast} variable="rain_probability" unit="%" /> : <ForecastStatus reason={regionalRain.reason ?? "Esperando la siguiente captura automática de Open-Meteo."} />}
          <RegionalWindows anchorTime={data.generated_at} rain={regionalRain} temperature={regionalTemperature} rainAmount={regionalRainAmount} cloudCover={data.regional_forecasts.cloud_cover} />
          <p className="mt-3 text-[10px] leading-4 text-[var(--muted)]">Pronóstico externo sobre una celda de grilla. No equivale a medición de pluviómetro ni a pronóstico emitido por SIATA.</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><div><p className="eyebrow">MODELO LOCAL · PM2.5</p><h3 className="mt-1.5 text-base font-medium">Horizontes automáticos</h3></div><Badge>{latestModel ? `Ridge · versión #${latestModel.id}` : "En recopilación"}</Badge></CardHeader>
        <CardContent className="pt-4">
          <div className="grid grid-cols-3 gap-2">
            {HORIZONS.map((horizon) => <ModelHorizon key={horizon} horizon={horizon} records={forecastRows} />)}
          </div>
          {latestModel ? <div className="mt-4 space-y-2 border-t border-[var(--line)] pt-3 text-[10px] text-[var(--muted)]">
            <p>Último entrenamiento evaluado · {formatDate(latestModel.trained_at)}</p>
            <p>MAE {formatValue(latestModel.metrics.mae, 2)} µg/m³ · RMSE {formatValue(latestModel.metrics.rmse, 2)} µg/m³ · {latestModel.training_points} puntos de entrenamiento</p>
          </div> : <p className="mt-4 border-t border-[var(--line)] pt-3 text-[11px] leading-5 text-[var(--muted)]">
            El worker revisa automáticamente las estaciones. Publica un modelo cuando encuentra al menos 72 horas consecutivas y supera el baseline de persistencia.
          </p>}
          <p className="mt-3 text-[10px] text-[var(--muted)]">{forecastWorker?.last_run?.finished_at ? `Último ciclo automático ${formatDate(forecastWorker.last_run.finished_at)} · ${statusLabel(forecastWorker.last_run.status)}` : "El worker de pronósticos iniciará en el próximo ciclo del backend."}</p>
        </CardContent>
      </Card>
    </section>

    <section className="mt-4" aria-label="Mapa ambiental multicapas">
      <Card className="min-w-0 overflow-hidden">
        <CardHeader><div><p className="eyebrow">VALLE DE ABURRÁ · {displayStations.length} UBICACIONES</p><h3 className="mt-1.5 text-base font-medium">Mapa geográfico y capas meteorológicas</h3></div><Badge>Actualización automática · 60 s</Badge></CardHeader>
        <CardContent className="pt-4"><MapLoader stations={data.stations} readings={Object.values(data.observations).flat()} regionalForecasts={data.regional_forecasts} /></CardContent>
      </Card>
    </section>

    <section className="mt-4" aria-label="Cobertura y calidad por variable">
      <DataCoverage data={data} />
    </section>

    <section className="mt-4 grid gap-4 xl:grid-cols-3" aria-label="Tendencias ambientales e hidrología">
      <RegionalHistory data={data.regional_history} />
      <AirQualityTrend data={data.network_history} />
      <HydrologicalCaptures rain={data.observations.rain ?? []} levels={data.observations.river_level ?? []} />
    </section>

    <section className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]" aria-label="Estado del ecosistema de datos">
      <Card>
        <CardHeader><div><p className="eyebrow">INGESTA Y PROCEDENCIA</p><h3 className="mt-1.5 text-base font-medium">Fuentes y servicios</h3></div><Badge>{sourceFailures ? `${sourceFailures} con error` : "Estado consultado"}</Badge></CardHeader>
        <CardContent className="divide-y divide-[var(--line)] pt-2">
          {data.sources.sources.map((source) => <SourceRow key={source.id} source={source} />)}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><div><p className="eyebrow">CALIDAD Y EVENTOS</p><h3 className="mt-1.5 text-base font-medium">Señal de la red</h3></div><Badge>{freshnessLabel(data.freshness.stations_online, data.freshness.total_stations)}</Badge></CardHeader>
        <CardContent className="pt-4">
          <div className="grid grid-cols-2 gap-3 text-xs">
            <Fact label="Estaciones activas" value={countByType(data.station_counts)} />
            <Fact label="Rezago medio PM2.5" value={data.freshness.average_lag_seconds == null ? "Sin medición válida" : humanLag(data.freshness.average_lag_seconds)} />
          </div>
          <div className="my-4 border-t border-[var(--line)]" />
          {data.events.length ? <div className="space-y-3">{data.events.slice(0, 5).map((event) => <div key={`${event.event_type}:${event.station_ids.join(",")}`} className="border-l-2 border-[var(--fg)] pl-3"><div className="flex items-center justify-between gap-2"><p className="text-xs font-medium">{event.title}</p><span className="text-[9px] uppercase tracking-wider text-[var(--muted)]">{event.severity}</span></div><p className="mt-1.5 text-[10px] leading-4 text-[var(--muted)]">{event.description}</p><p className="mt-1.5 text-[9px] text-[var(--muted)]">{formatDate(event.detected_at)}</p></div>)}</div> : <ForecastStatus reason="Sin eventos ambientales activos registrados con observaciones verificables." />}
          <div className="mt-4 border-t border-[var(--line)] pt-3 text-[10px] leading-5 text-[var(--muted)]">
            Lluvia y nivel con hora de captura o unidad no validada se conservan con su procedencia y no se cuentan como una lectura actual comparable.
          </div>
        </CardContent>
      </Card>
    </section>
  </motion.div>;
}

function Metric({ label, value, unit, count, icon: Icon }: {
  label: string; value: number | null; unit: string; count: number; icon: LucideIcon;
}) {
  const available = value != null;
  if (!available) return null;
  return <Card><CardContent className="py-4">
    <div className="flex items-center justify-between"><p className="eyebrow">{label}</p><Icon className="size-4 text-[var(--muted)]" /></div>
    <p className="mt-4 truncate text-2xl font-medium tracking-tight">{formatValue(value)}<span className="ml-1.5 text-xs font-normal text-[var(--muted)]">{unit}</span></p>
    <p className="mt-2 text-[10px] text-[var(--muted)]">{count} estaciones · últimas 3 h</p>
  </CardContent></Card>;
}

function circularMeanDegrees(rows: Observation[]) {
  if (!rows.length) return null;
  const radians = rows.map((row) => row.value * Math.PI / 180);
  const x = radians.reduce((sum, value) => sum + Math.cos(value), 0) / radians.length;
  const y = radians.reduce((sum, value) => sum + Math.sin(value), 0) / radians.length;
  if (Math.hypot(x, y) < 1e-6) return null;
  return (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;
}

function ModelHorizon({ horizon, records }: { horizon: number; records: ForecastRun[] }) {
  const available = records.filter((record) => {
    const generated = parseUtcDate(record.generated_at)?.getTime();
    return record.horizon_hours === horizon && record.status === "available" &&
      record.forecast.length >= horizon && generated != null && isRecent(record.generated_at, 2);
  });
  const values = available.map((record) => record.forecast[horizon - 1]?.prediction).filter((value): value is number => typeof value === "number");
  const mean = values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
  const mae = available.map((record) => record.metrics.mae).filter((value): value is number => typeof value === "number");
  return <div className="rounded-lg border border-[var(--line)] p-3">
    <p className="text-[10px] text-[var(--muted)]">{horizon} horas</p>
    <p className={`mt-2 font-medium ${mean == null ? "text-[11px] text-[var(--muted)]" : "text-base"}`}>{mean == null ? "Recopilando" : `${formatValue(mean)} µg/m³`}</p>
    <p className="mt-1 text-[9px] text-[var(--muted)]">{values.length ? `Media · ${values.length} estaciones` : "Sin pronóstico vigente"}</p>
    {mae.length > 0 && <p className="mt-1 text-[9px] text-[var(--muted)]">MAE {formatValue(mae.reduce((sum, value) => sum + value, 0) / mae.length, 2)}</p>}
  </div>;
}

function RegionalWindows({ anchorTime, rain, temperature, rainAmount, cloudCover }: {
  anchorTime: string; rain: RegionalForecast; temperature: RegionalForecast; rainAmount: RegionalForecast; cloudCover?: RegionalForecast;
}) {
  const rainPoints = rain.forecast ?? [];
  const temperaturePoints = temperature.forecast ?? [];
  const amountPoints = rainAmount.forecast ?? [];
  const cloudPoints = cloudCover?.forecast ?? [];
  const now = parseUtcDate(anchorTime)?.getTime() ?? 0;
  const windows = [1, 3, 6, 24] as const;
  return <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
    {windows.map((hours) => {
      const end = now + hours * 3_600_000;
      const within = (point: { timestamp: string }) => {
        const time = parseUtcDate(point.timestamp)?.getTime();
        return time != null && time > now - 5 * 60_000 && time <= end;
      };
      const rainWindow = rainPoints.filter(within);
      const tempWindow = temperaturePoints.filter(within);
      const amountWindow = amountPoints.filter(within);
      const cloudWindow = cloudPoints.filter(within);
      const peak = rainWindow.length ? Math.max(...rainWindow.map((point) => point.value)) : null;
      const completeAmountWindow = amountWindow.length === hours;
      const total = completeAmountWindow ? amountWindow.reduce((sum, point) => sum + point.value, 0) : null;
      const low = tempWindow.length ? Math.min(...tempWindow.map((point) => point.value)) : null;
      const high = tempWindow.length ? Math.max(...tempWindow.map((point) => point.value)) : null;
      const cloudMean = hours === 24 && cloudWindow.length ? cloudWindow.reduce((sum, point) => sum + point.value, 0) / cloudWindow.length : null;
      return <div key={hours} className="rounded-lg bg-[var(--canvas)] px-3 py-2.5">
        <p className="text-[9px] text-[var(--muted)]">Acumulado · {hours} h</p>
        <p className="mt-1 text-sm font-medium">{total == null ? "Sin horas completas" : `${formatValue(total)} mm`}</p>
        <p className="mt-1 text-[9px] text-[var(--muted)]">{peak == null ? "Probabilidad sin dato" : `Prob. máx. ${formatValue(peak, 0)}%`}</p>
        {hours === 24 && <p className="mt-1 text-[9px] text-[var(--muted)]">{low == null || high == null ? "Temperatura sin dato" : `${formatValue(low)}–${formatValue(high)} °C`}</p>}
        {hours === 24 && cloudMean != null && <p className="mt-1 text-[9px] text-[var(--muted)]">Nubosidad media {formatValue(cloudMean, 0)}%</p>}
      </div>;
    })}
  </div>;
}

function SourceRow({ source }: { source: Source }) {
  const state = source.last_run?.finished_at ? `${statusLabel(source.last_run.status)} · ${formatDate(source.last_run.finished_at)}` : statusLabel(source.status);
  const detail = source.last_run?.error_message || source.limitation || (
    source.last_run?.records_count
      ? `${source.last_run.records_count.toLocaleString("es-CO")} registros en el último ciclo`
      : source.update_frequency
  );
  const execution = source.last_run?.metadata;
  const model = execution && typeof execution.model === "string" ? execution.model : null;
  const endpoint = execution && typeof execution.endpoint === "string" ? execution.endpoint : null;
  const domain = execution && typeof execution.domain === "string" ? execution.domain : null;
  return <div className="flex items-start justify-between gap-3 py-2.5">
    <div className="min-w-0"><p className="truncate text-[11px] font-medium">{source.name}</p><p className="mt-1 truncate text-[9px] text-[var(--muted)]">{detail}</p><p className="mt-1 truncate text-[9px] text-[var(--muted)]">{source.last_run?.latency_ms != null ? `Latencia medida: ${source.last_run.latency_ms.toLocaleString("es-CO")} ms` : `Frecuencia: ${source.update_frequency}`}{source.latest_valid_time ? ` · Válido ${formatDate(source.latest_valid_time)}` : ""}</p>{model && <p className="mt-1 truncate text-[9px] text-[var(--muted)]">Ejecución remota: {model}{domain ? ` · ${domain}` : ""}{endpoint ? ` · ${endpoint}` : ""}</p>}</div>
    <span className={`shrink-0 rounded-full border border-[var(--line)] px-2 py-1 text-[9px] ${source.status === "error" ? "text-[var(--fg)]" : "text-[var(--muted)]"}`}>{state}</span>
  </div>;
}

function ForecastStatus({ reason }: { reason: string }) {
  return <div className="flex min-h-[150px] items-center rounded-xl border border-dashed border-[var(--line)] px-5 py-4 text-xs leading-5 text-[var(--muted)]">{reason}</div>;
}

function RegionalHistory({ data }: { data: DashboardSnapshot["regional_history"] }) {
  const rows = Object.entries(data).flatMap(([variable, result]) => {
    const last = result.status === "available" ? result.series.at(-1) : undefined;
    return last ? [{ variable, unit: result.unit ?? "", timestamp: last.timestamp, value: last.value }] : [];
  });
  return <Card>
    <CardHeader><div><p className="eyebrow">NASA POWER · ANÁLISIS DIARIO</p><h3 className="mt-1.5 text-base font-medium">Contexto meteorológico regional</h3></div><Badge>{rows.length ? "Datos publicados" : "Esperando publicación"}</Badge></CardHeader>
    <CardContent className="pt-2">
      {rows.length ? <div className="divide-y divide-[var(--line)]">{rows.map((row) => <div key={row.variable} className="flex items-center justify-between gap-3 py-2.5"><div><p className="text-[11px] font-medium">{regionalLabel(row.variable)}</p><p className="mt-1 text-[9px] text-[var(--muted)]">Día válido {formatDate(row.timestamp, { day: "2-digit", month: "short", year: "numeric", timeZone: "America/Bogota" })}</p></div><p className="text-sm font-medium">{formatValue(row.value)} <span className="text-[10px] font-normal text-[var(--muted)]">{row.unit}</span></p></div>)}</div> : <ForecastStatus reason="NASA POWER todavía no publica una observación diaria dentro de la ventana disponible." />}
      {data.rain?.status === "available" && data.rain.series.length > 1 && <div className="mt-2"><RegionalForecastChart points={data.rain.series} variable="rain" unit={data.rain.unit ?? "mm"} /></div>}
      <p className="mt-3 border-t border-[var(--line)] pt-3 text-[10px] leading-4 text-[var(--muted)]">Estimación regional de grilla; conserva su fecha válida y resolución. No representa una estación SIATA. La irradiancia procede de análisis diarios, no de una lectura actual.</p>
    </CardContent>
  </Card>;
}

function AirQualityTrend({ data }: { data: DashboardSnapshot["network_history"] }) {
  const pm25 = data.PM25;
  const last = pm25?.status === "available" ? pm25.series.at(-1) : undefined;
  const pollutants = ["PM10", "O3", "NO2"].flatMap((id) => {
    const result = data[id];
    const point = result?.status === "available" ? result.series.at(-1) : undefined;
    return point ? [{ id, value: point.value, unit: result.unit ?? "", timestamp: point.timestamp }] : [];
  });
  return <Card>
    <CardHeader><div><p className="eyebrow">SIATA · ÚLTIMOS 7 DÍAS</p><h3 className="mt-1.5 text-base font-medium">Tendencia de calidad del aire</h3></div><Badge>{last ? `${last.count ?? 0} estaciones en última hora` : "Sin serie válida"}</Badge></CardHeader>
    <CardContent className="pt-2">
      {pm25?.status === "available" && pm25.series.length > 1 ? <RegionalForecastChart points={pm25.series} variable="PM25" unit={pm25.unit ?? "µg/m³"} /> : <ForecastStatus reason="La serie requiere varias horas de PM2.5 con calidad aceptada. No se sustituye con datos de otras estaciones o proveedores." />}
      {pollutants.length > 0 && <div className="grid grid-cols-3 gap-2 border-t border-[var(--line)] pt-3">{pollutants.map((item) => <div key={item.id}><p className="text-[9px] text-[var(--muted)]">{item.id === "O3" ? "Ozono" : item.id}</p><p className="mt-1 text-xs font-medium">{formatValue(item.value)} <span className="text-[9px] font-normal text-[var(--muted)]">{item.unit}</span></p><p className="mt-1 text-[8px] text-[var(--muted)]">{formatDate(item.timestamp)}</p></div>)}</div>}
      <p className="mt-3 text-[10px] leading-4 text-[var(--muted)]">Cada hora resume primero cada estación y luego calcula la mediana entre estaciones válidas. Cobertura dispareja; no es interpolación espacial.</p>
    </CardContent>
  </Card>;
}

function HydrologicalCaptures({ rain, levels }: { rain: Observation[]; levels: Observation[] }) {
  const rows = [...rain, ...levels].sort((a, b) => (parseUtcDate(b.observed_at)?.getTime() ?? 0) - (parseUtcDate(a.observed_at)?.getTime() ?? 0)).slice(0, 8);
  return <Card>
    <CardHeader><div><p className="eyebrow">SIATA · LLUVIA Y NIVEL</p><h3 className="mt-1.5 text-base font-medium">Capturas hidrológicas</h3></div><Badge>{rows.length ? `${rows.length} registros` : "Esperando registros"}</Badge></CardHeader>
    <CardContent className="pt-2">
      {rows.length ? <div className="divide-y divide-[var(--line)]">{rows.map((row) => <div key={`${row.station_id}:${row.variable_id}`} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 py-2.5"><div className="min-w-0"><p className="truncate text-[11px] font-medium">{row.station_name ?? row.station_id}</p><p className="mt-1 truncate text-[9px] text-[var(--muted)]">{row.variable_id === "rain" ? "Precipitación" : "Nivel hidrológico"} · {qualityLabel(row.quality_status)} · {formatDate(row.observed_at)}</p></div><p className="text-right text-xs font-medium">{formatValue(row.value)} <span className="text-[9px] font-normal text-[var(--muted)]">{row.unit}</span></p></div>)}</div> : <ForecastStatus reason="No hay capturas hidrológicas almacenadas en el último registro publicado por SIATA." />}
      <p className="mt-3 border-t border-[var(--line)] pt-3 text-[10px] leading-4 text-[var(--muted)]">La etiqueta indica si la fuente publica hora de sensor y unidad validadas; las capturas sin esos datos no se cuentan como condiciones actuales.</p>
    </CardContent>
  </Card>;
}

function regionalLabel(variable: string) {
  return ({ rain: "Precipitación diaria", temperature: "Temperatura", humidity: "Humedad relativa", wind_speed: "Velocidad del viento", solar_irradiance: "Radiación solar" } as Record<string, string>)[variable] ?? variable;
}

const COVERAGE_VARIABLES = [
  ["PM25", "PM2.5", ["air_quality"]], ["PM10", "PM10", ["air_quality"]], ["O3", "Ozono", ["air_quality"]], ["NO2", "NO₂", ["air_quality"]],
  ["temperature", "Temperatura", ["meteorology"]], ["humidity", "Humedad", ["meteorology"]], ["wind_speed", "Viento", ["meteorology"]],
  ["wind_direction", "Dirección del viento", ["meteorology"]], ["pressure", "Presión", ["meteorology"]],
  ["rain", "Precipitación SIATA", ["pluviometric"]], ["river_level", "Nivel hidrológico", ["stream_level"]],
] as const;

function DataCoverage({ data }: { data: DashboardSnapshot }) {
  const now = parseUtcDate(data.generated_at)?.getTime() ?? 0;
  const rows = COVERAGE_VARIABLES.map(([id, label, stationTypes]) => {
    const observations = data.observations[id] ?? [];
    const compatible = data.stations.filter((station) => stationTypes.some((stationType) => stationType === station.station_type));
    const valid = observations.filter((row) => isRecent(row.observed_at) && !INVALID_QUALITY.has(row.quality_status));
    const freshIds = new Set(valid.map((row) => row.station_id));
    const latest = observations.filter((row) => !INVALID_QUALITY.has(row.quality_status))
      .sort((a, b) => (parseUtcDate(b.observed_at)?.getTime() ?? 0) - (parseUtcDate(a.observed_at)?.getTime() ?? 0))[0];
    const timestamp = latest ? parseUtcDate(latest.observed_at)?.getTime() : null;
    const lag = timestamp == null ? null : Math.max(0, (now - timestamp) / 1000);
    const invalid = observations.filter((row) => INVALID_QUALITY.has(row.quality_status)).length;
    const stale = observations.filter((row) => !INVALID_QUALITY.has(row.quality_status) && !isRecent(row.observed_at)).length;
    return { id, label, total: compatible.length, count: freshIds.size, invalid, stale, latest, lag };
  }).filter((row) => row.total > 0 || data.observations[row.id]?.length);

  return <Card>
    <CardHeader><div><p className="eyebrow">CALIDAD DE LA RED · SIATA</p><h3 className="mt-1.5 text-base font-medium">Frescura y cobertura por variable</h3></div><Badge>Ventana reciente · 3 h</Badge></CardHeader>
    <CardContent className="overflow-x-auto pt-2">
      {rows.length ? <table className="data-table min-w-[690px]"><thead><tr><th>Variable</th><th>Cobertura reciente</th><th>Última válida</th><th>Rezago</th><th>Calidad del feed</th></tr></thead><tbody>
        {rows.map((row) => <tr key={row.id}><td className="font-medium">{row.label}</td><td>{row.count} / {row.total || "—"} estaciones</td><td>{row.latest ? formatDate(row.latest.observed_at) : "Sin lectura validada"}</td><td>{row.lag == null ? "Sin medición válida" : humanLag(row.lag)}</td><td className="text-[var(--muted)]">{row.invalid ? `${row.invalid} no validada` : "Sin registros inválidos recientes"}{row.stale ? ` · ${row.stale} fuera de ventana` : ""}</td></tr>)}
      </tbody></table> : <ForecastStatus reason="La red aún no tiene inventario de sensores disponible para evaluar cobertura." />}
      <p className="mt-3 text-[10px] leading-4 text-[var(--muted)]">Cobertura cuenta estaciones con observación reciente y calidad aceptada, sobre el inventario SIATA compatible. Una captura almacenada con unidad u hora sin validar no cuenta como condición actual.</p>
    </CardContent>
  </Card>;
}

function qualityLabel(status: string) {
  return ({ good: "Validada", retrieval_timestamp: "Hora de captura", unvalidated_unit: "Unidad sin validar", extreme_value: "Valor extremo" } as Record<string, string>)[status] ?? status;
}

function Fact({ label, value }: { label: string; value: string }) {
  return <div className="rounded-lg border border-[var(--line)] px-3 py-2.5"><p className="text-[9px] text-[var(--muted)]">{label}</p><p className="mt-1.5 text-xs font-medium">{value}</p></div>;
}

function statusLabel(status: string) {
  return ({
    success: "Operativa", partial: "Parcial", failed: "Error", error: "Error", empty: "Sin salida disponible",
    running: "En curso", scheduled: "Programada", available: "Disponible", configured: "Credencial configurada",
    not_configured: "Sin credencial", not_integrated: "No integrada", visualization_only: "Visualización",
  } as Record<string, string>)[status] ?? status;
}

function freshnessLabel(online: number, total: number) {
  return total ? `${online} / ${total} recientes` : "Esperando inventario";
}

function countByType(counts: Record<string, number>) {
  const rows = Object.entries(counts).filter(([, count]) => count > 0).map(([type, count]) => `${count} ${stationType(type)}`);
  return rows.length ? rows.join(" · ") : "Esperando inventario";
}

function stationType(type: string) {
  return ({ air_quality: "aire", meteorology: "meteorología", pluviometric: "pluviómetro", stream_level: "nivel" } as Record<string, string>)[type] ?? type;
}
