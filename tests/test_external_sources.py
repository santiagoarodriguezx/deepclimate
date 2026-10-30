import datetime as dt
import json
import os
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.agent.decision import JevDecisionEngine, persist_decision
from backend.database.models import Base, JevDecisionRecord, RegionalDatum, SourceRun
from backend.ingestion.external_sources import (
    _store_rows,
    parse_open_meteo_response,
    parse_power_response,
)
from backend.services.source_catalog import get_source_catalog


class ExternalSourceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_open_meteo_keeps_only_future_forecast_and_normalizes_timezone(self):
        fetched_at = dt.datetime(2026, 10, 30, 15, 0)
        payload = {
            "latitude": 6.22,
            "longitude": -75.55,
            "elevation": 1480,
            "timezone": "America/Bogota",
            "utc_offset_seconds": -18000,
            "hourly_units": {"temperature_2m": "°C"},
            "hourly": {
                "time": ["2026-10-30T09:00", "2026-10-30T10:00", "2026-10-30T11:00"],
                "temperature_2m": [19.0, 20.0, None],
            },
        }

        rows = parse_open_meteo_response(payload, fetched_at=fetched_at, anchor_station_count=12)

        self.assertEqual([row["valid_at"] for row in rows], [fetched_at])
        self.assertEqual(rows[0]["record_type"], "forecast")
        self.assertEqual(rows[0]["value"], 20.0)
        self.assertEqual(rows[0]["latitude"], 6.22)
        self.assertIn("not an observation", rows[0]["metadata_json"])

    def test_nvidia_source_reports_configuration_without_claiming_live_health(self):
        with patch.dict(os.environ, {"NVIDIA_API_KEY": "nvidia-test-key"}, clear=True):
            catalog = get_source_catalog(self.db)
        source = next(item for item in catalog["sources"] if item["id"] == "nvidia_nim")
        self.assertEqual(source["status"], "configured")
        self.assertIsNone(source["last_run"])
        self.assertIn("servicio remoto", source["limitation"])

    def test_power_skips_missing_sentinel_and_converts_pressure_to_hpa(self):
        payload = {
            "geometry": {"coordinates": [-75.5, 6.2, 1500]},
            "properties": {"parameter": {
                "T2M": {"20261027": 18.5},
                "PRECTOTCORR": {"20261027": -999},
                "PS": {"20261027": 83.7},
            }},
            "parameters": {"T2M": {"units": "C"}, "PS": {"units": "kPa"}},
        }

        rows = parse_power_response(
            payload,
            latitude=6.2,
            longitude=-75.5,
            fetched_at=dt.datetime(2026, 10, 30, 15),
        )

        by_variable = {row["variable_id"]: row for row in rows}
        self.assertNotIn("rain", by_variable)
        self.assertEqual(by_variable["surface_pressure"]["value"], 837.0)
        self.assertEqual(by_variable["surface_pressure"]["record_type"], "regional_analysis")

    def test_regional_upsert_is_idempotent_per_forecast_vintage(self):
        row = {
            "source_id": "open_meteo", "record_type": "forecast", "variable_id": "temperature",
            "valid_at": dt.datetime(2026, 10, 30, 15), "vintage_id": "20261030T15",
            "issued_at": dt.datetime(2026, 10, 30, 15), "value": 20.0, "unit": "°C",
            "latitude": 6.22, "longitude": -75.55, "elevation_m": 1480,
            "spatial_resolution": "provider cell", "temporal_resolution": "1 h",
            "quality_status": "provider_forecast", "metadata_json": "{}",
            "fetched_at": dt.datetime(2026, 10, 30, 15),
        }

        _store_rows(self.db, [row])
        _store_rows(self.db, [{**row, "value": 21.0}])

        stored = self.db.query(RegionalDatum).all()
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0].value, 21.0)

    def test_decisions_are_deterministic_and_persisted(self):
        engine = JevDecisionEngine()
        accepted = engine.decide_model_candidate(
            "station:PM25", dataset_ready=True, mae=1.0, baseline_mae=1.2,
        )
        rejected = engine.decide_model_candidate(
            "station:PM25", dataset_ready=True, mae=1.3, baseline_mae=1.2,
        )
        persist_decision(self.db, rejected)
        self.db.commit()

        self.assertTrue(accepted.allowed)
        self.assertFalse(rejected.allowed)
        record = self.db.query(JevDecisionRecord).one()
        self.assertFalse(record.allowed)
        self.assertEqual(json.loads(record.metadata_json)["mae"], 1.3)

    def test_source_catalog_reports_connected_runs_and_separate_discovery(self):
        now = dt.datetime.utcnow()
        self.db.add_all([
            SourceRun(source_id="open_meteo", started_at=now, finished_at=now, status="success", records_count=24),
            SourceRun(
                source_id="siata_discovery", started_at=now, finished_at=now,
                status="partial", records_count=6,
                metadata_json=json.dumps({"sources": [{"id": "air", "status": "active"}]}),
            ),
        ])
        self.db.commit()

        catalog = get_source_catalog(self.db)
        sources = {item["id"]: item for item in catalog["sources"]}

        self.assertEqual(sources["open_meteo"]["status"], "success")
        self.assertEqual(sources["open_meteo"]["last_run"]["records_count"], 24)
        self.assertEqual(sources["siata"]["availability_scan"]["status"], "partial")


if __name__ == "__main__":
    unittest.main()
