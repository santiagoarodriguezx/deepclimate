"""
Comprehensive end-to-end test script for SIATA Intelligence.
Verifies DB, Ingestion, ML models, and Jev Agent.
"""

import sys
import os
from pathlib import Path

# Add the project root so this integration script works from any checkout path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend.database.connection import init_db, get_db
from backend.database.repository import EnvironmentalRepository
from backend.ingestion.siata.discovery import SiataDiscovery
from backend.ingestion.siata.stations import StationAdapter
from backend.ingestion.siata.air import AirQualityAdapter
from backend.ingestion.siata.meteorology import MeteorologyAdapter
from backend.ingestion.siata.historical import HistoricalLakeManager
from backend.events.alert_engine import AlertEngine
from backend.agent.jev import JevAgent

print("=== 1. Testing DB Initialization ===")
init_db()
print("Database and canonical variables seeded successfully.")

with get_db() as db:
    repo = EnvironmentalRepository(db)

    print("\n=== 2. Testing Source Discovery ===")
    disc = SiataDiscovery()
    cat = disc.scan_sources()
    print(f"Catalog generated with {len(cat['sources'])} official sources.")
    disc.close()
    if not cat["sources"]:
        raise RuntimeError("SIATA source discovery returned no sources.")

    print("\n=== 3. Testing Station Synchronization ===")
    st_adapter = StationAdapter()
    st_res = st_adapter.sync_stations(db)
    print("Stations sync result:", st_res)
    st_adapter.close()
    if not st_res.get("total_synced"):
        raise RuntimeError("Station sync did not return any usable stations.")

    print("\n=== 4. Testing Real-time Air Quality Ingestion ===")
    air_adapter = AirQualityAdapter()
    air_res = air_adapter.fetch_and_ingest(db)
    print("Air quality ingestion result:", air_res)
    air_adapter.close()
    if air_res.get("errors"):
        raise RuntimeError(f"Air quality ingestion errors: {air_res['errors']}")

    print("\n=== 5. Testing Real-time Meteorology Ingestion ===")
    met_adapter = MeteorologyAdapter()
    met_res = met_adapter.fetch_and_ingest(db, sample_telemetry=5)
    print("Meteorology ingestion result:", met_res)
    met_adapter.close()
    if met_res.get("errors"):
        raise RuntimeError(f"Meteorology ingestion errors: {met_res['errors']}")

    print("\n=== 6. Testing Historical Data Lake Ingestion (1 archive, sample files) ===")
    hist_manager = HistoricalLakeManager()
    archives = hist_manager.list_available_archives()
    print(f"Found {len(archives)} IDEAM archives. Testing with latest: {archives[-1] if archives else 'None'}")
    if archives:
        hist_res = hist_manager.ingest_archive(archives[-1], db, max_xls_files=5)
        print("Historical ingestion result:", hist_res)
        if hist_res.get("status") != "completed" or not hist_res.get("xls_files_parsed"):
            raise RuntimeError(f"Historical ingestion did not parse data: {hist_res}")
    hist_manager.close()

    print("\n=== 7. Testing Alert Engine ===")
    alert_engine = AlertEngine(db)
    events = alert_engine.evaluate_events()
    print(f"Alert engine evaluated. Generated {len(events)} events.")

    print("\n=== 8. Testing Jev Agent Queries ===")
    agent = JevAgent(db)

    # Query 1
    q1 = "¿Qué está pasando con el aire en Itagüí?"
    print(f"\n--- Query 1: '{q1}' ---")
    resp1 = agent.process_query(q1)
    print("Answer:\n", resp1["answer"])
    if not resp1.get("answer"):
        raise RuntimeError("Jev returned an empty answer.")
    print("\nEvidence:\n", resp1["evidence"])

    # Query 2
    q2 = "¿Está pasando algo extraño en el Valle ahora?"
    print(f"\n--- Query 2: '{q2}' ---")
    resp2 = agent.process_query(q2)
    print("Answer:\n", resp2["answer"])
    print("\nEvidence:\n", resp2["evidence"])

    # Query 3
    q3 = "¿Qué variables están correlacionadas con PM2.5?"
    print(f"\n--- Query 3: '{q3}' ---")
    resp3 = agent.process_query(q3)
    print("Answer:\n", resp3["answer"])
    print("\nEvidence:\n", resp3["evidence"])

print("\n=== End-to-end SIATA integration run completed successfully. ===")
