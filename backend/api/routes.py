"""
FastAPI Routes for SIATA Intelligence.
Exposes clean REST APIs for Frontend, Agent, ML models, and Observability.
"""

import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database.connection import get_db_session
from backend.database.repository import EnvironmentalRepository
from backend.database.models import JevDecisionRecord, RegionalDatum
from backend.agent.decision import JevDecisionEngine
from backend.monitoring.freshness import FreshnessMonitor, is_recent_observation
from backend.agent.jev import JevAgent
from backend.agent.tools.env_tools import EnvironmentalToolKit
from backend.ingestion.siata.historical import HistoricalLakeManager
from backend.services.ingestion import run_ingestion_sync as run_siata_ingestion_sync
from backend.services.source_catalog import get_source_catalog
from backend.services.gibs import get_gibs_layers

router = APIRouter(prefix="/api")


# Request/Response schemas
class QueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1200)


@router.get("/stations")
def get_stations(
    municipality: Optional[str] = Query(None, description="Filtrar por municipio (e.g. Itagüí, Medellín)"),
    station_type: Optional[str] = Query(None, description="air_quality o meteorology"),
    db: Session = Depends(get_db_session)
):
    repo = EnvironmentalRepository(db)
    stations = repo.get_stations(municipality=municipality, station_type=station_type)
    return [s.to_dict() for s in stations]


@router.get("/stations/{station_id}")
def get_station_detail(station_id: str, db: Session = Depends(get_db_session)):
    repo = EnvironmentalRepository(db)
    st = repo.get_station_by_id_or_code(station_id)
    if not st:
        raise HTTPException(status_code=404, detail="Estación no encontrada.")
    return st.to_dict()


@router.get("/observations/latest")
def get_latest_observations(
    variable_id: str = Query("PM25", description="Variable canonical (PM25, PM10, temperature, rain, etc.)"),
    db: Session = Depends(get_db_session)
):
    repo = EnvironmentalRepository(db)
    return repo.get_latest_by_variable(variable_id)


@router.get("/observations/timeseries")
def get_timeseries(
    station_id: str = Query(..., description="ID o código de estación"),
    variable_id: str = Query("PM25", description="Variable canonical"),
    days: int = Query(7, ge=1, le=60),
    aggregation: str = Query("hour", pattern="^(raw|hour|day)$"),
    db: Session = Depends(get_db_session)
):
    toolkit = EnvironmentalToolKit(db)
    return toolkit.get_time_series(station_id=station_id, variable_id=variable_id, days=days, aggregation=aggregation)


@router.get("/freshness")
def get_freshness_report(
    variable_id: str = Query("PM25"),
    db: Session = Depends(get_db_session)
):
    monitor = FreshnessMonitor(db)
    return monitor.get_valley_freshness_report(variable_id=variable_id)


@router.get("/events")
def get_active_events(db: Session = Depends(get_db_session)):
    repo = EnvironmentalRepository(db)
    events = repo.get_active_events()
    return [e.to_dict() for e in events]


@router.get("/sources")
def get_sources(db: Session = Depends(get_db_session)):
    """Verified source registry with latest persisted health and connector runs."""
    return get_source_catalog(db)


@router.get("/sources/gibs")
def get_gibs_source_layers():
    """Return current NASA GIBS layer time dimensions and tile matrix contracts."""
    try:
        return get_gibs_layers()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"NASA GIBS no está disponible: {type(exc).__name__}.") from exc


@router.get("/sources/data")
def get_regional_source_data(
    source_id: str = Query(..., pattern="^(open_meteo|nasa_power)$"),
    variable_id: str = Query(..., min_length=1, max_length=64),
    record_type: str = Query(..., pattern="^(forecast|regional_analysis)$"),
    hours: int = Query(72, ge=1, le=8760),
    limit: int = Query(1000, ge=1, le=5000),
    db: Session = Depends(get_db_session),
):
    now = datetime.datetime.utcnow()
    query = db.query(RegionalDatum).filter(
        RegionalDatum.source_id == source_id,
        RegionalDatum.variable_id == variable_id,
        RegionalDatum.record_type == record_type,
        RegionalDatum.valid_at >= now - datetime.timedelta(hours=hours),
    ).order_by(RegionalDatum.valid_at, RegionalDatum.issued_at.desc()).limit(limit)
    rows = query.all()
    return {
        "source_id": source_id,
        "variable_id": variable_id,
        "record_type": record_type,
        "records_count": len(rows),
        "data": [row.to_dict() for row in rows],
    }


@router.get("/regional/forecast")
def get_regional_forecast(
    variable_id: str = Query("rain_probability", min_length=1, max_length=64),
    hours: int = Query(24, ge=1, le=72),
    db: Session = Depends(get_db_session),
):
    return EnvironmentalToolKit(db).get_regional_forecast(variable_id=variable_id, hours=hours)


@router.get("/regional/history")
def get_regional_history(
    variable_id: str = Query("rain", min_length=1, max_length=64),
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db_session),
):
    return EnvironmentalToolKit(db).get_regional_history(variable_id=variable_id, days=days)


