"""Verified regional model/reanalysis connectors; never write into SIATA observations."""

import datetime as dt
import json
import logging
import math
import statistics
import time
import xml.etree.ElementTree as ET
from typing import Any, Callable
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.agent.decision import JevDecisionEngine, persist_decision
from backend.database.connection import get_db
from backend.database.models import RegionalDatum, SourceRun, Station

logger = logging.getLogger(__name__)
UTC = dt.timezone.utc
BOGOTA = ZoneInfo("America/Bogota")

POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
IDEAM_S3_URL = "https://s3-radaresideam.s3.us-east-1.amazonaws.com/"

POWER_PARAMETERS = {
    "T2M": ("temperature", "°C", lambda value: value),
    "RH2M": ("humidity", "%", lambda value: value),
    "PRECTOTCORR": ("rain", "mm/day", lambda value: value),
    "ALLSKY_SFC_SW_DWN": ("solar_irradiance", "MJ/m²/day", lambda value: value),
    "WS10M": ("wind_speed", "m/s", lambda value: value),
    "PS": ("surface_pressure", "hPa", lambda value: value * 10.0),
}

OPEN_METEO_VARIABLES = {
    "temperature_2m": ("temperature", "°C"),
    "relative_humidity_2m": ("humidity", "%"),
    "precipitation": ("rain", "mm"),
    "precipitation_probability": ("rain_probability", "%"),
    "cloud_cover": ("cloud_cover", "%"),
    "wind_speed_10m": ("wind_speed", "m/s"),
    "surface_pressure": ("surface_pressure", "hPa"),
}

IDEAM_RADARS = ("Barrancabermeja", "Carimagua", "Guaviare", "Munchique")


def _now_utc() -> dt.datetime:
    return dt.datetime.now(UTC).replace(tzinfo=None)


