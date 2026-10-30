"""Small DB-backed periodic scheduler for the single-service SQLite deployment.

Execution checkpoints live in source_runs; job_leases prevent duplicate runs
when more than one API process is accidentally started against the same DB.
Unsuccessful jobs retry with bounded exponential backoff and never block peers.
"""

import asyncio
import datetime
import logging
import os
import uuid
from collections.abc import Callable

from sqlalchemy.exc import IntegrityError

from backend.database.connection import get_db
from backend.database.models import JobLease, SourceRun

logger = logging.getLogger(__name__)
PROCESS_OWNER = uuid.uuid4().hex


def _seconds_until_due(source_id: str, interval_seconds: int) -> float:
    now = datetime.datetime.utcnow()
    with get_db() as db:
        recent = db.query(SourceRun).filter(SourceRun.source_id == source_id).order_by(
            SourceRun.finished_at.desc(), SourceRun.id.desc(),
        ).limit(10).all()
    if not recent or recent[0].finished_at is None:
        return 0
    last = recent[0]
    if last.status == "failed":
        failure_streak = 0
        for run in recent:
            if run.status != "failed":
                break
            failure_streak += 1
        wait = min(3600, 60 * (2 ** min(max(0, failure_streak - 1), 6)))
    else:
        wait = interval_seconds
    elapsed = max(0.0, (now - last.finished_at).total_seconds())
    return max(0.0, wait - elapsed)


def _claim_lease(job_id: str, owner_id: str, lease_seconds: int) -> bool:
    now = datetime.datetime.utcnow()
    deadline = now + datetime.timedelta(seconds=lease_seconds)
    try:
        with get_db() as db:
            row = db.query(JobLease).filter(JobLease.job_id == job_id).first()
            if row is None:
                db.add(JobLease(job_id=job_id, owner_id=owner_id, locked_until=deadline, updated_at=now))
                db.flush()
                return True
            if row.locked_until > now and row.owner_id != owner_id:
                return False
            row.owner_id = owner_id
            row.locked_until = deadline
            row.updated_at = now
            db.flush()
            return True
    except IntegrityError:
        # Concurrent first insert: retry as an atomic conditional update.
        with get_db() as db:
            updated = db.query(JobLease).filter(
                JobLease.job_id == job_id,
                JobLease.locked_until <= now,
            ).update({"owner_id": owner_id, "locked_until": deadline, "updated_at": now})
            return updated == 1


def _release_lease(job_id: str, owner_id: str) -> None:
    now = datetime.datetime.utcnow()
    with get_db() as db:
        db.query(JobLease).filter(
            JobLease.job_id == job_id,
            JobLease.owner_id == owner_id,
        ).update({"locked_until": now, "updated_at": now})


async def periodic_worker(
    source_id: str,
    interval_seconds: int,
    job: Callable[[], dict],
) -> None:
    interval_seconds = max(60, interval_seconds)
    owner = f"{PROCESS_OWNER}:{source_id}"
    # Keep the recovery window short after an unclean process exit while
    # allowing a normal source request enough time to finish.
    lease_seconds = max(300, min(interval_seconds, 600))
    while True:
        delay = await asyncio.to_thread(_seconds_until_due, source_id, interval_seconds)
        if delay > 0:
            await asyncio.sleep(delay)
        claimed = await asyncio.to_thread(_claim_lease, source_id, owner, lease_seconds)
        if not claimed:
            await asyncio.sleep(30)
            continue
        task = asyncio.create_task(asyncio.to_thread(job))
        try:
            result = await asyncio.shield(task)
            logger.info(
                "Scheduled pipeline job finished source=%s status=%s records=%s",
                source_id, result.get("status"), result.get("records_count", result.get("records", 0)),
            )
        except asyncio.CancelledError:
            try:
                await task
            except Exception:
                logger.exception("Scheduled job failed while application was shutting down source=%s", source_id)
            raise
        except Exception:
            logger.exception("Scheduled pipeline job failed source=%s", source_id)
            # A failed run might not have reached the source-run log.
            await asyncio.sleep(60)
        finally:
            await asyncio.to_thread(_release_lease, source_id, owner)


def pipeline_jobs() -> list[tuple[str, int, Callable[[], dict]]]:
    """Each connector runs on its own worker and can fail/retry independently."""
    from backend.ingestion.external_sources import (
        run_ideam_radar_job, run_nasa_power_job, run_open_meteo_job,
    )
    from backend.services.automl import run_auto_ml_job
    from backend.services.ingestion import run_scheduled_discovery_job, run_scheduled_siata_job

    def interval(name: str, fallback: int, minimum: int = 60) -> int:
        try:
            return max(minimum, int(os.getenv(name, str(fallback))))
        except ValueError:
            return fallback

    jobs = []
    if os.getenv("SIATA_SYNC_ENABLED", "true").lower() not in {"0", "false", "no"}:
        jobs.append(("siata", interval("SIATA_SYNC_INTERVAL_SECONDS", 300), run_scheduled_siata_job))
    if os.getenv("SIATA_DISCOVERY_ENABLED", "true").lower() not in {"0", "false", "no"}:
        jobs.append(("siata_discovery", interval("SIATA_DISCOVERY_INTERVAL_SECONDS", 86400), run_scheduled_discovery_job))
    if os.getenv("OPEN_METEO_SYNC_ENABLED", "true").lower() not in {"0", "false", "no"}:
        jobs.append(("open_meteo", interval("OPEN_METEO_SYNC_INTERVAL_SECONDS", 10800), run_open_meteo_job))
    if os.getenv("NASA_POWER_SYNC_ENABLED", "true").lower() not in {"0", "false", "no"}:
        jobs.append(("nasa_power", interval("NASA_POWER_SYNC_INTERVAL_SECONDS", 86400), run_nasa_power_job,))
    if os.getenv("IDEAM_RADAR_CATALOG_ENABLED", "true").lower() not in {"0", "false", "no"}:
        jobs.append(("ideam_radar", interval("IDEAM_RADAR_CATALOG_INTERVAL_SECONDS", 21600), run_ideam_radar_job))
    if os.getenv("SIATA_AUTO_ML_ENABLED", "true").lower() not in {"0", "false", "no"}:
        jobs.append(("automl", interval("SIATA_AUTO_ML_INTERVAL_SECONDS", 21600), run_auto_ml_job))
    return jobs