@router.get("/jev/decisions")
def get_jev_decisions(limit: int = Query(30, ge=1, le=100), db: Session = Depends(get_db_session)):
    rows = db.query(JevDecisionRecord).order_by(JevDecisionRecord.created_at.desc(), JevDecisionRecord.id.desc()).limit(limit).all()
    return {
        "engine": "jev_deterministic_v1",
        "external_provider": JevDecisionEngine.provider_status(),
        "decisions": [row.to_dict() for row in rows],
    }


@router.get("/ml/anomalies")
def get_anomalies(
    station_id: Optional[str] = Query(None, description="Estación para anomalía temporal"),
    variable_id: str = Query("PM25"),
    spatial: bool = Query(False, description="True para anomalías espaciales del valle"),
    db: Session = Depends(get_db_session)
):
    toolkit = EnvironmentalToolKit(db)
    if spatial or not station_id:
        return toolkit.detect_spatial_anomalies(variable_id=variable_id)
    return toolkit.detect_anomalies(station_id=station_id, variable_id=variable_id)


@router.get("/ml/forecast")
def get_forecast(
    station_id: str = Query("ITA-CJUS"),
    variable_id: str = Query("PM25"),
    horizon_hours: int = Query(24, ge=6, le=72),
    db: Session = Depends(get_db_session)
):
    toolkit = EnvironmentalToolKit(db)
    return toolkit.forecast_variable(station_id=station_id, variable_id=variable_id, horizon_hours=horizon_hours)


@router.post("/ml/train")
def train_forecast_model(
    station_id: str = Query(..., min_length=1, max_length=64),
    variable_id: str = Query("PM25", min_length=1, max_length=32),
    db: Session = Depends(get_db_session),
):
    return EnvironmentalToolKit(db).train_forecast_model(station_id, variable_id)


@router.get("/ml/models")
def get_model_runs(
    station_id: str = Query(..., min_length=1, max_length=64),
    variable_id: str = Query("PM25", min_length=1, max_length=32),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db_session),
):
    repo = EnvironmentalRepository(db)
    station = repo.get_station_by_id_or_code(station_id)
    if not station:
        raise HTTPException(status_code=404, detail="Estación no encontrada.")
    return [run.to_dict() for run in repo.get_model_runs(station.id, variable_id, limit)]


@router.get("/ml/correlations")
def get_correlations(
    station_id: str = Query("MED-PJIC"),
    var_a: str = Query("rain"),
    var_b: str = Query("PM25"),
    days: int = Query(14),
    db: Session = Depends(get_db_session)
):
    toolkit = EnvironmentalToolKit(db)
    return toolkit.find_correlations(station_id=station_id, var_a=var_a, var_b=var_b, days=days)


@router.get("/ml/clusters")
def get_clusters(db: Session = Depends(get_db_session)):
    repo = EnvironmentalRepository(db)
    features = [
        {"station_id": row["station_id"], "station_name": row["station_name"],
         "municipality": row["municipality"], "current_pm25": row["value"]}
        for row in repo.get_latest_by_variable("PM25")
        if row["station_type"] == "air_quality" and row["quality_status"] not in {"unvalidated_unit", "retrieval_timestamp"}
        and is_recent_observation(row.get("observed_at"))
    ]
    toolkit = EnvironmentalToolKit(db)
    return toolkit.clustering_engine.cluster_stations(features)


@router.post("/agent/query")
def ask_jev(request: QueryRequest, db: Session = Depends(get_db_session)):
    """
    Submits an analytical question to Jev.
    Executes tool sequence, enforces non-hallucination, and returns transparent evidence.
    """
    agent = JevAgent(db)
    return agent.process_query(request.query)


@router.post("/ingestion/sync")
def run_ingestion_sync(db: Session = Depends(get_db_session)):
    """
    Executes source discovery and real-time ingestion pass across all SIATA networks.
    """
    return run_siata_ingestion_sync(db)


@router.post("/ingestion/historical")
def ingest_historical_sample(
    archive_name: Optional[str] = Query(None, description="Nombre del archivo zip de IDEAM"),
    db: Session = Depends(get_db_session)
):
    """
    Downloads and ingests an official historical monthly zip from SIATA / IDEAM into the raw lake.
    """
    manager = HistoricalLakeManager()
    try:
        if not archive_name:
            available = manager.list_available_archives()
            if not available:
                raise HTTPException(status_code=503, detail="SIATA no publicó archivos históricos disponibles.")
            archive_name = available[-1]
        try:
            return manager.ingest_archive(archive_name, db)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        manager.close()


@router.get("/health")
def health_check(db: Session = Depends(get_db_session)):
    repo = EnvironmentalRepository(db)
    st_count = len(repo.get_stations(active_only=True))
    freshness = FreshnessMonitor(db).get_valley_freshness_report("PM25")

    return {
        "status": "healthy" if freshness["stations_online"] else "degraded",
        "platform": "SIATA Intelligence",
        "active_stations": st_count,
        "data_freshness": {
            "stations_online": freshness["stations_online"],
            "average_lag_seconds": freshness["average_lag_seconds"]
        }
    }
