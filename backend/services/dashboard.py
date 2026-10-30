"""Read-only snapshot that brings persisted source data into one dashboard API."""

import datetime

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from backend.agent.tools.env_tools import EnvironmentalToolKit
from backend.database.models import EnvironmentalEvent, ForecastRun, ModelRun, Observation, SourceRun, Station
from backend.database.repository import EnvironmentalRepository
from backend.monitoring.freshness import FreshnessMonitor, INVALID_OBSERVATION_QUALITY
from backend.services.source_catalog import get_source_catalog

OBSERVATION_VARIABLES = (
    "PM25", "PM10", "O3", "NO2", "temperature", "humidity", "rain",
    "wind_speed", "wind_direction", "pressure", "river_level",
)
REGIONAL_FORECAST_VARIABLES = (
    "rain_probability", "rain", "temperature", "humidity", "wind_speed", "surface_pressure", "cloud_cover",
)
REGIONAL_HISTORY_VARIABLES = ("rain", "temperature", "humidity", "wind_speed", "solar_irradiance")
NETWORK_TREND_VARIABLES = ("PM25", "PM10", "O3", "NO2")


def build_dashboard_snapshot(db: Session) -> dict:
    stations = db.query(Station).filter(Station.active.is_(True)).order_by(Station.name).all()
    station_counts = dict(
        db.query(Station.station_type, func.count(Station.id))
        .filter(Station.active.is_(True))
        .group_by(Station.station_type)
        .all()
    )
    repository = EnvironmentalRepository(db)
    toolkit = EnvironmentalToolKit(db)
    observations = {
        variable_id: repository.get_latest_by_variable(variable_id)
        for variable_id in OBSERVATION_VARIABLES
    }
    regional_forecasts = {
        variable_id: toolkit.get_regional_forecast(variable_id=variable_id, hours=72)
        for variable_id in REGIONAL_FORECAST_VARIABLES
    }
    regional_history = {
        variable_id: toolkit.get_regional_history(variable_id=variable_id, days=14)
        for variable_id in REGIONAL_HISTORY_VARIABLES
    }
    network_history = _network_hourly_history(db)
    forecasts = db.query(ForecastRun).join(
        Station, Station.id == ForecastRun.station_id,
    ).filter(Station.active.is_(True)).order_by(
        Station.municipality, Station.name, ForecastRun.horizon_hours,
    ).all()
    models = db.query(ModelRun).join(
        Station, Station.id == ModelRun.station_id,
    ).filter(Station.active.is_(True)).order_by(desc(ModelRun.trained_at)).limit(50).all()
    events = db.query(EnvironmentalEvent).filter(
        EnvironmentalEvent.active.is_(True),
    ).order_by(desc(EnvironmentalEvent.detected_at)).limit(12).all()

    latest_runs = {}
    for run in db.query(SourceRun).order_by(desc(SourceRun.finished_at), desc(SourceRun.id)).all():
        latest_runs.setdefault(run.source_id, run)

    return {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "refresh_after_seconds": 60,
        "stations": [{
            "id": station.id,
            "source_id": station.source_id,
            "name": station.name,
            "code": station.code,
            "municipality": station.municipality,
            "latitude": station.latitude,
            "longitude": station.longitude,
            "altitude": station.altitude,
            "station_type": station.station_type,
            "active": station.active,
            "subbasin": station.subbasin,
            "neighborhood": station.neighborhood,
        } for station in stations],
        "station_counts": station_counts,
        "observations": observations,
        "regional_forecasts": regional_forecasts,
        "regional_history": regional_history,
        "network_history": network_history,
        "model_forecasts": [record.to_dict() for record in forecasts],
        "models": [record.to_dict() for record in models],
        "events": [event.to_dict() for event in events],
        "freshness": FreshnessMonitor(db).get_valley_freshness_report("PM25"),
        "sources": get_source_catalog(db),
        "pipeline_runs": [run.to_dict() for run in latest_runs.values()],
    }


def _network_hourly_history(db: Session, days: int = 7) -> dict:
    """Hourly regional medians from valid SIATA station observations (not spatial interpolation)."""
    now = datetime.datetime.utcnow()
    rows = db.query(
        Observation.variable_id, Observation.station_id, Observation.observed_at, Observation.value,
    ).join(Station, Station.id == Observation.station_id).filter(
        Station.active.is_(True),
        Observation.variable_id.in_(NETWORK_TREND_VARIABLES),
        Observation.observed_at >= now - datetime.timedelta(days=days),
        Observation.quality_status.notin_(INVALID_OBSERVATION_QUALITY),
    ).order_by(Observation.observed_at).all()

    by_station_hour: dict[tuple[str, datetime.datetime, str], list[float]] = {}
    for variable_id, station_id, observed_at, value in rows:
        hour = observed_at.replace(minute=0, second=0, microsecond=0)
        by_station_hour.setdefault((variable_id, hour, station_id), []).append(float(value))
    by_variable_hour: dict[str, dict[datetime.datetime, list[float]]] = {key: {} for key in NETWORK_TREND_VARIABLES}
    for (variable_id, hour, _station_id), values in by_station_hour.items():
        by_variable_hour[variable_id].setdefault(hour, []).append(sum(values) / len(values))

    unit_by_variable = {"PM25": "µg/m³", "PM10": "µg/m³", "O3": "µg/m³", "NO2": "µg/m³"}
    result = {}
    for variable_id, buckets in by_variable_hour.items():
        series = []
        for hour, station_means in sorted(buckets.items()):
            sorted_values = sorted(station_means)
            middle = len(sorted_values) // 2
            median = sorted_values[middle] if len(sorted_values) % 2 else (sorted_values[middle - 1] + sorted_values[middle]) / 2
            series.append({"timestamp": hour.isoformat(), "value": median, "count": len(station_means)})
        result[variable_id] = {
            "status": "available" if series else "unavailable",
            "source_id": "siata",
            "source_name": "SIATA · mediana horaria de estaciones válidas",
            "variable_id": variable_id,
            "unit": unit_by_variable[variable_id],
            "spatial_resolution": "Mediana de estaciones con observaciones; sin interpolación espacial",
            "temporal_resolution": "Mediana horaria de 7 días",
            "series": series,
        }
    return result
