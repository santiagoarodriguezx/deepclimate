"""
Real-time Meteorology and Pluviometric Network Ingestion Adapter.
Consumes:
- https://siata.gov.co/data/siata_app/PluviometricaMeteo.json
- https://siata.gov.co/data/siata_app/Pluviometrica.json
- Station telemetry feeds: https://siata.gov.co/data/siata_app/{codigo}.json
"""

import datetime
import math
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from backend.database.repository import EnvironmentalRepository
from backend.ingestion.siata.client import SiataClient


class MeteorologyAdapter:
    BASE_URL = "https://siata.gov.co/data/siata_app"

    def __init__(self, timeout: float = 12.0):
        self.client = SiataClient(
            headers={"User-Agent": "SIATA-Intelligence/1.0 (environmental research)"},
            timeout=timeout,
        )

    def fetch_and_ingest(self, db: Session, sample_telemetry: int = 10) -> Dict[str, Any]:
        """
        Polls meteorology and rain feeds, plus individual station telemetry for detailed variables.
        """
        repo = EnvironmentalRepository(db)
        total_inserted = 0
        now = datetime.datetime.utcnow()

        errors = {}
        feed_counts = {}
        for feed, prefix, variable, unit, station_type, quality in [
            ("PluviometricaMeteo.json", "METEO", "rain", "mm", "meteorology", "retrieval_timestamp"),
            ("Pluviometrica.json", "PLUV", "rain", "mm", "pluviometric", "retrieval_timestamp"),
            ("Nivel.json", "RIVER", "river_level", "unknown", "stream_level", "unvalidated_unit"),
        ]:
            try:
                response = self.client.get(f"{self.BASE_URL}/{feed}")
                records = response.json().get("estaciones")
                if not isinstance(records, list):
                    raise ValueError(f"{feed} no contiene una lista de estaciones.")
                observations = []
                for station in records:
                    value = self._number(station.get("valor"))
                    code = station.get("codigo")
                    if value is None or value == -999 or code is None:
                        continue
                    station_id = f"{prefix}-{code}"
                    existing_station = repo.get_station_by_id_or_code(station_id)
                    latitude = self._number(station.get("latitud"))
                    longitude = self._number(station.get("longitud"))
                    valid_coordinates = (
                        latitude is not None and longitude is not None
                        and -90 <= latitude <= 90 and -180 <= longitude <= 180
                        and latitude != 0 and longitude != 0
                    )
                    if valid_coordinates:
                        repo.upsert_station({
                            "id": station_id,
                            "source_id": str(code),
                            "name": station.get("nombre") or station_id,
                            "code": station_id,
                            "municipality": station.get("ciudad") or "Valle de Aburrá",
                            "latitude": latitude,
                            "longitude": longitude,
                            "station_type": station_type,
                            "active": True,
                        })
                    elif not existing_station:
                        continue
                    observations.append({
                        "station_id": station_id,
                        "variable_id": variable,
                        "observed_at": now,
                        "value": value,
                        "raw_value": str(station.get("valor")),
                        "unit": unit,
                        "quality_code": "source_timestamp_not_published",
                        "quality_status": quality,
                        "source": f"siata_{feed.removesuffix('.json').lower()}_snapshot",
                    })
                inserted = repo.bulk_insert_observations(observations)
                total_inserted += inserted
                feed_counts[feed] = {"fetched": len(observations), "inserted": inserted}
                if not observations:
                    errors[feed] = "El feed no devolvió observaciones válidas."
            except Exception as exc:
                errors[feed] = str(exc)

        # 2. Query detailed telemetry for sample weather stations (temp, humidity, wind)
        telemetry_obs = []
        # Key weather stations in Aburrá valley
        key_stations = ["1019", "201", "202", "206", "829", "840", "871", "897", "68", "73"]
        for st_code in key_stations[:sample_telemetry]:
            try:
                resp = self.client.get(f"{self.BASE_URL}/{st_code}.json")
                if resp.status_code != 200:
                    continue
                d = resp.json()
                st_id = f"METEO-{st_code}"

                # Parse timestamp if valid
                epoch_str = d.get("date")
                obs_time = now
                if epoch_str:
                    try:
                        obs_time = datetime.datetime.fromtimestamp(float(epoch_str), datetime.timezone.utc).replace(tzinfo=None)
                    except (ValueError, OSError, OverflowError):
                        continue

                # Temperature
                temperature = self._number(d.get("t"))
                if temperature is not None and temperature != -999 and -50 <= temperature <= 65:
                    telemetry_obs.append({
                        "station_id": st_id,
                        "variable_id": "temperature",
                        "observed_at": obs_time,
                        "value": temperature,
                        "raw_value": str(d["t"]),
                        "unit": "°C",
                        "quality_code": "realtime",
                        "quality_status": "good",
                        "source": "siata_station_telemetry"
                    })

                # Humidity
                humidity = self._number(d.get("h"))
                if humidity is not None and 0 <= humidity <= 100:
                    telemetry_obs.append({
                        "station_id": st_id,
                        "variable_id": "humidity",
                        "observed_at": obs_time,
                        "value": humidity,
                        "raw_value": str(d["h"]),
                        "unit": "%",
                        "quality_code": "realtime",
                        "quality_status": "good",
                        "source": "siata_station_telemetry"
                    })

                # Wind Speed
                wind_speed = self._number(d.get("ws"))
                if wind_speed is not None and 0 <= wind_speed <= 100:
                    telemetry_obs.append({
                        "station_id": st_id,
                        "variable_id": "wind_speed",
                        "observed_at": obs_time,
                        "value": wind_speed,
                        "raw_value": str(d["ws"]),
                        "unit": "m/s",
                        "quality_code": "realtime",
                        "quality_status": "good",
                        "source": "siata_station_telemetry"
                    })

                # Wind Direction
                wind_direction = self._number(d.get("wd"))
                if wind_direction is not None and 0 <= wind_direction <= 360:
                    telemetry_obs.append({
                        "station_id": st_id,
                        "variable_id": "wind_direction",
                        "observed_at": obs_time,
                        "value": wind_direction,
                        "raw_value": str(d["wd"]),
                        "unit": "°",
                        "quality_code": "realtime",
                        "quality_status": "good",
                        "source": "siata_station_telemetry"
                    })

            except Exception as exc:
                errors[f"station_{st_code}"] = str(exc)
                continue

        total_inserted += repo.bulk_insert_observations(telemetry_obs)

        return {
            "total_inserted": total_inserted,
            "feeds": feed_counts,
            "meteo_rain_records": sum(
                feed.get("fetched", 0)
                for name, feed in feed_counts.items()
                if name in {"PluviometricaMeteo.json", "Pluviometrica.json"}
            ),
            "telemetry_records": len(telemetry_obs),
            "errors": errors,
            "ingested_at": now.isoformat()
        }

    @staticmethod
    def _number(value):
        try:
            number = float(value)
            return number if math.isfinite(number) else None
        except (TypeError, ValueError):
            return None

    def close(self):
        self.client.close()
