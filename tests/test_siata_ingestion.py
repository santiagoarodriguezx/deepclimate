import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database.models import Base, Observation, Variable
from backend.database.models import Station
from backend.database.repository import EnvironmentalRepository
from backend.ingestion.siata.air import AirQualityAdapter
from backend.ingestion.siata.meteorology import MeteorologyAdapter
from backend.ingestion.siata.stations import StationAdapter
from backend.utils.time import parse_siata_local_time


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, feeds):
        self.feeds = feeds

    def get(self, url):
        return FakeResponse(self.feeds[url.rsplit("/", 1)[-1]])

    def close(self):
        pass


class FakeAirClient(FakeClient):
    def post(self, url, **kwargs):
        return FakeResponse({
            "status": "ok",
            "feature_vector": [{
                "atributos": {"descripcion": {
                    "Codigo": {"valor_alfanumerico": "28"},
                    "Municipio": {"valor_alfanumerico": "Itagüí"},
                    "concentracion_maximo_operador": {"valor_numerico": "14.2"},
                    "ICA_PM25_Valor": {"valor_numerico": "51"},
                    "fecha_ultima_actualizacion": {"valor_alfanumerico": "2026-10-30 10:10:00"},
                }},
                "geometry_text": '{"type":"Point","coordinates":[-75.5972061,6.1856666]}',
            }],
        })


class SiataIngestionTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.engine = engine
        self.db = sessionmaker(bind=engine)()
        self.db.add_all([
            Variable(id="rain", code="rain", name="Rain", unit="mm", category="hydrology"),
            Variable(id="river_level", code="river_level", name="Level", unit="m", category="hydrology"),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_meteorology_feeds_ingest_without_synthetic_coordinates(self):
        valid = {"codigo": "1019", "nombre": "Meteo", "ciudad": "Medellín", "latitud": 6.2, "longitud": -75.5, "valor": "1.2"}
        missing_geo = {"codigo": "bad", "valor": "2.0"}
        adapter = MeteorologyAdapter()
        adapter.client.close()
        adapter.client = FakeClient({
            "PluviometricaMeteo.json": {"estaciones": [valid, missing_geo]},
            "Pluviometrica.json": {"estaciones": [{**valid, "codigo": "pluv-1"}]},
            "Nivel.json": {"estaciones": [{**valid, "codigo": "river-1"}]},
        })
        try:
            result = adapter.fetch_and_ingest(self.db, sample_telemetry=0)
        finally:
            adapter.client.close()

        self.assertEqual(result["meteo_rain_records"], 2)
        self.assertEqual(self.db.query(Observation).count(), 3)
        self.assertIsNone(
            self.db.query(Observation).filter(Observation.station_id == "METEO-bad").first()
        )

    def test_local_siata_timestamp_converts_to_utc(self):
        result = parse_siata_local_time("2026-10-30 10:10:00")
        self.assertEqual(result.isoformat(), "2026-10-30T15:10:00")
        self.assertIsNone(parse_siata_local_time("not a timestamp"))

    def test_station_inventory_decodes_utf8_names(self):
        self.assertEqual(StationAdapter._decode_text(b"Estaci\xc3\xb3n"), "Estación")

    def test_air_layer_matches_inventory_by_coordinates_and_uses_concentration(self):
        self.db.add(Station(
            id="ITA-CJUS", source_id="", name="Casa de Justicia", code="ITA-CJUS",
            municipality="Itagüí", latitude=6.1856666, longitude=-75.5972061,
            station_type="air_quality", active=True,
        ))
        self.db.commit()
        adapter = AirQualityAdapter()
        adapter.client.close()
        adapter.client = FakeAirClient({})
        try:
            rows = adapter._fetch_layer(
                "layer-id", "PM25", "µg/m³", EnvironmentalRepository(self.db)
            )
        finally:
            adapter.client.close()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["station_id"], "ITA-CJUS")
        self.assertEqual(rows[0]["value"], 14.2)


if __name__ == "__main__":
    unittest.main()
