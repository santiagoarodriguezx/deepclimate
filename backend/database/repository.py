"""
Database repository providing high-performance, validated query interfaces.
Used by Ingestion, ML models, API endpoints, and Jev agent tools.
"""

import datetime
import math
from typing import List, Dict, Any, Optional
from sqlalchemy import func, and_, desc
from sqlalchemy.orm import Session
from backend.database.models import Station, Variable, Observation, EnvironmentalEvent, IngestionRun, ModelRun


class EnvironmentalRepository:
    def __init__(self, db: Session):
        self.db = db

    def upsert_station(self, station_data: Dict[str, Any]) -> Station:
        """Inserts or updates a station in the canonical inventory."""
        st_id = str(station_data.get("id") or station_data.get("code"))
        station = self.db.query(Station).filter(Station.id == st_id).first()
        if not station:
            station = Station(id=st_id)
            self.db.add(station)

        station.source_id = str(station_data.get("source_id", ""))
        station.name = str(station_data.get("name", st_id))
        station.code = str(station_data.get("code", st_id))
        station.municipality = station_data.get("municipality") or "Medellín"
        station.latitude = float(station_data.get("latitude", 0.0))
        station.longitude = float(station_data.get("longitude", 0.0))
        station.altitude = float(station_data["altitude"]) if station_data.get("altitude") is not None else None
        station.station_type = station_data.get("station_type", "air_quality")
        station.active = station_data.get("active", True)
        station.subbasin = station_data.get("subbasin")
        station.neighborhood = station_data.get("neighborhood")
        station.metadata_json = station_data.get("metadata_json")

        self.db.flush()
        return station

    def bulk_insert_observations(self, observations: List[Dict[str, Any]]) -> int:
        """
        Inserts observations, avoiding duplicates by checking (station_id, variable_id, observed_at).
        Returns number of newly inserted records.
        """
        if not observations:
            return 0

        inserted_count = 0
        now = datetime.datetime.utcnow()

        for obs in observations:
            try:
                obs_at = obs["observed_at"]
                if isinstance(obs_at, str):
                    obs_at = datetime.datetime.fromisoformat(obs_at.replace("Z", "+00:00"))
                if obs_at.tzinfo is not None:
                    obs_at = obs_at.astimezone(datetime.timezone.utc).replace(tzinfo=None)
                value = float(obs["value"])
                if not math.isfinite(value):
                    continue
            except (KeyError, TypeError, ValueError):
                continue

            # Check for existing record
            existing = self.db.query(Observation.id).filter(
                Observation.station_id == obs["station_id"],
                Observation.variable_id == obs["variable_id"],
                Observation.observed_at == obs_at
            ).first()

            if not existing:
                new_obs = Observation(
                    station_id=obs["station_id"],
                    variable_id=obs["variable_id"],
                    observed_at=obs_at,
                    value=value,
                    raw_value=str(obs.get("raw_value", obs["value"])),
                    unit=obs.get("unit", ""),
                    quality_code=str(obs.get("quality_code", "")),
                    quality_status=obs.get("quality_status", "good"),
                    source=obs.get("source", "siata_realtime"),
                    ingested_at=now
                )
                self.db.add(new_obs)
                inserted_count += 1

        self.db.commit()
        return inserted_count

    def get_stations(
        self,
        municipality: Optional[str] = None,
        station_type: Optional[str] = None,
        active_only: bool = True
    ) -> List[Station]:
        """Retrieves stations filtered by municipality and/or type."""
        query = self.db.query(Station)
        if active_only:
            query = query.filter(Station.active == True)
        if municipality:
            # Case insensitive match
            query = query.filter(func.lower(Station.municipality).contains(municipality.lower()))
        if station_type:
            query = query.filter(Station.station_type == station_type)
        return query.all()

    def get_station_by_id_or_code(self, identifier: str) -> Optional[Station]:
        """Finds a station by id, code, or source_id."""
        clean_id = identifier.strip().upper()
        return self.db.query(Station).filter(
            (func.upper(Station.id) == clean_id) |
            (func.upper(Station.code) == clean_id) |
            (Station.source_id == identifier.strip())
        ).first()

    def get_latest_observation(self, station_id: str, variable_id: str) -> Optional[Observation]:
        """Returns the most recent observation for a given station and variable."""
        # Normalize station identifier
        st = self.get_station_by_id_or_code(station_id)
        if not st:
            return None

        return self.db.query(Observation).filter(
            Observation.station_id == st.id,
            Observation.variable_id == variable_id
        ).order_by(desc(Observation.observed_at)).first()

    def get_latest_by_variable(self, variable_id: str) -> List[Dict[str, Any]]:
        """
        Returns the latest observation for every active station measuring variable_id.
        """
        latest = self.db.query(
            Observation.station_id.label("station_id"),
            func.max(Observation.observed_at).label("observed_at"),
        ).filter(Observation.variable_id == variable_id).group_by(Observation.station_id).subquery()
        rows = self.db.query(Station, Observation).join(
            latest, latest.c.station_id == Station.id
        ).join(
            Observation,
            and_(Observation.station_id == Station.id,
                 Observation.variable_id == variable_id,
                 Observation.observed_at == latest.c.observed_at),
        ).filter(Station.active == True).all()
        return [{
            "station_id": st.id,
            "station_name": st.name,
            "station_code": st.code,
            "municipality": st.municipality,
            "latitude": st.latitude,
            "longitude": st.longitude,
            "station_type": st.station_type,
            "variable_id": obs.variable_id,
            "value": obs.value,
            "unit": obs.unit,
            "observed_at": obs.observed_at.isoformat() if obs.observed_at else None,
            "quality_status": obs.quality_status,
            "quality_code": obs.quality_code,
        } for st, obs in rows]

    def get_time_series(
        self,
        station_id: str,
        variable_id: str,
        start_time: datetime.datetime,
        end_time: datetime.datetime,
        aggregation: str = "raw",  # raw, hour, day
        exclude_quality_status: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Queries time series from database with SQL aggregation.
        Never sends millions of raw rows to agent.
        """
        st = self.get_station_by_id_or_code(station_id)
        if not st:
            return []

        query = self.db.query(Observation).filter(
            Observation.station_id == st.id,
            Observation.variable_id == variable_id,
            Observation.observed_at >= start_time,
            Observation.observed_at <= end_time
        ).order_by(Observation.observed_at)
        if exclude_quality_status:
            query = query.filter(~Observation.quality_status.in_(exclude_quality_status))

        rows = query.all()
        if not rows:
            return []

        if aggregation == "raw":
            return [
                {
                    "timestamp": r.observed_at.isoformat(),
                    "value": round(r.value, 2),
                    "quality_status": r.quality_status
                }
                for r in rows
            ]

        # In-memory fast aggregation by hour or day
        buckets = {}
        for r in rows:
            if aggregation == "day":
                key = r.observed_at.strftime("%Y-%m-%d")
            else:  # hour
                key = r.observed_at.strftime("%Y-%m-%d %H:00")

            if key not in buckets:
                buckets[key] = []
            buckets[key].append(r.value)

        aggregated = []
        for ts, vals in sorted(buckets.items()):
            aggregated.append({
                "timestamp": ts,
                "value": round(sum(vals) / len(vals), 2),
                "min": round(min(vals), 2),
                "max": round(max(vals), 2),
                "count": len(vals)
            })
        return aggregated

    def compare_periods(
        self,
        station_id: str,
        variable_id: str,
        p1_start: datetime.datetime,
        p1_end: datetime.datetime,
        p2_start: datetime.datetime,
        p2_end: datetime.datetime
    ) -> Dict[str, Any]:
        """Compares statistical distributions of a variable between two time windows."""
        p1_series = self.get_time_series(station_id, variable_id, p1_start, p1_end, aggregation="raw")
        p2_series = self.get_time_series(station_id, variable_id, p2_start, p2_end, aggregation="raw")

        def stats_of(series):
            if not series:
                return {"count": 0, "mean": 0.0, "min": 0.0, "max": 0.0, "std": 0.0}
            vals = [s["value"] for s in series]
            mean = sum(vals) / len(vals)
            var = sum((x - mean) ** 2 for x in vals) / len(vals) if len(vals) > 1 else 0
            return {
                "count": len(vals),
                "mean": round(mean, 2),
                "min": round(min(vals), 2),
                "max": round(max(vals), 2),
                "std": round(var ** 0.5, 2)
            }

        s1 = stats_of(p1_series)
        s2 = stats_of(p2_series)

        mean_diff = s2["mean"] - s1["mean"]
        pct_change = round((mean_diff / s1["mean"] * 100), 2) if s1["mean"] != 0 else 0.0

        return {
            "station_id": station_id,
            "variable_id": variable_id,
            "period_1": {
                "start": p1_start.isoformat(),
                "end": p1_end.isoformat(),
                "stats": s1
            },
            "period_2": {
                "start": p2_start.isoformat(),
                "end": p2_end.isoformat(),
                "stats": s2
            },
            "comparison": {
                "absolute_difference": round(mean_diff, 2),
                "percentage_change": pct_change,
                "trend": "increasing" if mean_diff > 0.5 else ("decreasing" if mean_diff < -0.5 else "stable")
            }
        }

    def record_event(self, event_data: Dict[str, Any]) -> EnvironmentalEvent:
        """Stores a detected environmental event."""
        import json
        event = EnvironmentalEvent(
            event_type=event_data["event_type"],
            severity=event_data.get("severity", "medium"),
            title=event_data["title"],
            description=event_data["description"],
            detected_at=event_data.get("detected_at", datetime.datetime.utcnow()),
            station_ids_json=json.dumps(event_data.get("station_ids", [])),
            evidence_json=json.dumps(event_data.get("evidence", {})),
            active=event_data.get("active", True)
        )
        self.db.add(event)
        self.db.commit()
        return event

    def get_active_events(self) -> List[EnvironmentalEvent]:
        """Returns currently active environmental anomaly events."""
        return self.db.query(EnvironmentalEvent).filter(
            EnvironmentalEvent.active == True
        ).order_by(desc(EnvironmentalEvent.detected_at)).all()

    def is_file_processed(self, source_url: str, sha256_hash: str) -> bool:
        """Checks if a historical file has already been ingested with matching checksum."""
        run = self.db.query(IngestionRun).filter(
            IngestionRun.source_url == source_url,
            IngestionRun.sha256 == sha256_hash,
            IngestionRun.status == "completed"
        ).first()
        return run is not None

    def record_ingestion_run(self, run_data: Dict[str, Any]) -> IngestionRun:
        """Records metadata for an ingestion batch (historical lake tracking)."""
        run = IngestionRun(
            source_url=run_data["source_url"],
            sha256=run_data["sha256"],
            file_size=run_data.get("file_size", 0),
            records_count=run_data.get("records_count", 0),
            downloaded_at=run_data.get("downloaded_at", datetime.datetime.utcnow()),
            parser_version=run_data.get("parser_version", "1.0.0"),
            schema_version=run_data.get("schema_version", "1.0.0"),
            status=run_data.get("status", "completed"),
            error_message=run_data.get("error_message")
        )
        self.db.add(run)
        self.db.commit()
        return run

    def record_model_run(self, run_data: Dict[str, Any]) -> ModelRun:
        import json
        run = ModelRun(
            model_name=run_data["model_name"],
            station_id=run_data["station_id"],
            variable_id=run_data["variable_id"],
            trained_at=run_data["trained_at"],
            training_points=run_data["training_points"],
            validation_points=run_data["validation_points"],
            train_start=run_data["train_start"],
            train_end=run_data["train_end"],
            metrics_json=json.dumps(run_data["metrics"]),
            artifact_json=json.dumps(run_data["artifact"]),
        )
        self.db.add(run)
        self.db.commit()
        return run

    def get_model_runs(self, station_id: str, variable_id: str, limit: int = 20) -> List[ModelRun]:
        return self.db.query(ModelRun).filter(
            ModelRun.station_id == station_id,
            ModelRun.variable_id == variable_id,
        ).order_by(desc(ModelRun.trained_at)).limit(limit).all()
