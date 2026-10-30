import { z } from "zod";
import type {
  AgentAnswer, EnvironmentalEvent, Forecast, Freshness, GibsLayers, Health, JevDecision,
  ModelRun, Observation, RegionalForecast, RegionalHistory, SourceCatalog, Station, TimeSeries,
} from "@/lib/types";

const stationSchema = z.object({
  id: z.string(), name: z.string(), station_type: z.string(), active: z.boolean(),
  latitude: z.number().nullable(), longitude: z.number().nullable(),
}).passthrough();

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path.startsWith("/") ? path : `/api/${path}`, {
    ...init,
    headers: { ...(init?.body ? { "Content-Type": "application/json" } : {}), ...init?.headers },
    cache: "no-store",
  });
  if (!response.ok) {
    let message = `Error ${response.status}`;
    const raw = await response.text();
    try {
      const body = raw ? JSON.parse(raw) : {};
      message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
      if (!raw) message = `Error ${response.status}`;
    } catch {
      message = raw || message;
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export async function getStations() {
  const raw = await api<unknown>("/api/stations");
  return z.array(stationSchema).parse(raw) as Station[];
}
export const getLatest = (variable: string) => api<Observation[]>(`/api/observations/latest?variable_id=${encodeURIComponent(variable)}`);
export const getSeries = (station: string, variable: string, days: number, aggregation = "hour") =>
  api<TimeSeries>(`/api/observations/timeseries?station_id=${encodeURIComponent(station)}&variable_id=${encodeURIComponent(variable)}&days=${days}&aggregation=${aggregation}`);
export const getFreshness = (variable: string) => api<Freshness>(`/api/freshness?variable_id=${encodeURIComponent(variable)}`);
export const getEvents = () => api<EnvironmentalEvent[]>("/api/events");
export const getHealth = () => api<Health>("/api/health");
export const getSources = () => api<SourceCatalog>("/api/sources");
export const getGibsLayers = () => api<GibsLayers>("/api/sources/gibs");
export const getJevDecisions = (limit = 30) => api<{
  engine: string; external_provider: SourceCatalog["decision_provider"]; decisions: JevDecision[];
}>(`/api/jev/decisions?limit=${limit}`);
export const getRegionalForecast = (variable: string, hours = 24) =>
  api<RegionalForecast>(`/api/regional/forecast?variable_id=${encodeURIComponent(variable)}&hours=${hours}`);
export const getRegionalHistory = (variable: string, days = 7) =>
  api<RegionalHistory>(`/api/regional/history?variable_id=${encodeURIComponent(variable)}&days=${days}`);
export const getRuns = (station: string, variable: string, limit = 20) =>
  api<ModelRun[]>(`/api/ml/models?station_id=${encodeURIComponent(station)}&variable_id=${encodeURIComponent(variable)}&limit=${limit}`);
export const getForecast = (station: string, variable: string, horizon: number) =>
  api<Forecast>(`/api/ml/forecast?station_id=${encodeURIComponent(station)}&variable_id=${encodeURIComponent(variable)}&horizon_hours=${horizon}`);
export const getAnomalies = (variable: string, station?: string) => api<{
  status?: string; stations_evaluated?: number; anomalies: Array<Record<string, unknown>>;
}>(`/api/ml/anomalies?variable_id=${encodeURIComponent(variable)}${station ? `&station_id=${encodeURIComponent(station)}` : "&spatial=true"}`);
export const getCorrelation = (station: string, a: string, b: string, days: number) =>
  api<Record<string, unknown>>(`/api/ml/correlations?station_id=${encodeURIComponent(station)}&var_a=${encodeURIComponent(a)}&var_b=${encodeURIComponent(b)}&days=${days}`);
export const getClusters = () => api<{ status: string; n_clusters: number; clusters: Array<Record<string, unknown>> }>("/api/ml/clusters");
export const askAgent = (query: string) => api<AgentAnswer>("/api/agent/query", {
  method: "POST", body: JSON.stringify({ query }),
});
export const syncNow = () => api<Record<string, unknown>>("/api/ingestion/sync", { method: "POST" });
export const ingestHistorical = () => api<Record<string, unknown>>("/api/ingestion/historical", { method: "POST" });
export const trainModel = (station: string, variable: string) => api<ModelRun & {
  status: string; reason?: string;
}>(`/api/ml/train?station_id=${encodeURIComponent(station)}&variable_id=${encodeURIComponent(variable)}`, { method: "POST" });
