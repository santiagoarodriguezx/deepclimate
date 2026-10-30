"""
Station Ingestion and Canonical Mapping Adapter.
Extracts stations from official SIATA metadata sources:
- https://siata.gov.co/CalidadAire/cadatos/Estaciones.txt
- https://siata.gov.co/data/siata_app/PluviometricaMeteo.json
"""

import csv
import io
import json
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from backend.database.repository import EnvironmentalRepository
from backend.ingestion.siata.client import SiataClient


class StationAdapter:
    def __init__(self, timeout: float = 12.0):
        self.client = SiataClient(
            headers={"User-Agent": "SIATA-Intelligence/1.0 (environmental research)"},
            timeout=timeout,
        )

    def sync_stations(self, db: Session) -> Dict[str, Any]:
        """
        Fetches official station inventories and populates the canonical stations table.
        """
        repo = EnvironmentalRepository(db)
        stats = {"air_quality_count": 0, "meteo_count": 0, "total_synced": 0}
        errors = {}

        # 1. Calidad del Aire stations
        try:
            air_stations = self.fetch_air_quality_stations()
        except Exception as exc:
            errors["air_quality"] = str(exc)
            air_stations = []
        for st in air_stations:
            repo.upsert_station(st)
            stats["air_quality_count"] += 1

        # 2. Meteorology & Rain stations
        try:
            meteo_stations = self.fetch_meteo_stations()
        except Exception as exc:
            errors["meteorology"] = str(exc)
            meteo_stations = []
        for st in meteo_stations:
            repo.upsert_station(st)
            stats["meteo_count"] += 1

        if not air_stations and not meteo_stations:
            raise RuntimeError("SIATA no devolvió inventarios de estaciones.")
        db.commit()
        stats["total_synced"] = stats["air_quality_count"] + stats["meteo_count"]
        stats["errors"] = errors
        return stats

    def fetch_air_quality_stations(self) -> List[Dict[str, Any]]:
        """Parses https://siata.gov.co/CalidadAire/cadatos/Estaciones.txt"""
        url = "https://siata.gov.co/CalidadAire/cadatos/Estaciones.txt"
        stations = []
        try:
            resp = self.client.get(url)
            if resp.status_code != 200:
                return stations

            text = self._decode_text(resp.content)
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            reader = csv.DictReader(lines, skipinitialspace=True)
            for row in reader:
                code = (row.get("Nombre") or "").strip()
                if not code:
                    continue

                source_id = (row.get("Código") or "").strip()
                name = (row.get("Nombre_Estacion") or row.get("Nombre_Largo") or code).strip()
                muni = (row.get("Municipio") or "Medellín").strip()

                try:
                    lat = float(row.get("Latitud", 0.0))
                    lon = float(row.get("Longitud", 0.0))
                except (ValueError, TypeError):
                    continue

                if not (-90 <= lat <= 90 and -180 <= lon <= 180) or lat == 0.0 or lon == 0.0:
                    continue

                measured_vars = []
                for var_key, can_code in [
                    ("PM2.5", "PM25"), ("PM10", "PM10"), ("NO", "NO"),
                    ("NO2", "NO2"), ("Ozono", "O3"), ("CO", "CO"), ("SO2", "SO2")
                ]:
                    if row.get(var_key) == "1":
                        measured_vars.append(can_code)

                stations.append({
                    "id": code,
                    "source_id": source_id,
                    "name": name,
                    "code": code,
                    "municipality": muni,
                    "latitude": lat,
                    "longitude": lon,
                    "altitude": None,
                    "station_type": "air_quality",
                    "active": True,
                    "metadata_json": json.dumps({"measured_variables": measured_vars})
                })
        except Exception:
            raise

        return stations

    def fetch_meteo_stations(self) -> List[Dict[str, Any]]:
        """Parses https://siata.gov.co/data/siata_app/PluviometricaMeteo.json"""
        url = "https://siata.gov.co/data/siata_app/PluviometricaMeteo.json"
        stations = []
        try:
            resp = self.client.get(url)
            if resp.status_code != 200:
                return stations

            data = resp.json()
            raw_stations = data.get("estaciones", [])
            for st in raw_stations:
                code_id = str(st.get("codigo"))
                st_id = f"METEO-{code_id}"
                name = st.get("nombre", f"Estación Meteorológica {code_id}")
                muni = st.get("ciudad", "Medellín")
                lat = float(st.get("latitud", 0.0))
                lon = float(st.get("longitud", 0.0))

                if not (-90 <= lat <= 90 and -180 <= lon <= 180) or lat == 0.0 or lon == 0.0:
                    continue

                stations.append({
                    "id": st_id,
                    "source_id": code_id,
                    "name": name,
                    "code": st_id,
                    "municipality": muni,
                    "latitude": lat,
                    "longitude": lon,
                    "altitude": None,
                    "station_type": "meteorology",
                    "active": True,
                    "subbasin": st.get("subcuenca"),
                    "neighborhood": st.get("barrio"),
                    "metadata_json": json.dumps({"comuna": st.get("comuna", "")})
                })
        except Exception:
            raise

        return stations

    def close(self):
        self.client.close()

    @staticmethod
    def _decode_text(content: bytes) -> str:
        try:
            return content.decode("utf-8-sig")
        except UnicodeDecodeError:
            return content.decode("latin-1")
