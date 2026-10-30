export type Station = {
  id: string;
  source_id?: string | null;
  name: string;
  code?: string | null;
  municipality?: string | null;
  latitude: number | null;
  longitude: number | null;
  altitude?: number | null;
  station_type: string;
  active: boolean;
  neighborhood?: string | null;
  subbasin?: string | null;
};

export type Observation = {
  station_id: string;
  station_name?: string;
  station_code?: string;
  municipality?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  station_type?: string;
  variable_id: string;
  value: number;
  unit: string;
  observed_at: string;
  quality_status: string;
};

export type SeriesPoint = {
  timestamp: string;
  value: number;
  min?: number;
  max?: number;
  count?: number;
  quality_status?: string;
};

export type TimeSeries = {
  station_id: string;
  variable_id: string;
  days: number;
  aggregation: string;
  points_count: number;
  series: SeriesPoint[];
};

export type EnvironmentalEvent = {
  id?: number;
  event_type: string;
  severity: string;
  title: string;
  description: string;
  detected_at: string;
  station_ids: string[];
  evidence?: Record<string, unknown>;
};

export type Freshness = {
  variable_id: string;
  checked_at: string;
  total_stations: number;
  stations_online: number;
  stations_offline: number;
  average_lag_seconds: number | null;
  status_distribution: Record<string, number>;
  stations: Array<{ station_id: string; station_name: string; status: string; lag_seconds: number | null }>;
};

export type ModelRun = {
  id: number;
  model_name: string;
  station_id: string;
  variable_id: string;
  trained_at: string;
  training_points: number;
  validation_points: number;
  train_start: string;
  train_end: string;
  metrics: Record<string, number | null>;
};

export type Forecast = {
  status: string;
  reason?: string;
  station_id?: string;
  variable_id?: string;
  model?: string;
  model_run_id?: number;
  trained_at?: string;
  generated_at?: string;
  horizon_hours?: number;
  metrics?: Record<string, number | null>;
  forecast: Array<{ timestamp: string; prediction: number; lower: number; upper: number }>;
};

export type ForecastRun = {
  id: number;
  station_id: string;
  variable_id: string;
  horizon_hours: 24 | 48 | 72;
  model_run_id: number | null;
  generated_at: string;
  status: string;
  reason: string | null;
  metrics: Record<string, number | null>;
  forecast: Array<{ timestamp: string; prediction: number; lower: number; upper: number }>;
};

export type AgentAnswer = {
  query: string;
  answer: string;
  evidence: {
    stations: string[];
    variables: string[];
    ml_models_applied: string[];
    data_freshness: string;
    active_anomalies_count: number;
    tool_calls_executed: number;
    execution_time_ms: number;
  };
  ai_provider?: string;
  ai_model?: string | null;
};

export type Health = {
  status: string;
  platform: string;
  active_stations: number;
  data_freshness: { stations_online: number; average_lag_seconds: number | null };
};

export type DashboardSnapshot = {
  generated_at: string;
  refresh_after_seconds: number;
  stations: Station[];
  station_counts: Record<string, number>;
  observations: Record<string, Observation[]>;
  regional_forecasts: Record<string, RegionalForecast>;
  regional_history: Record<string, RegionalHistory>;
  network_history: Record<string, RegionalHistory>;
  model_forecasts: ForecastRun[];
  models: ModelRun[];
  events: EnvironmentalEvent[];
  freshness: Freshness;
  sources: SourceCatalog;
  pipeline_runs: SourceRun[];
};

export type SourceRun = {
  id: number;
  source_id: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  records_count: number;
  latency_ms: number | null;
  error_message: string | null;
  metadata: Record<string, unknown>;
};

export type Source = {
  id: string;
  name: string;
  category: string;
  url: string;
  variables: string[];
  temporal_resolution: string;
  spatial_resolution: string;
  update_frequency: string;
  latency: string;
  license: string;
  integration: string;
  status: string;
  limitation?: string;
  last_run: SourceRun | null;
  availability_scan?: SourceRun | null;
  records_stored: number;
  latest_valid_time: string | null;
};

export type SourceCatalog = {
  checked_at: string;
  sources: Source[];
  decision_provider: { provider: string; status: string; reason: string; fallback: string };
};

export type JevDecision = {
  id: number;
  action: string;
  subject: string;
  allowed: boolean;
  reason: string;
  engine: string;
  external_provider_status: string;
  created_at: string;
  metadata: Record<string, unknown>;
};

export type RegionalForecast = {
  status: string;
  reason?: string;
  source_id?: string;
  source_name?: string;
  variable_id?: string;
  unit?: string;
  latitude?: number;
  longitude?: number;
  spatial_resolution?: string;
  temporal_resolution?: string;
  generated_at?: string | null;
  forecast: Array<{ timestamp: string; value: number }>;
};

export type RegionalHistory = {
  status: string;
  reason?: string;
  source_id?: string;
  source_name?: string;
  variable_id?: string;
  unit?: string;
  latest_fetch_at?: string;
  series: Array<{ timestamp: string; value: number; count?: number }>;
};

export type GibsLayer = {
  id: string;
  title: string;
  default_time: string;
  time_ranges: string[];
  tile_matrix_set: string;
  max_zoom: number | null;
  formats: string[];
  legend_url?: string | null;
};

export type GibsLayers = {
  provider: string;
  checked_at: string;
  layers: GibsLayer[];
  interpretation: string;
};

export const VARIABLES = [
  { id: "PM25", label: "PM2.5", unit: "µg/m³", category: "air_quality" },
  { id: "PM10", label: "PM10", unit: "µg/m³", category: "air_quality" },
  { id: "O3", label: "Ozono", unit: "µg/m³", category: "air_quality" },
  { id: "temperature", label: "Temperatura", unit: "°C", category: "meteorology" },
  { id: "humidity", label: "Humedad", unit: "%", category: "meteorology" },
  { id: "rain", label: "Precipitación", unit: "mm · intervalo no publicado", category: "hydrology" },
  { id: "river_level", label: "Nivel", unit: "unidad no validada", category: "hydrology" },
] as const;

export const variableMeta = (id: string) => VARIABLES.find((item) => item.id === id) ?? {
  id, label: id, unit: "", category: "other",
};
