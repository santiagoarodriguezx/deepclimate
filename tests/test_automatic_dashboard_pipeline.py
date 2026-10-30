import datetime as dt
import json
import math
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database.models import Base, ForecastRun, ModelRun, Observation, Station, Variable
from backend.monitoring.freshness import FreshnessMonitor
from backend.services.dashboard import build_dashboard_snapshot
from backend.services.forecasting import _generate_forecasts
from backend.ml.forecasting.predictor import EnvironmentalForecaster
from backend.api.routes import router


class AutomaticDashboardPipelineTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.db.add(Variable(id="PM25", code="PM25", name="PM2.5", unit="µg/m³", category="air_quality"))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_real_model_forecasts_are_persisted_and_exposed_in_unified_snapshot(self):
        now = dt.datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        station = Station(
            id="AQ-01", source_id="1", name="Estación de prueba", code="AQ-01",
            municipality="Medellín", latitude=6.24, longitude=-75.58,
            station_type="air_quality", active=True,
        )
        waiting_station = Station(
            id="AQ-02", source_id="2", name="Estación en recopilación", code="AQ-02",
            municipality="Medellín", latitude=6.25, longitude=-75.57,
            station_type="air_quality", active=True,
        )
        self.db.add_all([station, waiting_station])
        self.db.flush()

        start = now - dt.timedelta(hours=71)
        series = []
        for hour in range(72):
            stamp = start + dt.timedelta(hours=hour)
            value = 12.0 + math.sin(hour / 4) + hour * 0.015
            self.db.add(Observation(
                station_id=station.id, variable_id="PM25", observed_at=stamp,
                value=value, unit="µg/m³", quality_status="good", source="integration-test",
            ))
            series.append({"timestamp": stamp.isoformat(), "value": value})

        trained = EnvironmentalForecaster().train(series)
        self.assertEqual(trained["status"], "trained")
        model = ModelRun(
            model_name=trained["model"], station_id=station.id, variable_id="PM25",
            trained_at=now, training_points=trained["training_points"],
            validation_points=trained["validation_points"],
            train_start=dt.datetime.fromisoformat(trained["train_start"]),
            train_end=dt.datetime.fromisoformat(trained["train_end"]),
            metrics_json=json.dumps(trained["metrics"]),
            artifact_json=json.dumps(trained["artifact"]),
        )
        self.db.add(model)
        self.db.commit()

        available, run_details = _generate_forecasts(self.db)
        self.assertEqual(available, 3)
        self.assertEqual(run_details["statuses"], {"available": 3, "model_not_trained": 3})

        forecasts = self.db.query(ForecastRun).order_by(ForecastRun.station_id, ForecastRun.horizon_hours).all()
        self.assertEqual(len(forecasts), 6)
        by_horizon = {row.horizon_hours: row for row in forecasts if row.station_id == station.id}
        self.assertEqual(set(by_horizon), {24, 48, 72})
        self.assertEqual([len(by_horizon[hour].to_dict()["forecast"]) for hour in (24, 48, 72)], [24, 48, 72])
        self.assertTrue(all(row.status == "available" for row in by_horizon.values()))
        self.assertTrue(all(row.model_run_id == model.id for row in by_horizon.values()))

        _generate_forecasts(self.db)
        self.assertEqual(self.db.query(ForecastRun).count(), 6)

        snapshot = build_dashboard_snapshot(self.db)
        self.assertEqual(snapshot["station_counts"], {"air_quality": 2})
        self.assertEqual(len(snapshot["model_forecasts"]), 6)
        self.assertEqual(len(snapshot["models"]), 1)
        self.assertEqual(snapshot["models"][0]["id"], model.id)
        self.assertEqual(snapshot["freshness"]["stations_online"], 1)

    def test_empty_network_has_unknown_lag_instead_of_zero(self):
        self.db.add(Station(
            id="AQ-03", source_id="3", name="Sin lecturas", code="AQ-03",
            municipality="Medellín", latitude=6.24, longitude=-75.58,
            station_type="air_quality", active=True,
        ))
        self.db.commit()

        freshness = FreshnessMonitor(self.db).get_valley_freshness_report("PM25")
        self.assertIsNone(freshness["average_lag_seconds"])
        self.assertEqual(freshness["stations_online"], 0)
        self.assertEqual(freshness["stations"][0]["status"], "UNKNOWN")

    def test_dashboard_is_single_read_route_and_manual_pipeline_routes_are_absent(self):
        registered = {
            (route.path, method)
            for route in router.routes
            for method in getattr(route, "methods", set())
        }
        self.assertIn(("/api/dashboard", "GET"), registered)
        self.assertIn(("/api/ml/forecasts", "GET"), registered)
        for path in ("/api/ml/train", "/api/ml/forecast", "/api/ingestion/sync", "/api/ingestion/historical"):
            self.assertFalse(any(route_path == path for route_path, _ in registered), path)

    def test_network_pollution_trend_uses_station_hour_means_and_excludes_bad_quality(self):
        hour = dt.datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        self.db.add_all([
            Station(id="AQ-A", name="A", latitude=6.2, longitude=-75.5, station_type="air_quality", active=True),
            Station(id="AQ-B", name="B", latitude=6.3, longitude=-75.6, station_type="air_quality", active=True),
        ])
        self.db.add_all([
            Observation(station_id="AQ-A", variable_id="PM25", observed_at=hour + dt.timedelta(minutes=5), value=10, unit="µg/m³", source="SIATA", quality_status="good"),
            Observation(station_id="AQ-A", variable_id="PM25", observed_at=hour + dt.timedelta(minutes=35), value=14, unit="µg/m³", source="SIATA", quality_status="good"),
            Observation(station_id="AQ-B", variable_id="PM25", observed_at=hour + dt.timedelta(minutes=10), value=20, unit="µg/m³", source="SIATA", quality_status="good"),
            Observation(station_id="AQ-B", variable_id="PM25", observed_at=hour + dt.timedelta(minutes=20), value=999, unit="µg/m³", source="SIATA", quality_status="extreme_value"),
        ])
        self.db.commit()
        snapshot = build_dashboard_snapshot(self.db)
        point = snapshot["network_history"]["PM25"]["series"][-1]
        self.assertEqual(point["value"], 16)
        self.assertEqual(point["count"], 2)
        self.assertIn("sin interpolación", snapshot["network_history"]["PM25"]["spatial_resolution"])


if __name__ == "__main__":
    unittest.main()
