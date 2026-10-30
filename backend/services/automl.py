"""Scheduled, data-gated champion/challenger training for SIATA station models."""

import datetime
import logging

from sqlalchemy import func, desc

from backend.agent.decision import JevDecisionEngine, persist_decision
from backend.agent.tools.env_tools import EnvironmentalToolKit
from backend.database.connection import get_db
from backend.database.models import Observation, Station
from backend.ingestion.external_sources import _execute_logged
from backend.monitoring.freshness import INVALID_OBSERVATION_QUALITY

logger = logging.getLogger(__name__)
MIN_OBSERVATIONS_TO_SCREEN = 72


def _train_batch(db):
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=60)
    candidates = db.query(
        Observation.station_id,
        func.count(Observation.id).label("points"),
    ).join(Station, Station.id == Observation.station_id).filter(
        Station.active.is_(True),
        Station.station_type == "air_quality",
        Observation.variable_id == "PM25",
        Observation.observed_at >= cutoff,
        Observation.quality_status.notin_(INVALID_OBSERVATION_QUALITY),
    ).group_by(Observation.station_id).having(
        func.count(Observation.id) >= MIN_OBSERVATIONS_TO_SCREEN,
    ).order_by(desc("points")).all()

    if not candidates:
        decision = JevDecisionEngine().decide_model_candidate(
            "SIATA:PM25:auto-scan",
            dataset_ready=False,
            mae=None,
            baseline_mae=None,
        )
        decision.reason = "No hay series PM2.5 recientes con al menos 72 observaciones para evaluar candidatos."
        persist_decision(db, decision)
        db.commit()
        return 0, {
            "candidate_stations": 0,
            "required_observations_for_screening": MIN_OBSERVATIONS_TO_SCREEN,
            "reason": decision.reason,
        }

    toolkit = EnvironmentalToolKit(db)
    trained = []
    outcomes = []
    for station_id, point_count in candidates:
        result = toolkit.train_forecast_model(station_id, "PM25")
        outcomes.append({
            "station_id": station_id,
            "recent_observations": int(point_count),
            "status": result.get("status"),
            "reason": result.get("reason"),
        })
        if result.get("status") == "trained":
            trained.append(station_id)
    return len(trained), {
        "candidate_stations": len(candidates),
        "models_promoted": trained,
        "outcomes": outcomes,
        "selection_policy": "Temporal validation; candidate must beat persistence baseline and existing champion MAE.",
    }


def run_auto_ml_job() -> dict:
    with get_db() as db:
        result = _execute_logged(db, "automl", lambda: _train_batch(db), decide=False)
        logger.info("Automated ML run status=%s records=%s", result["status"], result["records_count"])
        return result
