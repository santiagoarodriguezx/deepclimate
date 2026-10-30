import datetime
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database.models import Base, EnvironmentalEvent, Observation, Station, Variable
from backend.events.alert_engine import AlertEngine
from backend.monitoring.freshness import FreshnessMonitor
from backend.monitoring.freshness import is_recent_observation


class FixedSpatialDetector:
    def __init__(self):
        self.enabled = True

    def detect_spatial_anomalies(self, observations):
        if not self.enabled:
            return []
        target = observations[0]
        return [{
            "station_id": target["station_id"], "station_name": target["station_name"],
            "municipality": target["municipality"], "value": target["value"],
            "neighbor_mean": 10.0, "local_deviation_score": 3.0,
        }]


class MonitoringAndAlertTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.db.add(Variable(id="PM25", code="PM25", name="PM2.5", unit="µg/m³", category="air"))
        self.db.add(Variable(id="rain", code="rain", name="Rain", unit="mm", category="hydrology"))
        for index in range(3):
            station_id = f"AIR-{index}"
            self.db.add(Station(
                id=station_id, source_id=str(index), name=station_id, code=station_id,
                municipality="Medellín", latitude=6.2 + index * 0.01, longitude=-75.5,
                station_type="air_quality", active=True,
            ))
            self.db.add(Observation(
                station_id=station_id, variable_id="PM25", observed_at=datetime.datetime.utcnow(),
                value=20 + index, unit="µg/m³", source="test", quality_status="good",
            ))
        self.db.add(Station(
            id="MET-1", source_id="4", name="Meteo", code="MET-1", municipality="Medellín",
            latitude=6.2, longitude=-75.5, station_type="meteorology", active=True,
        ))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_air_quality_freshness_uses_only_relevant_network(self):
        report = FreshnessMonitor(self.db).get_valley_freshness_report("PM25")
        self.assertEqual(report["total_stations"], 3)
        self.assertEqual(report["status_distribution"]["UNKNOWN"], 0)

    def test_alerts_update_in_place_and_close_when_resolved(self):
        engine = AlertEngine(self.db)
        detector = FixedSpatialDetector()
        engine.spatial_detector = detector

        self.assertEqual(len(engine.evaluate_events()), 1)
        self.assertEqual(len(engine.evaluate_events()), 0)
        self.assertEqual(self.db.query(EnvironmentalEvent).filter_by(active=True).count(), 1)

        detector.enabled = False
        engine.evaluate_events()
        self.assertEqual(self.db.query(EnvironmentalEvent).filter_by(active=True).count(), 0)

    def test_stale_observations_do_not_create_current_alerts(self):
        cutoff = datetime.datetime.utcnow() - datetime.timedelta(hours=5)
        for observation in self.db.query(Observation).all():
            observation.observed_at = cutoff
        self.db.commit()

        self.assertEqual(AlertEngine(self.db).evaluate_events(), [])
        self.assertEqual(self.db.query(EnvironmentalEvent).filter_by(active=True).count(), 0)

    def test_recent_observation_uses_utc_naive_database_convention(self):
        now = datetime.datetime(2026, 1, 1, 15, tzinfo=datetime.timezone.utc)
        self.assertTrue(is_recent_observation(datetime.datetime(2026, 1, 1, 14), now=now))
        self.assertFalse(is_recent_observation(datetime.datetime(2026, 1, 1, 10), now=now))


if __name__ == "__main__":
    unittest.main()
