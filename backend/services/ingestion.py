import datetime
import json
import threading
import time

from sqlalchemy.orm import Session

from backend.agent.decision import JevDecisionEngine, persist_decision
from backend.database.connection import get_db
from backend.events.alert_engine import AlertEngine
from backend.ingestion.siata.air import AirQualityAdapter
from backend.ingestion.siata.discovery import SiataDiscovery
from backend.ingestion.siata.meteorology import MeteorologyAdapter
from backend.ingestion.siata.stations import StationAdapter
from backend.database.models import SourceRun


_sync_lock = threading.Lock()


def run_scheduled_siata_job() -> dict:
    """Entry point for the independent persistent SIATA scheduler worker."""
    with get_db() as db:
        return run_ingestion_sync(db)


def run_scheduled_discovery_job() -> dict:
    """Check the source catalog independently; slow probes cannot delay sensor ingestion."""
    with get_db() as db:
        started = datetime.datetime.utcnow()
        timer = time.monotonic()
        decision = JevDecisionEngine().decide_ingestion("siata_discovery", enabled=True, due=True)
        persist_decision(db, decision)
        db.commit()
        discovery = SiataDiscovery(timeout=4.0)
        try:
            catalog = discovery.scan_sources()
            sources = catalog.get("sources", [])
            active = sum(source.get("status") == "active" for source in sources)
            status = "success" if sources and active == len(sources) else "partial" if active else "failed"
            failed = [source.get("id") for source in sources if source.get("status") != "active"]
            error = f"Fuentes sin respuesta válida: {', '.join(failed)}"[:1000] if failed else None
            metadata = {
                "version": catalog.get("version"),
                "source_count": len(sources),
                "active_count": active,
                "sources": [{"id": source.get("id"), "status": source.get("status")} for source in sources],
            }
        except Exception as exc:
            db.rollback()
            status = "failed"
            active = 0
            error = f"{type(exc).__name__}: {str(exc)[:500]}"
            metadata = {"source_count": 0, "active_count": 0, "sources": []}
        finally:
            discovery.close()
        run = SourceRun(
            source_id="siata_discovery",
            started_at=started,
            finished_at=datetime.datetime.utcnow(),
            status=status,
            records_count=active,
            latency_ms=int((time.monotonic() - timer) * 1000),
            error_message=error,
            metadata_json=json.dumps(metadata, ensure_ascii=False),
        )
        db.add(run)
        db.commit()
        return run.to_dict()


def run_ingestion_sync(db: Session) -> dict:
    if not _sync_lock.acquire(blocking=False):
        return {"status": "in_progress"}
    started = datetime.datetime.utcnow()
    timer = time.monotonic()
    results, errors = {}, {}
    try:
        decision = JevDecisionEngine().decide_ingestion("siata", enabled=True, due=True)
        persist_decision(db, decision)
        db.commit()
        run = SourceRun(
            source_id="siata",
            started_at=started,
            finished_at=None,
            status="running",
            records_count=0,
            latency_ms=None,
            error_message=None,
            metadata_json="{}",
        )
        db.add(run)
        db.commit()
        for name, adapter_type, method in [
            ("station_sync", StationAdapter, "sync_stations"),
            ("air_quality_sync", AirQualityAdapter, "fetch_and_ingest"),
            ("meteorology_sync", MeteorologyAdapter, "fetch_and_ingest"),
        ]:
            adapter = adapter_type()
            try:
                result = getattr(adapter, method)(db)
                results[name] = result
                errors.update({f"{name}.{key}": value for key, value in result.get("errors", {}).items()})
            except Exception as exc:
                db.rollback()
                errors[name] = str(exc)
            finally:
                adapter.close()

        try:
            events = AlertEngine(db).evaluate_events()
            results["new_events_detected"] = len(events)
        except Exception as exc:
            db.rollback()
            errors["alert_engine"] = str(exc)

        results["status"] = "success" if not errors else "partial"
        if errors:
            results["errors"] = errors
        count_keys = {
            "inserted", "inserted_observations", "records_count", "new_records",
            "total_synced", "total_inserted",
        }
        records_count = sum(
            int(value)
            for item in results.values() if isinstance(item, dict)
            for key, value in item.items()
            if key in count_keys and isinstance(value, (int, float))
        )
        run.finished_at = datetime.datetime.utcnow()
        run.status = results["status"]
        run.records_count = records_count
        run.latency_ms = int((time.monotonic() - timer) * 1000)
        run.error_message = "; ".join(f"{key}: {value}" for key, value in errors.items())[:1000] or None
        db.commit()
        return results
    except Exception as exc:
        db.rollback()
        failed_run = db.query(SourceRun).filter(SourceRun.source_id == "siata", SourceRun.started_at == started).first()
        if failed_run:
            failed_run.finished_at = datetime.datetime.utcnow()
            failed_run.status = "failed"
            failed_run.latency_ms = int((time.monotonic() - timer) * 1000)
            failed_run.error_message = f"{type(exc).__name__}: {str(exc)[:500]}"
            db.commit()
        raise
    finally:
        _sync_lock.release()
