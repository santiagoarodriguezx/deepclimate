"""
Real-time Air Quality Ingestion Adapter.
Consumes official SIATA layer services for PM2.5, PM10, and Ozone.
Maintains continuous freshness without fragile scraping.
"""

import datetime
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from backend.database.repository import EnvironmentalRepository
from backend.ingestion.siata.client import SiataClient
from backend.utils.time import parse_siata_local_time


class AirQualityAdapter:
    LAYER_URL = "https://siata.gov.co/siata_nuevo/index.php/capa_service/consultar_capa_carga"

    LAYERS = {
        "PM25_POECA": {"id_capa": "C_00000000000000000000602", "variable": "PM25", "unit": "µg/m³"},
        "PM25_NO_POECA": {"id_capa": "C_00000000000000000000603", "variable": "PM25", "unit": "µg/m³"},
        "PM10_24H": {"id_capa": "C_00000000000000000000745", "variable": "PM10", "unit": "µg/m³"},
        "OZONE_1H": {"id_capa": "C_00000000000000000000747", "variable": "O3", "unit": "µg/m³"},
    }

    def __init__(self, timeout: float = 15.0):
        self.client = SiataClient(
            headers={
                "User-Agent": "SIATA-Intelligence/1.0 (environmental research)",
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=timeout,
        )

    def fetch_and_ingest(self, db: Session) -> Dict[str, Any]:
        """
        Polls real-time air quality layers from SIATA and ingests latest observations into DB.
        """
        repo = EnvironmentalRepository(db)
        total_ingested = 0
        layer_results = {}

        errors = {}
        for layer_key, cfg in self.LAYERS.items():
            try:
                observations = self._fetch_layer(cfg["id_capa"], cfg["variable"], cfg["unit"], repo)
                count = repo.bulk_insert_observations(observations)
                total_ingested += count
                layer_results[layer_key] = {"fetched": len(observations), "inserted": count}
                if not observations:
                    errors[layer_key] = "La capa no devolvió observaciones válidas."
            except Exception as exc:
                errors[layer_key] = str(exc)

        return {
            "total_inserted": total_ingested,
            "layers": layer_results,
            "errors": errors,
            "ingested_at": datetime.datetime.utcnow().isoformat()
        }

    def _fetch_layer(self, id_capa: str, variable_id: str, unit: str, repo: EnvironmentalRepository) -> List[Dict[str, Any]]:
        observations = []
        try:
            resp = self.client.post(self.LAYER_URL, data={"id_capa": id_capa})
            if resp.status_code != 200:
                return observations

            data = resp.json()
            if data.get("status") != "ok":
                return observations

            for feat in data.get("feature_vector", []):
                attrs = feat.get("atributos", {})
                desc = attrs.get("descripcion", {})

                raw_code = desc.get("Codigo", {}).get("valor_numerico")
                if raw_code is None:
                    raw_code = desc.get("Codigo", {}).get("valor_alfanumerico")
                if raw_code is None:
                    continue

                try:
                    source_id = str(int(float(raw_code)))
                except (ValueError, TypeError):
                    source_id = str(raw_code).strip()

                if not source_id:
                    continue

                # Resolve SIATA's numeric code to the inventory's stable station code.
                st = repo.get_station_by_id_or_code(source_id)
                if not st:
                    st = repo.get_station_by_id_or_code(f"SIATA-{source_id}")
                try:
                    import json
                    coords = json.loads(feat.get("geometry_text") or "{}").get("coordinates", [])
                    longitude, latitude = float(coords[0]), float(coords[1])
                    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                        continue
                except (TypeError, ValueError, IndexError, AttributeError):
                    continue

                if not st:
                    st = self._nearest_inventory_station(repo, latitude, longitude)
                if not st:
                    muni = desc.get("Municipio", {}).get("valor_alfanumerico") or "Medellín"
                    st = repo.upsert_station({
                        "id": f"SIATA-{source_id}",
                        "source_id": source_id,
                        "name": f"Estación SIATA {source_id}",
                        "code": f"SIATA-{source_id}",
                        "municipality": muni,
                        "latitude": latitude,
                        "longitude": longitude,
                        "station_type": "air_quality",
                        "active": True
                    })

                # Extract observation value (SIATA often stores values as string in valor_alfanumerico)
                raw_val = None
                concentration = desc.get("concentracion_maximo_operador", {})
                raw_val = concentration.get("valor_numerico")
                if raw_val is None:
                    raw_val = concentration.get("valor_alfanumerico")

                if raw_val is None:
                    continue

                try:
                    val = float(raw_val)
                    if val < 0:
                        continue
                except (ValueError, TypeError):
                    continue

                # Extract observation timestamp
                ts_str = desc.get("fecha_ultima_actualizacion", {}).get("valor_alfanumerico")
                obs_time = parse_siata_local_time(ts_str)
                if obs_time is None:
                    continue

                # Quality indicator
                quality_status = "good"
                if val > 300:
                    quality_status = "extreme_value"

                observations.append({
                    "station_id": st.id,
                    "variable_id": variable_id,
                    "observed_at": obs_time,
                    "value": float(val),
                    "raw_value": str(val),
                    "unit": unit,
                    "quality_code": "realtime_ok",
                    "quality_status": quality_status,
                    "source": "siata_layer_service"
                })

        except Exception:
            raise

        return observations

    @staticmethod
    def _nearest_inventory_station(repo: EnvironmentalRepository, latitude: float, longitude: float):
        """Match feeds with missing inventory IDs only when coordinates are within 200 m."""
        import math

        candidates = repo.get_stations(station_type="air_quality")
        nearest, nearest_distance = None, float("inf")
        for station in candidates:
            lat1, lat2 = math.radians(latitude), math.radians(station.latitude)
            dlat = lat2 - lat1
            dlon = math.radians(station.longitude - longitude)
            a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
            distance = 6371 * 2 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1 - a)))
            if distance < nearest_distance:
                nearest, nearest_distance = station, distance
        return nearest if nearest_distance <= 0.2 else None

    def close(self):
        self.client.close()
