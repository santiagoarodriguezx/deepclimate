"""
Data Freshness and Quality Monitor.
Continuously calculates lag, station availability, and ingestion health.
Enforces that stale data is never misrepresented as real-time.
"""

import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc
from backend.database.models import Station, Observation


def is_recent_observation(value, max_age_hours: float = 3, now: datetime.datetime | None = None) -> bool:
    """Return whether an observation timestamp is within the accepted real-time window."""
    try:
        observed_at = value if isinstance(value, datetime.datetime) else datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    current = now or datetime.datetime.now(datetime.timezone.utc)
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=datetime.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=datetime.timezone.utc)
    age = (current - observed_at).total_seconds()
    return -300 <= age <= max_age_hours * 3600


class FreshnessMonitor:
    # Health thresholds in seconds
    HEALTHY_THRESHOLD = 3600       # 1 hour
    DELAYED_THRESHOLD = 10800      # 3 hours
    STALE_THRESHOLD = 86400        # 24 hours

    def __init__(self, db: Session):
        self.db = db

    def check_station_freshness(self, station_id: str, variable_id: str = "PM25") -> Dict[str, Any]:
        """
        Calculates exact freshness lag and health status for a specific station & variable.
        """
        now = datetime.datetime.utcnow()
        obs = self.db.query(Observation).filter(
            Observation.station_id == station_id,
            Observation.variable_id == variable_id
        ).order_by(desc(Observation.observed_at)).first()

        if not obs:
            return {
                "station_id": station_id,
                "variable_id": variable_id,
                "last_observation": None,
                "checked_at": now.isoformat(),
                "lag_seconds": None,
                "status": "UNKNOWN",
                "human_lag": "Sin registros disponibles"
            }

        lag_seconds = int((now - obs.observed_at).total_seconds())

        if lag_seconds < 0:
            status = "HEALTHY"
            lag_seconds = 0
        elif lag_seconds <= self.HEALTHY_THRESHOLD:
            status = "HEALTHY"
        elif lag_seconds <= self.DELAYED_THRESHOLD:
            status = "DELAYED"
        elif lag_seconds <= self.STALE_THRESHOLD:
            status = "STALE"
        else:
            status = "OFFLINE"

        # Human readable lag
        if lag_seconds < 60:
            human = f"Hace {lag_seconds}s"
        elif lag_seconds < 3600:
            human = f"Hace {lag_seconds // 60}m"
        elif lag_seconds < 86400:
            human = f"Hace {lag_seconds // 3600}h { (lag_seconds % 3600) // 60 }m"
        else:
            human = f"Hace {lag_seconds // 86400} días"

        return {
            "station_id": station_id,
            "variable_id": variable_id,
            "value": obs.value,
            "unit": obs.unit,
            "last_observation": obs.observed_at.isoformat(),
            "checked_at": now.isoformat(),
            "lag_seconds": lag_seconds,
            "status": status,
            "human_lag": human
        }

    def get_valley_freshness_report(self, variable_id: str = "PM25") -> Dict[str, Any]:
        """
        Produces a comprehensive system-wide health and freshness report for all active stations.
        """
        query = self.db.query(Station).filter(Station.active == True)
        if variable_id in {"PM25", "PM10", "O3", "NO", "NO2", "CO", "SO2"}:
            query = query.filter(Station.station_type == "air_quality")
        stations = query.all()
        now = datetime.datetime.utcnow()

        station_reports = []
        counts = {
            "HEALTHY": 0,
            "DELAYED": 0,
            "STALE": 0,
            "OFFLINE": 0,
            "UNKNOWN": 0
        }

        total_lag = 0
        counted_lags = 0

        for st in stations:
            rep = self.check_station_freshness(st.id, variable_id)
            rep["station_name"] = st.name
            rep["municipality"] = st.municipality
            counts[rep["status"]] += 1
            if rep["lag_seconds"] is not None:
                total_lag += rep["lag_seconds"]
                counted_lags += 1
            station_reports.append(rep)

        avg_lag_seconds = int(total_lag / counted_lags) if counted_lags > 0 else 0

        return {
            "variable_id": variable_id,
            "checked_at": now.isoformat(),
            "total_stations": len(stations),
            "status_distribution": counts,
            "average_lag_seconds": avg_lag_seconds,
            "stations_online": counts["HEALTHY"] + counts["DELAYED"],
            "stations_offline": counts["OFFLINE"] + counts["UNKNOWN"],
            "stations": station_reports
        }