def _get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = httpx.get(url, params=params, timeout=25.0, follow_redirects=True)
            if response.status_code == 429 or response.status_code >= 500:
                response.raise_for_status()
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, dict):
                raise ValueError("La fuente devolvió una respuesta JSON inesperada.")
            return body
        except (httpx.HTTPError, ValueError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(0.6 * (2 ** attempt))
    raise RuntimeError(f"Fallo consultando el proveedor ({type(last_error).__name__}).") from last_error


def regional_anchor(db: Session) -> tuple[float, float, int]:
    """Use the coordinate median of geolocated SIATA air stations, never a guessed city point."""
    rows = db.query(Station.latitude, Station.longitude).filter(
        Station.active.is_(True),
        Station.station_type == "air_quality",
        Station.latitude.between(-90, 90),
        Station.longitude.between(-180, 180),
        Station.latitude != 0,
        Station.longitude != 0,
    ).all()
    coordinates = [(float(lat), float(lon)) for lat, lon in rows if math.isfinite(lat) and math.isfinite(lon)]
    if len(coordinates) < 3:
        raise RuntimeError("La red no publica suficientes coordenadas SIATA para fijar el punto regional.")
    return statistics.median(lat for lat, _ in coordinates), statistics.median(lon for _, lon in coordinates), len(coordinates)


def _store_rows(db: Session, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    dialect = db.get_bind().dialect.name
    unique = ["source_id", "record_type", "variable_id", "valid_at", "vintage_id"]
    update_keys = (
        "issued_at", "value", "unit", "latitude", "longitude", "elevation_m",
        "spatial_resolution", "temporal_resolution", "quality_status", "metadata_json", "fetched_at",
    )
    if dialect == "sqlite":
        stmt = sqlite_insert(RegionalDatum).values(rows)
    elif dialect == "postgresql":
        stmt = postgres_insert(RegionalDatum).values(rows)
    else:
        inserted = 0
        for row in rows:
            existing = db.query(RegionalDatum).filter_by(**{key: row[key] for key in unique}).first()
            if existing:
                for key in update_keys:
                    setattr(existing, key, row[key])
            else:
                db.add(RegionalDatum(**row))
                inserted += 1
        db.flush()
        return inserted
    stmt = stmt.on_conflict_do_update(
        index_elements=unique,
        set_={key: getattr(stmt.excluded, key) for key in update_keys},
    )
    db.execute(stmt)
    return len(rows)


def parse_power_response(
    payload: dict[str, Any],
    *,
    latitude: float,
    longitude: float,
    fetched_at: dt.datetime,
) -> list[dict[str, Any]]:
    parameters = payload.get("properties", {}).get("parameter", {})
    metadata = payload.get("parameters", {})
    point = payload.get("geometry", {}).get("coordinates", [longitude, latitude])
    if len(point) < 2:
        raise ValueError("NASA POWER omitió las coordenadas de salida.")
    result = []
    for code, (variable_id, unit, convert) in POWER_PARAMETERS.items():
        for day, raw_value in parameters.get(code, {}).items():
            try:
                value = float(raw_value)
                valid_at = dt.datetime.strptime(day, "%Y%m%d")
            except (TypeError, ValueError):
                continue
            if not math.isfinite(value) or value <= -900:
                continue
            result.append({
                "source_id": "nasa_power",
                "record_type": "regional_analysis",
                "variable_id": variable_id,
                "valid_at": valid_at,
                "vintage_id": "power-daily-final-or-near-real-time",
                "issued_at": None,
                "value": convert(value),
                "unit": unit,
                "latitude": float(point[1]),
                "longitude": float(point[0]),
                "elevation_m": float(point[2]) if len(point) > 2 else None,
                "spatial_resolution": "NASA POWER meteorology grid: approximately 0.5° latitude × 0.625° longitude",
                "temporal_resolution": "daily",
                "quality_status": "gridded_reanalysis",
                "metadata_json": json.dumps({
                    "parameter": code,
                    "provider_units": metadata.get(code, {}).get("units"),
                    "provider_long_name": metadata.get(code, {}).get("longname"),
                    "coordinate_method": "median of active geolocated SIATA air-quality stations",
                    "anchor_station_count": None,
                    "interpretation": "Regional model/reanalysis product; not a station measurement.",
                }, ensure_ascii=False),
                "fetched_at": fetched_at,
            })
    return result


def parse_open_meteo_response(
    payload: dict[str, Any],
    *,
    fetched_at: dt.datetime,
    anchor_station_count: int,
) -> list[dict[str, Any]]:
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    units = payload.get("hourly_units") or {}
    latitude = payload.get("latitude")
    longitude = payload.get("longitude")
    timezone_name = payload.get("timezone") or "UTC"
    if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        raise ValueError("Open-Meteo omitió las coordenadas de la celda consultada.")
    zone = ZoneInfo(timezone_name)
    vintage_id = fetched_at.strftime("%Y%m%dT%H")
    result = []
    for api_name, (variable_id, unit) in OPEN_METEO_VARIABLES.items():
        values = hourly.get(api_name) or []
        for index, raw_value in enumerate(values[:len(times)]):
            if raw_value is None:
                continue
            try:
                value = float(raw_value)
                local_time = dt.datetime.fromisoformat(times[index])
            except (TypeError, ValueError):
                continue
            if not math.isfinite(value):
                continue
            if local_time.tzinfo is None:
                local_time = local_time.replace(tzinfo=zone)
            valid_at = local_time.astimezone(UTC).replace(tzinfo=None)
            # Values earlier than collection time are model analysis/history, not future forecasts.
            if valid_at < fetched_at.replace(minute=0, second=0, microsecond=0):
                continue
            provider_unit = units.get(api_name, unit)
            result.append({
                "source_id": "open_meteo",
                "record_type": "forecast",
                "variable_id": variable_id,
                "valid_at": valid_at,
                "vintage_id": vintage_id,
                "issued_at": fetched_at,
                "value": value,
                "unit": unit,
                "latitude": float(latitude),
                "longitude": float(longitude),
                "elevation_m": float(payload["elevation"]) if payload.get("elevation") is not None else None,
                "spatial_resolution": "Grid/model selected by Open-Meteo Best Match; cell coordinate returned by provider",
                "temporal_resolution": "1 h API output; native model interval may differ",
                "quality_status": "provider_forecast",
                "metadata_json": json.dumps({
                    "api_variable": api_name,
                    "provider_unit": provider_unit,
                    "provider_model_selection": "Best Match",
                    "timezone": timezone_name,
                    "utc_offset_seconds": payload.get("utc_offset_seconds"),
                    "coordinate_method": "median of active geolocated SIATA air-quality stations",
                    "anchor_station_count": anchor_station_count,
                    "interpretation": "External model forecast; not an observation or SIATA-issued forecast.",
                }, ensure_ascii=False),
                "fetched_at": fetched_at,
            })
    return result


def _execute_logged(
    db: Session,
    source_id: str,
    operation: Callable[[], tuple[int, dict[str, Any]]],
    *,
    decide: bool = True,
) -> dict[str, Any]:
    started = _now_utc()
    timer = time.monotonic()
    status, count, error, metadata = "failed", 0, None, {}
    try:
        if decide:
            decision = JevDecisionEngine().decide_ingestion(source_id, enabled=True, due=True)
            persist_decision(db, decision)
            db.commit()
            if not decision.allowed:
                status = "skipped"
                error = decision.reason
                finished = _now_utc()
                run = SourceRun(
                    source_id=source_id, started_at=started, finished_at=finished,
                    status=status, records_count=0,
                    latency_ms=int((time.monotonic() - timer) * 1000),
                    error_message=error, metadata_json="{}",
                )
                db.add(run)
                db.commit()
                return run.to_dict()
        count, metadata = operation()
        status = "success" if count > 0 else "empty"
    except Exception as exc:
        db.rollback()
        error = f"{type(exc).__name__}: {str(exc)[:500]}"
        logger.warning("Source ingestion failed source=%s error=%s", source_id, type(exc).__name__)
    finished = _now_utc()
    run = SourceRun(
        source_id=source_id,
        started_at=started,
        finished_at=finished,
        status=status,
        records_count=count,
        latency_ms=int((time.monotonic() - timer) * 1000),
        error_message=error,
        metadata_json=json.dumps(metadata, ensure_ascii=False, default=str),
    )
    db.add(run)
    db.commit()
    return run.to_dict()


def _ingest_power(db: Session) -> tuple[int, dict[str, Any]]:
    latitude, longitude, station_count = regional_anchor(db)
    today = dt.datetime.now(UTC).date()
    end_day = today - dt.timedelta(days=2)  # provider data have a real publication lag
    start_day = end_day - dt.timedelta(days=13)
    params = {
        "parameters": ",".join(POWER_PARAMETERS),
        "community": "AG",
        "longitude": f"{longitude:.5f}",
        "latitude": f"{latitude:.5f}",
        "start": start_day.strftime("%Y%m%d"),
        "end": end_day.strftime("%Y%m%d"),
        "format": "JSON",
    }
    payload = _get_json(POWER_URL, params)
    fetched_at = _now_utc()
    rows = parse_power_response(payload, latitude=latitude, longitude=longitude, fetched_at=fetched_at)
    for row in rows:
        detail = json.loads(row["metadata_json"])
        detail["anchor_station_count"] = station_count
        row["metadata_json"] = json.dumps(detail, ensure_ascii=False)
    count = _store_rows(db, rows)
    return count, {
        "parameters": list(POWER_PARAMETERS),
        "requested_start": start_day.isoformat(),
        "requested_end": end_day.isoformat(),
        "anchor": {"latitude": latitude, "longitude": longitude, "station_count": station_count},
        "provider_geometry": payload.get("geometry"),
        "source_note": "POWER meteorological fields are gridded model/reanalysis data; not local station data.",
    }


def _ingest_open_meteo(db: Session) -> tuple[int, dict[str, Any]]:
    latitude, longitude, station_count = regional_anchor(db)
    params = {
        "latitude": f"{latitude:.5f}",
        "longitude": f"{longitude:.5f}",
        "hourly": ",".join(OPEN_METEO_VARIABLES),
        "forecast_days": 3,
        "timezone": "America/Bogota",
        "wind_speed_unit": "ms",
    }
    payload = _get_json(OPEN_METEO_URL, params)
    fetched_at = _now_utc()
    rows = parse_open_meteo_response(payload, fetched_at=fetched_at, anchor_station_count=station_count)
    count = _store_rows(db, rows)
    return count, {
        "requested_variables": list(OPEN_METEO_VARIABLES),
        "anchor": {"latitude": latitude, "longitude": longitude, "station_count": station_count},
        "provider_cell": {"latitude": payload.get("latitude"), "longitude": payload.get("longitude"), "elevation_m": payload.get("elevation")},
        "timezone": payload.get("timezone"),
        "forecast_hours_received": len(payload.get("hourly", {}).get("time", [])),
        "provider_model_selection": "Best Match",
    }


def _parse_s3_page(xml_text: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    contents = []
    for item in root.findall("{*}Contents"):
        key = item.findtext("{*}Key")
        modified = item.findtext("{*}LastModified")
        size = item.findtext("{*}Size")
        if key:
            contents.append({"key": key, "last_modified": modified, "size_bytes": int(size or 0)})
    return contents


def _ideam_radar_catalog() -> tuple[int, dict[str, Any]]:
    today = dt.datetime.now(UTC).date()
    days = [today - dt.timedelta(days=2), today - dt.timedelta(days=1)]
    summary: dict[str, Any] = {}
    total = 0
    errors = []
    for radar in IDEAM_RADARS:
        files = []
        for day in days:
            prefix = f"l2_data/{day:%Y/%m/%d}/{radar}/"
            try:
                response = httpx.get(
                    IDEAM_S3_URL,
                    params={"list-type": "2", "prefix": prefix},
                    timeout=20.0,
                    follow_redirects=True,
                )
                response.raise_for_status()
                files.extend(_parse_s3_page(response.text))
            except (httpx.HTTPError, ET.ParseError) as exc:
                errors.append({"radar": radar, "error": type(exc).__name__})
        files.sort(key=lambda item: item["last_modified"] or "", reverse=True)
        total += len(files)
        summary[radar] = {
            "volumes_listed": len(files),
            "latest_archive_object": files[0] if files else None,
        }
    if not total and errors:
        raise RuntimeError("No se pudo consultar el índice S3 público del IDEAM.")
    return total, {
        "date_window_utc": [day.isoformat() for day in days],
        "radars": summary,
        "partial_errors": errors,
        "operation": "metadata_only; raw radar volumes were not downloaded",
        "use_limit": "IDEAM publishes the bucket with about one-day delay; not an operational nowcasting feed.",
    }


def run_open_meteo_job() -> dict[str, Any]:
    with get_db() as db:
        return _execute_logged(db, "open_meteo", lambda: _ingest_open_meteo(db))


def run_nasa_power_job() -> dict[str, Any]:
    with get_db() as db:
        return _execute_logged(db, "nasa_power", lambda: _ingest_power(db))


def run_ideam_radar_job() -> dict[str, Any]:
    with get_db() as db:
        return _execute_logged(db, "ideam_radar", _ideam_radar_catalog)


def source_run_status(db: Session, source_id: str) -> dict[str, Any] | None:
    run = db.query(SourceRun).filter(SourceRun.source_id == source_id).order_by(desc(SourceRun.finished_at), desc(SourceRun.id)).first()
    return run.to_dict() if run else None
