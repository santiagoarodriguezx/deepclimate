"""
SIATA Intelligence - Backend Application Entrypoint.
FastAPI service orchestrating Ingestion, ML models, Jev Agent, and REST API.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.database.connection import init_db
from backend.api.routes import router
from backend.services.scheduler import periodic_worker, pipeline_jobs


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing SIATA Intelligence database and autonomous workers")
    init_db()
    jobs = pipeline_jobs()
    workers = [
        asyncio.create_task(periodic_worker(source_id, interval, job), name=f"pipeline:{source_id}")
        for source_id, interval, job in jobs
    ]
    app.state.pipeline_workers = workers
    app.state.pipeline_jobs = [source_id for source_id, _, _ in jobs]
    logger.info("Autonomous pipeline workers started: %s", app.state.pipeline_jobs)
    yield
    for worker in workers:
        worker.cancel()
    if workers:
        await asyncio.gather(*workers, return_exceptions=True)
    logger.info("SIATA Intelligence workers stopped")


app = FastAPI(
    title="SIATA Intelligence API",
    description="Experimental Environmental AI Platform for the Aburrá Valley consuming official SIATA data.",
    version="2.1.0",
    lifespan=lifespan
)

# CORS configuration for Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173").split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
def root():
    return {
        "service": "SIATA Intelligence API",
        "status": "available",
        "docs": "/docs",
        "frontend": "Start the Next.js application from frontend/.",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
