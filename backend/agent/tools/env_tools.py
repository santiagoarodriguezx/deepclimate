"""
Jev Agent Environmental Tools.
Provides structured, validated tools for the Jev reasoning agent.
Directly executes SQL queries and ML algorithms without overwhelming the context with raw data.
"""

import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from backend.database.repository import EnvironmentalRepository
from backend.database.models import RegionalDatum
from backend.monitoring.freshness import FreshnessMonitor, is_recent_observation
from backend.agent.decision import JevDecisionEngine, persist_decision
from backend.ml.anomalies.temporal import TemporalAnomalyDetector
from backend.ml.anomalies.spatial import SpatialAnomalyDetector
from backend.ml.forecasting.predictor import EnvironmentalForecaster
from backend.ml.correlations.engine import CorrelationEngine
from backend.ml.clustering.station_clusters import StationClusterEngine


class EnvironmentalToolKit:
    def __init__(self, db: Session):
        self.db = db
        self.repo = EnvironmentalRepository(db)
        self.freshness = FreshnessMonitor(db)
        self.temporal_detector = TemporalAnomalyDetector()
        self.spatial_detector = SpatialAnomalyDetector()
        self.forecaster = EnvironmentalForecaster()
        self.correlation_engine = CorrelationEngine()
        self.clustering_engine = StationClusterEngine()

    def get_stations(
        self,
        municipality: Optional[str] = None,
        station_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List active SIATA monitoring stations filtered by municipality or station type."""
        stations = self.repo.get_stations(municipality=municipality, station_type=station_type)
        return [st.to_dict() for st in stations]

    def get_station(self, station_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve details and location for a specific station by its ID or code."""
        st = self.repo.get_station_by_id_or_code(station_id)
        return st.to_dict() if st else None

    def get_latest_observation(
        self,
        station_id: str,
        variable_id: str = "PM25"
    ) -> Dict[str, Any]:
        """
        Retrieves the latest observation for a station and variable,
        including data freshness lag and sensor status.
        """
        st = self.repo.get_station_by_id_or_code(station_id)
        if not st:
            return {"error": f"Station '{station_id}' not found."}

        obs = self.repo.get_latest_observation(st.id, variable_id)
        freshness_info = self.freshness.check_station_freshness(st.id, variable_id)

        if not obs:
            return {
                "station": st.name,
                "station_code": st.code,
                "variable": variable_id,
                "value": None,
                "freshness": freshness_info
            }

        return {
            "station": st.name,
            "station_code": st.code,
            "municipality": st.municipality,
            "variable": variable_id,
            "value": obs.value,
            "unit": obs.unit,
            "observed_at": obs.observed_at.isoformat(),
            "quality": obs.quality_status,
            "freshness": {
                "lag_seconds": freshness_info["lag_seconds"],
                "status": freshness_info["status"],
                "human_lag": freshness_info["human_lag"]
            }
        }

    def get_latest_by_variable(self, variable_id: str = "PM25") -> List[Dict[str, Any]]:
        """Returns the most recent observations for all active stations measuring a specific variable."""
        return self.repo.get_latest_by_variable(variable_id)

    def get_time_series(
        self,
        station_id: str,
        variable_id: str = "PM25",
        days: int = 7,
        aggregation: str = "hour"
    ) -> Dict[str, Any]:
        """
        Retrieves aggregated historical time series for charts and analysis.
        Aggregation: 'hour' or 'day' to avoid sending excessive raw records.
        """
        now = datetime.datetime.utcnow()
        start = now - datetime.timedelta(days=days)
        points = self.repo.get_time_series(station_id, variable_id, start, now, aggregation=aggregation)
        return {
            "station_id": station_id,
            "variable_id": variable_id,
            "days": days,
            "aggregation": aggregation,
            "points_count": len(points),
            "series": points
        }

    def compare_periods(
        self,
        station_id: str,
        variable_id: str = "PM25",
        days_window: int = 7
    ) -> Dict[str, Any]:
        """Compares the last N days against the preceding N days for trend evaluation."""
        now = datetime.datetime.utcnow()
        p2_end = now
        p2_start = now - datetime.timedelta(days=days_window)
        p1_end = p2_start
        p1_start = p2_start - datetime.timedelta(days=days_window)

        return self.repo.compare_periods(station_id, variable_id, p1_start, p1_end, p2_start, p2_end)

    def detect_anomalies(
        self,
        station_id: str,
        variable_id: str = "PM25",
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Executes Temporal Anomaly Detection (Isolation Forest, Robust MAD, Rolling Z-score)
        on a station's time series.
        """
        now = datetime.datetime.utcnow()
        start = now - datetime.timedelta(days=days)
        series = self.repo.get_time_series(station_id, variable_id, start, now, aggregation="hour")
        anomalies = self.temporal_detector.detect_anomalies(series, method="combined")
        return {
            "station_id": station_id,
            "variable_id": variable_id,
            "period_days": days,
            "points_evaluated": len(series),
            "status": "available" if len(series) >= 10 else "insufficient_data",
            "anomalies_detected_count": len(anomalies),
            "anomalies": anomalies[-10:]  # return most recent 10
        }

    def detect_spatial_anomalies(self, variable_id: str = "PM25") -> Dict[str, Any]:
        """
        Compares all stations currently measuring variable_id against their spatial neighbors
        to find geographic anomalies.
        """
        observations = [
            row for row in self.repo.get_latest_by_variable(variable_id)
            if is_recent_observation(row.get("observed_at"))
            and row.get("quality_status") not in {"unvalidated_unit", "retrieval_timestamp"}
        ]
        anomalies = self.spatial_detector.detect_spatial_anomalies(observations)
        return {
            "variable_id": variable_id,
            "stations_evaluated": len(observations),
            "status": "available" if len(observations) >= 3 else "insufficient_data",
            "spatial_anomalies_count": len(anomalies),
            "anomalies": anomalies
        }

    def forecast_variable(
        self,
        station_id: str,
        variable_id: str = "PM25",
        horizon_hours: int = 24
    ) -> Dict[str, Any]:
        """Uses the latest persisted, temporally evaluated model; never invents a fallback forecast."""
        now = datetime.datetime.utcnow()
        station = self.repo.get_station_by_id_or_code(station_id)
        if not station:
            return {"status": "station_not_found", "station_id": station_id, "forecast": []}
        runs = self.repo.get_model_runs(station.id, variable_id, limit=1)
        if not runs:
            return {"status": "model_not_trained", "station_id": station.id, "variable_id": variable_id, "forecast": []}
        start = now - datetime.timedelta(days=60)
        series = self.repo.get_time_series(
            station.id, variable_id, start, now, aggregation="hour",
            exclude_quality_status=["unvalidated_unit", "retrieval_timestamp"],
        )
        fc = self.forecaster.forecast(series, runs[0].to_dict(include_artifact=True)["artifact"], horizon_hours)
        latest_timestamp = series[-1]["timestamp"] if series else None
        if fc.get("status") == "available" and not is_recent_observation(latest_timestamp):
            fc = {
                "status": "stale_data",
                "reason": "La última observación es demasiado antigua para generar un pronóstico actual.",
                "forecast": [],
            }
        fc["station_id"] = station.id
        fc["variable_id"] = variable_id
        fc["model_run_id"] = runs[0].id
        fc["model"] = runs[0].model_name
        fc["trained_at"] = runs[0].trained_at.isoformat()
        fc["metrics"] = runs[0].to_dict()["metrics"]
        fc["training_points"] = runs[0].training_points
        fc["generated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        return fc

    def train_forecast_model(self, station_id: str, variable_id: str = "PM25") -> Dict[str, Any]:
        station = self.repo.get_station_by_id_or_code(station_id)
        if not station:
            return {"status": "station_not_found", "station_id": station_id}
        end = datetime.datetime.utcnow()
        series = self.repo.get_time_series(
            station.id, variable_id, end - datetime.timedelta(days=60), end,
            aggregation="hour", exclude_quality_status=["unvalidated_unit", "retrieval_timestamp"],
        )
        result = self.forecaster.train(series)
        if result["status"] != "trained":
            decision = JevDecisionEngine().decide_model_candidate(
                f"{station.id}:{variable_id}", dataset_ready=False, mae=None, baseline_mae=None,
            )
            persist_decision(self.db, decision)
            self.db.commit()
            result.update({"station_id": station.id, "variable_id": variable_id})
            return result

        runs = self.repo.get_model_runs(station.id, variable_id, limit=100)
        champion_errors = [
            metrics["mae"]
            for run in runs
            if isinstance((metrics := run.to_dict().get("metrics")), dict)
            and isinstance(metrics.get("mae"), (int, float))
        ]
        champion_mae = min(champion_errors) if champion_errors else None
        metrics = result["metrics"]
        decision = JevDecisionEngine().decide_model_candidate(
            f"{station.id}:{variable_id}",
            dataset_ready=True,
            mae=metrics.get("mae"),
            baseline_mae=metrics.get("baseline_mae"),
            champion_mae=champion_mae,
        )
        persist_decision(self.db, decision)
        if not decision.allowed:
            self.db.commit()
            return {
                "status": "candidate_rejected",
                "reason": decision.reason,
                "station_id": station.id,
                "variable_id": variable_id,
                "candidate_metrics": metrics,
                "champion_mae": champion_mae,
            }
        run = self.repo.record_model_run({
            "model_name": result["model"],
            "station_id": station.id,
            "variable_id": variable_id,
            "trained_at": datetime.datetime.fromisoformat(result["trained_at"]),
            "training_points": result["training_points"],
            "validation_points": result["validation_points"],
            "train_start": datetime.datetime.fromisoformat(result["train_start"]),
            "train_end": datetime.datetime.fromisoformat(result["train_end"]),
            "metrics": result["metrics"],
            "artifact": result["artifact"],
        })
        return {**run.to_dict(), "status": "trained"}

    def find_correlations(
        self,
        station_id: str,
        var_a: str = "rain",
        var_b: str = "PM25",
        days: int = 14
    ) -> Dict[str, Any]:
        """Finds Pearson and Spearman correlation between two variables (e.g. rain vs PM2.5)."""
        now = datetime.datetime.utcnow()
        start = now - datetime.timedelta(days=days)
        unreliable = ["unvalidated_unit", "retrieval_timestamp"]
        s_a = self.repo.get_time_series(
            station_id, var_a, start, now, aggregation="hour", exclude_quality_status=unreliable
        )
        s_b = self.repo.get_time_series(
            station_id, var_b, start, now, aggregation="hour", exclude_quality_status=unreliable
        )
        return self.correlation_engine.calculate_correlation(s_a, s_b, name_a=var_a, name_b=var_b)

    def get_data_freshness(self, variable_id: str = "PM25") -> Dict[str, Any]:
        """Returns the valley-wide freshness report."""
        return self.freshness.get_valley_freshness_report(variable_id)

    def get_active_events(self) -> List[Dict[str, Any]]:
        """Returns current verified environmental events and alerts detected by the engine."""
        events = self.repo.get_active_events()
        return [e.to_dict() for e in events]

    def get_regional_forecast(self, variable_id: str = "rain_probability", hours: int = 24) -> Dict[str, Any]:
        """Return stored Open-Meteo forecasts with their model-vintage provenance."""
        hours = min(72, max(1, int(hours)))
        now = datetime.datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        rows = self.db.query(RegionalDatum).filter(
            RegionalDatum.source_id == "open_meteo",
            RegionalDatum.record_type == "forecast",
            RegionalDatum.variable_id == variable_id,
            RegionalDatum.valid_at >= now,
            RegionalDatum.valid_at <= now + datetime.timedelta(hours=hours),
        ).order_by(RegionalDatum.valid_at, RegionalDatum.issued_at.desc()).limit(hours * 24).all()
        latest_by_time = {}
        for row in rows:
            latest_by_time.setdefault(row.valid_at, row)
        points = [latest_by_time[stamp] for stamp in sorted(latest_by_time)]
        if not points:
            return {
                "status": "unavailable",
                "reason": "Open-Meteo aún no tiene pronósticos guardados para esta variable.",
                "source_id": "open_meteo",
                "variable_id": variable_id,
                "forecast": [],
            }
        first = points[0]
        return {
            "status": "available",
            "source_id": "open_meteo",
            "source_name": "Open-Meteo Best Match",
            "variable_id": variable_id,
            "unit": first.unit,
            "latitude": first.latitude,
            "longitude": first.longitude,
            "spatial_resolution": first.spatial_resolution,
            "temporal_resolution": first.temporal_resolution,
            "generated_at": max((row.issued_at for row in points if row.issued_at), default=None).isoformat()
            if any(row.issued_at for row in points) else None,
            "forecast": [{"timestamp": row.valid_at.isoformat(), "value": row.value} for row in points],
        }

    def get_regional_history(self, variable_id: str = "rain", days: int = 7) -> Dict[str, Any]:
        """Return NASA POWER's daily regional analysis without presenting it as a station series."""
        days = min(90, max(1, int(days)))
        now = datetime.datetime.utcnow()
        rows = self.db.query(RegionalDatum).filter(
            RegionalDatum.source_id == "nasa_power",
            RegionalDatum.record_type == "regional_analysis",
            RegionalDatum.variable_id == variable_id,
            RegionalDatum.valid_at >= now - datetime.timedelta(days=days),
            RegionalDatum.valid_at <= now,
        ).order_by(RegionalDatum.valid_at).all()
        if not rows:
            return {
                "status": "unavailable",
                "reason": "NASA POWER aún no tiene valores regionales guardados para esta variable.",
                "source_id": "nasa_power",
                "variable_id": variable_id,
                "series": [],
            }
        return {
            "status": "available",
            "source_id": "nasa_power",
            "source_name": "NASA POWER · análisis meteorológico regional",
            "variable_id": variable_id,
            "unit": rows[0].unit,
            "spatial_resolution": rows[0].spatial_resolution,
            "temporal_resolution": rows[0].temporal_resolution,
            "latest_fetch_at": max(row.fetched_at for row in rows).isoformat(),
            "series": [{"timestamp": row.valid_at.isoformat(), "value": row.value} for row in rows],
        }
