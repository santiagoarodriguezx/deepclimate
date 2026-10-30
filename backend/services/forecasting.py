"""Persist rolling station forecasts from the latest approved model versions."""

import collections
import datetime
import json
import logging

from sqlalchemy.orm import Session

from backend.agent.tools.env_tools import EnvironmentalToolKit
from backend.database.connection import get_db
from backend.database.models import ForecastRun, Station
from backend.ingestion.external_sources import _execute_logged

logger = logging.getLogger(__name__)
HORIZONS_HOURS = (24, 48, 72)


def _generate_forecasts(db: Session) -> tuple[int, dict]:
    stations = db.query(Station).filter(
        Station.active.is_(True),
        Station.station_type == "air_quality",
    ).order_by(Station.id).all()
    toolkit = EnvironmentalToolKit(db)
    status_counts = collections.Counter()
    available_horizons = 0
    generated_points = 0
    generated_at = datetime.datetime.utcnow()

    for station in stations:
        try:
            result = toolkit.forecast_variable(station.id, "PM25", horizon_hours=72)
        except Exception as exc:
            logger.warning("Forecast generation failed station=%s error=%s", station.id, type(exc).__name__)
            db.rollback()
            result = {"status": "processing_error", "reason": f"Error de inferencia: {type(exc).__name__}", "forecast": []}

        points = result.get("forecast") or []
        for horizon in HORIZONS_HOURS:
            horizon_points = points[:horizon] if result.get("status") == "available" else []
            status = result.get("status", "processing_error")
            reason = result.get("reason")
            if status == "available" and len(horizon_points) != horizon:
                status = "insufficient_data"
                reason = f"El modelo devolvió {len(horizon_points)} de {horizon} horas requeridas."
                horizon_points = []

            row = db.query(ForecastRun).filter(
                ForecastRun.station_id == station.id,
                ForecastRun.variable_id == "PM25",
                ForecastRun.horizon_hours == horizon,
            ).first()
            if row is None:
                row = ForecastRun(
                    station_id=station.id,
                    variable_id="PM25",
                    horizon_hours=horizon,
                )
                db.add(row)
            row.model_run_id = result.get("model_run_id")
            row.generated_at = generated_at
            row.status = status
            row.reason = reason
            row.metrics_json = json.dumps(result.get("metrics") or {}, ensure_ascii=False)
            row.forecast_json = json.dumps(horizon_points, ensure_ascii=False)
            status_counts[status] += 1
            if status == "available":
                available_horizons += 1
                generated_points += len(horizon_points)

    db.commit()
    return available_horizons, {
        "stations_evaluated": len(stations),
        "horizons_hours": list(HORIZONS_HOURS),
        "available_horizons": available_horizons,
        "prediction_points": generated_points,
        "statuses": dict(status_counts),
        "policy": "Latest approved PM2.5 model; one inference to 72 h is sliced into the 24, 48 and 72 h snapshots.",
    }


def run_forecast_job() -> dict:
    """Scheduler entry point; one persisted row per active air station and horizon."""
    with get_db() as db:
        return _execute_logged(
            db,
            "model_forecasts",
            lambda: _generate_forecasts(db),
            decide=False,
        )
