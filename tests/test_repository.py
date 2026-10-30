import datetime
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database.models import Base, Observation, Station, Variable
from backend.database.repository import EnvironmentalRepository


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.db.add(Variable(id="PM25", code="PM25", name="PM2.5", unit="µg/m³", category="air"))
        self.db.add(Station(
            id="ST-1", source_id="1", name="Station", code="ST-1", municipality="Medellín",
            latitude=6.2, longitude=-75.5, station_type="air_quality", active=True,
        ))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_bulk_insert_normalizes_utc_and_ignores_duplicate(self):
        timestamp = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone(datetime.timedelta(hours=-5)))
        observation = {
            "station_id": "ST-1", "variable_id": "PM25", "observed_at": timestamp,
            "value": 9.5, "unit": "µg/m³", "source": "test",
        }
        repo = EnvironmentalRepository(self.db)

        self.assertEqual(repo.bulk_insert_observations([observation, observation]), 1)
        stored = self.db.query(Observation).one()
        self.assertEqual(stored.observed_at, datetime.datetime(2026, 1, 1, 5))
        self.assertEqual(repo.get_latest_by_variable("PM25")[0]["value"], 9.5)


if __name__ == "__main__":
    unittest.main()
